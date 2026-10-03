"""Translate the deliberately small supported Pydantic subset to MongoDB JSON Schema."""

import types
from datetime import datetime
from typing import Literal, Union, get_args, get_origin

from pydantic import BaseModel


class SchemaTranslator:
    SCALARS = {
        str: ["string"],
        int: ["int", "long"],
        float: ["double", "int", "long", "decimal"],
        bool: ["bool"],
        datetime: ["date"],
    }

    def translate(self, model: type[BaseModel]) -> dict:
        decorators = model.__pydantic_decorators__
        if decorators.field_validators or decorators.model_validators or decorators.validators or decorators.root_validators:
            raise TypeError(f"Unsupported custom validator on {model.__name__}")
        if decorators.field_serializers or decorators.model_serializers:
            raise TypeError(f"Unsupported custom serializer on {model.__name__}")
        if model.model_config.get("extra") == "forbid":
            raise TypeError("extra='forbid' is not supported yet (MongoDB documents also contain _id)")
        properties, required = {}, []
        for name, field in model.model_fields.items():
            if field.metadata:
                raise TypeError(f"Unsupported constraints on field {name}: {field.metadata}")
            if field.validation_alias is not None and not isinstance(field.validation_alias, str):
                raise TypeError(f"Unsupported AliasPath/AliasChoices on {name}")
            validation_key = field.validation_alias or field.alias or name
            key = field.serialization_alias or field.alias or name
            if validation_key != key:
                raise TypeError(
                    f"Unsupported alias mismatch on {name}: input name {validation_key!r} "
                    f"differs from stored name {key!r}"
                )
            if key.startswith("$") or "." in key:
                raise TypeError(f"Unsupported stored field name: {key}")
            properties[key] = self.field_schema(field.annotation)
            if field.is_required():
                required.append(key)
        result = {"bsonType": "object", "properties": properties}
        if required:
            result["required"] = required
        return result

    def field_schema(self, annotation) -> dict:
        origin, args = get_origin(annotation), get_args(annotation)
        if origin in (Union, types.UnionType):
            return self._nullable(annotation, args)
        if origin is Literal:
            return {"enum": list(args)}
        if origin is list:
            if len(args) != 1:
                raise TypeError(f"Unsupported list type: {annotation}")
            return {"bsonType": "array", "items": self.field_schema(args[0])}
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            return self.translate(annotation)
        if annotation in self.SCALARS:
            bson_types = self.SCALARS[annotation]
            return {"bsonType": bson_types[0] if len(bson_types) == 1 else bson_types}
        raise TypeError(f"Unsupported field type: {annotation}")

    def _nullable(self, annotation, args) -> dict:
        non_null = [arg for arg in args if arg is not type(None)]
        if len(non_null) != 1 or len(non_null) == len(args):
            raise TypeError(f"Unsupported union: {annotation}")
        schema = self.field_schema(non_null[0])
        if "enum" in schema:
            schema["enum"].append(None)
        else:
            existing = schema["bsonType"]
            schema["bsonType"] = (existing if isinstance(existing, list) else [existing]) + ["null"]
        return schema
