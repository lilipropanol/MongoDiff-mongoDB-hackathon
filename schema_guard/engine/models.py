"""Load schema sources: Pydantic models (FILE.py:Class) or language-agnostic JSON schema files (FILE.json)."""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from pydantic import BaseModel


class SchemaDocument:
    """A schema loaded from JSON: standard JSON Schema (from any language) or a MongoDB {$jsonSchema: ...} validator."""

    def __init__(self, schema: dict, path: Path):
        self.schema = schema
        self.path = path
        self.__name__ = path.name

    def __repr__(self):
        return f"SchemaDocument({self.path})"


def load_model(spec: str) -> type[BaseModel] | SchemaDocument:
    if spec.lower().endswith(".json"):
        return load_json_schema(spec)
    try:
        filename, class_name = spec.rsplit(":", 1)
    except ValueError as exc:
        raise ValueError(f"Model must use FILE.py:Class or FILE.json notation, got {spec!r}") from exc
    path = Path(filename).resolve()
    # The path hash keeps two files with the same name (e.g. a/models.py, b/models.py) from sharing a module.
    digest = hashlib.sha1(str(path).encode()).hexdigest()[:8]
    module_spec = importlib.util.spec_from_file_location(f"schema_guard_model_{path.stem}_{digest}", path)
    if module_spec is None or module_spec.loader is None:
        raise ValueError(f"Cannot load model file: {path}")
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[module_spec.name] = module
    module_spec.loader.exec_module(module)
    model = getattr(module, class_name, None)
    if not isinstance(model, type) or not issubclass(model, BaseModel):
        raise ValueError(f"{class_name} in {path} is not a Pydantic BaseModel")
    return model


def load_collection_validator(collection) -> tuple[SchemaDocument | None, dict]:
    """Read the $jsonSchema validator a collection enforces today (language-agnostic "old schema").

    Read-only: uses listCollections, which the Atlas read role allows. Returns (None, options) when the
    collection has no validator. Validators mixing $jsonSchema with other query operators are rejected.
    """
    infos = list(collection.database.list_collections(filter={"name": collection.name}))
    options = infos[0].get("options", {}) if infos else {}
    settings = {"exists": bool(infos), "validationLevel": options.get("validationLevel"),
                "validationAction": options.get("validationAction")}
    validator = options.get("validator")
    if not validator:
        return None, settings
    if set(validator) != {"$jsonSchema"}:
        raise ValueError(f"Collection validator uses {sorted(validator)}; only a plain $jsonSchema validator is supported")
    return SchemaDocument(validator["$jsonSchema"], Path(f"{collection.database.name}.{collection.name}.validator.json")), settings


def load_json_schema(spec: str) -> SchemaDocument:
    path = Path(spec).resolve()
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc
    if isinstance(data, dict) and "$jsonSchema" in data:
        data = data["$jsonSchema"]
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON Schema object")
    return SchemaDocument(data, path)
