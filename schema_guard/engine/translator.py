"""Translate the deliberately small supported Pydantic subset (or a JSON schema file) to MongoDB JSON Schema."""

import types
from datetime import datetime
from enum import Enum
from typing import Literal, Union, get_args, get_origin

from pydantic import BaseModel

from .json_schema import JsonSchemaConverter
from .models import SchemaDocument


class SchemaTranslator:
    SCALARS = {
        str: ["string"],
        int: ["int", "long"],
        float: ["double", "int", "long", "decimal"],
        bool: ["bool"],
        datetime: ["date"],
    }

    def __init__(self):
        self._stack = []

    def translate(self, model, path: str = "") -> dict:
        if isinstance(model, SchemaDocument):
            return JsonSchemaConverter().convert(model.schema)
        if model in self._stack:
            raise TypeError(f"Recursive model {model.__name__} is not supported" + (f" (at {path})" if path else ""))
        self._stack.append(model)
        try:
            return self._translate_model(model, path)
        finally:
            self._stack.pop()

    def _translate_model(self, model: type[BaseModel], path: str) -> dict:
        decorators = model.__pydantic_decorators__
        if decorators.field_validators or decorators.model_validators or decorators.validators or decorators.root_validators:
            raise TypeError(f"Unsupported custom validator on {model.__name__}")
        if decorators.field_serializers or decorators.model_serializers:
            raise TypeError(f"Unsupported custom serializer on {model.__name__}: it changes the stored shape")
        if model.model_config.get("extra") == "forbid":
            raise TypeError("extra='forbid' is not supported yet (MongoDB documents also contain _id)")
        properties, required = {}, []
        for name, field in model.model_fields.items():
            if field.metadata:
                raise TypeError(f"Unsupported constraints on field {name}: {field.metadata}")
            if field.validation_alias is not None and not isinstance(field.validation_alias, str):
                raise TypeError(f"Unsupported AliasPath/AliasChoices on {name}")
            if field.exclude:
                raise TypeError(f"Field {name} is excluded from serialization, so it is never stored; remove it from the model")
            validation_key = field.validation_alias or field.alias or name
            key = field.serialization_alias or field.alias or name
            if validation_key != key:
                raise TypeError(f"Unsupported alias mismatch on {name}: input name {validation_key!r} differs from stored name {key!r}")
            if key.startswith("$") or "." in key:
                raise TypeError(f"Unsupported stored field name: {key}")
            properties[key] = self.field_schema(field.annotation, f"{path}.{key}" if path else key)
            if field.is_required():
                required.append(key)
        result = {"bsonType": "object", "properties": properties}
        if required:
            result["required"] = required
        return result

    def field_schema(self, annotation, path: str = "") -> dict:
        origin, args = get_origin(annotation), get_args(annotation)
        if origin in (Union, types.UnionType):
            return self._nullable(annotation, args, path)
        if origin is Literal:
            return {"enum": list(args)}
        if origin is list:
            if len(args) != 1:
                raise TypeError(f"Unsupported list type{self._at(path)}: {annotation}")
            return {"bsonType": "array", "items": self.field_schema(args[0], f"{path}[]")}
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            return self.translate(annotation, path)
        if isinstance(annotation, type) and issubclass(annotation, Enum):
            return self._enum(annotation, path)
        if annotation in self.SCALARS:
            bson_types = self.SCALARS[annotation]
            return {"bsonType": bson_types[0] if len(bson_types) == 1 else bson_types}
        raise TypeError(f"Unsupported field type{self._at(path)}: {annotation}")

    def _enum(self, annotation, path) -> dict:
        values = [member.value for member in annotation]
        if not values or not all(type(v) in (str, int) for v in values):
            raise TypeError(f"Only Enums with str or int values are supported{self._at(path)}: {annotation.__name__}")
        return {"enum": values}

    def _nullable(self, annotation, args, path) -> dict:
        non_null = [arg for arg in args if arg is not type(None)]
        if len(non_null) != 1 or len(non_null) == len(args):
            raise TypeError(f"Unsupported union{self._at(path)}: {annotation}")
        schema = self.field_schema(non_null[0], path)
        if "enum" in schema:
            schema["enum"].append(None)
        else:
            existing = schema["bsonType"]
            schema["bsonType"] = (existing if isinstance(existing, list) else [existing]) + ["null"]
        return schema

    @staticmethod
    def _at(path):
        return f" at {path}" if path else ""
