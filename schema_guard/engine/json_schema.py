"""Convert language-agnostic JSON Schema into the MongoDB $jsonSchema subset the engine explains.

Accepts standard JSON Schema (as exported by Zod, TypeScript, Java, Go, Pydantic's model_json_schema(), ...)
and MongoDB-style schemas using bsonType. Output matches the shape SchemaTranslator produces for Pydantic,
so diff and impact treat every source the same. Unsupported keywords fail clearly instead of being guessed.
"""

TYPE_MAP = {
    "string": ["string"],
    "integer": ["int", "long"],
    "number": ["double", "int", "long", "decimal"],
    "boolean": ["bool"],
    "null": ["null"],
    "object": ["object"],
    "array": ["array"],
}
BSON_TYPES = {"double", "string", "object", "array", "binData", "objectId", "bool", "date", "null",
              "regex", "int", "timestamp", "long", "decimal"}
BSON_ALIASES = {"number": ["double", "int", "long", "decimal"]}
# Annotations that do not change which stored documents are valid.
IGNORED = {"title", "description", "$schema", "$id", "$comment", "default", "examples", "format",
           "readOnly", "writeOnly", "deprecated", "$defs", "definitions"}
STRUCTURAL = {"type", "bsonType", "enum", "const", "properties", "required", "items",
              "additionalProperties", "anyOf", "oneOf", "allOf", "$ref"}


class JsonSchemaConverter:
    def convert(self, schema: dict) -> dict:
        self._root = schema
        self._stack = []
        result = self._node(schema, "")
        if self._types(result) != ["object"]:
            raise TypeError("The top-level schema must describe an object (a MongoDB document)")
        return result

    def _node(self, node, path) -> dict:
        where = path or "<root>"
        if not isinstance(node, dict):
            raise TypeError(f"Schema at {where} must be an object, got {type(node).__name__}")
        if "$ref" in node:
            return self._ref(node["$ref"], path)
        unknown = set(node) - IGNORED - STRUCTURAL
        if unknown:
            raise TypeError(f"Unsupported JSON Schema keyword(s) {sorted(unknown)} at {where}; the engine cannot explain them faithfully")
        for combinator in ("anyOf", "oneOf"):
            if combinator in node:
                return self._nullable_union(node, combinator, path)
        if "allOf" in node:
            parts = node["allOf"]
            if not isinstance(parts, list) or len(parts) != 1 or set(node) - IGNORED - {"allOf"}:
                raise TypeError(f"Only a single-entry allOf wrapper is supported at {where}")
            return self._node(parts[0], path)
        return self._plain(node, path, where)

    def _plain(self, node, path, where) -> dict:
        if "type" in node and "bsonType" in node:
            raise TypeError(f"Use either type or bsonType at {where}, not both")
        types = self._json_types(node["type"], where) if "type" in node else self._bson_types(node.get("bsonType"), where)
        if not types and ("properties" in node or "required" in node):
            types = ["object"]
        if not types and "items" in node:
            types = ["array"]
        result = {}
        if "enum" in node or "const" in node:
            if "enum" in node and "const" in node:
                raise TypeError(f"Use either enum or const at {where}, not both")
            values = [node["const"]] if "const" in node else node["enum"]
            if not isinstance(values, list) or not values:
                raise TypeError(f"enum at {where} must be a non-empty list")
            result["enum"] = list(values)
            if "null" in types and None not in result["enum"]:
                result["enum"].append(None)
            # Like a Pydantic Literal: the enum alone defines the allowed values.
            types = []
        if types:
            result["bsonType"] = types[0] if len(types) == 1 else types
        if "object" in types:
            extra = node.get("additionalProperties", True)
            if extra is not True:
                raise TypeError(f"additionalProperties at {where} is not supported (MongoDB documents also contain _id). "
                                "Remove it from the exported schema, e.g. Zod .passthrough() or your generator's 'allow additional properties' option")
            properties = node.get("properties", {})
            if not isinstance(properties, dict):
                raise TypeError(f"properties at {where} must be an object")
            converted = {}
            for key, child in properties.items():
                if key.startswith("$") or "." in key:
                    raise TypeError(f"Unsupported stored field name: {key}")
                converted[key] = self._node(child, f"{path}.{key}" if path else key)
            result["properties"] = converted
            required = node.get("required", [])
            if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
                raise TypeError(f"required at {where} must be a list of field names")
            if required:
                result["required"] = list(required)
        elif "properties" in node or "required" in node:
            raise TypeError(f"properties/required at {where} need an object type")
        if "items" in node:
            if "array" not in types:
                raise TypeError(f"items at {where} needs an array type")
            if not isinstance(node["items"], dict):
                raise TypeError(f"Tuple-style items at {where} are not supported")
            result["items"] = self._node(node["items"], f"{path}[]")
        if not result:
            raise TypeError(f"Schema at {where} has no type, enum or structure; unconstrained fields are not supported")
        return result

    def _nullable_union(self, node, combinator, path) -> dict:
        where = path or "<root>"
        options = node[combinator]
        if set(node) - IGNORED - {combinator}:
            raise TypeError(f"{combinator} combined with other keywords is not supported at {where}")
        if not isinstance(options, list):
            raise TypeError(f"{combinator} at {where} must be a list")
        nulls = [o for o in options if isinstance(o, dict) and set(o) - IGNORED == {"type"} and o["type"] == "null"]
        others = [o for o in options if o not in nulls]
        if len(others) != 1 or len(nulls) != 1:
            raise TypeError(f"Only '<schema> or null' unions are supported at {where}")
        schema = self._node(others[0], path)
        if "enum" in schema:
            if None not in schema["enum"]:
                schema["enum"].append(None)
        else:
            existing = schema["bsonType"]
            existing = existing if isinstance(existing, list) else [existing]
            if "null" not in existing:
                schema["bsonType"] = existing + ["null"]
        return schema

    def _ref(self, ref, path) -> dict:
        if not isinstance(ref, str) or not ref.startswith("#/"):
            raise TypeError(f"Only local $ref values are supported at {path or '<root>'}: {ref!r}")
        if ref in self._stack:
            raise TypeError(f"Recursive schema reference {ref} is not supported")
        target = self._root
        for part in ref[2:].split("/"):
            if not isinstance(target, dict) or part not in target:
                raise TypeError(f"Unresolvable $ref {ref}")
            target = target[part]
        self._stack.append(ref)
        try:
            return self._node(target, path)
        finally:
            self._stack.pop()

    def _json_types(self, value, where) -> list[str]:
        names = value if isinstance(value, list) else [value]
        types = []
        for name in names:
            if name not in TYPE_MAP:
                raise TypeError(f"Unknown JSON Schema type {name!r} at {where}")
            types += [t for t in TYPE_MAP[name] if t not in types]
        return types

    def _bson_types(self, value, where) -> list[str]:
        if value is None:
            return []
        names = value if isinstance(value, list) else [value]
        types = []
        for name in names:
            expanded = BSON_ALIASES.get(name, [name])
            for item in expanded:
                if item not in BSON_TYPES:
                    raise TypeError(f"Unknown bsonType {name!r} at {where}")
                if item not in types:
                    types.append(item)
        return types

    @staticmethod
    def _types(schema) -> list[str]:
        types = schema.get("bsonType", [])
        return [types] if isinstance(types, str) else list(types)
