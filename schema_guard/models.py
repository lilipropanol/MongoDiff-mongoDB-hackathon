"""Load Pydantic models from Python files using module:Class notation."""

import importlib.util
import sys
from pathlib import Path
from pydantic import BaseModel


def load_model(spec: str) -> type[BaseModel]:
    try:
        filename, class_name = spec.rsplit(":", 1)
    except ValueError as exc:
        raise ValueError(f"Model must use FILE.py:Class notation, got {spec!r}") from exc
    path = Path(filename).resolve()
    module_spec = importlib.util.spec_from_file_location(f"schema_guard_model_{path.stem}", path)
    if module_spec is None or module_spec.loader is None:
        raise ValueError(f"Cannot load model file: {path}")
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[module_spec.name] = module
    module_spec.loader.exec_module(module)
    model = getattr(module, class_name, None)
    if not isinstance(model, type) or not issubclass(model, BaseModel):
        raise ValueError(f"{class_name} in {path} is not a Pydantic BaseModel")
    return model
