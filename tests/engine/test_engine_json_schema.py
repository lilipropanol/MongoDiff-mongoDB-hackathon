"""Language-agnostic schema sources: standard JSON Schema files and MongoDB $jsonSchema validators."""

import json
from pathlib import Path
from typing import Literal, Optional

import pytest
from pydantic import BaseModel, Field

from schema_guard.engine.json_schema import JsonSchemaConverter
from schema_guard.engine.models import SchemaDocument, load_json_schema, load_model
from schema_guard.engine.translator import SchemaTranslator

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = json.loads((ROOT / "tests/engine/fixtures/engine_starter_snapshot.json").read_text())


def convert(schema):
    return JsonSchemaConverter().convert(schema)


# --- The shipped example files describe exactly the same stored schema as the Python models ---

@pytest.mark.parametrize("filename, key", [
    ("movie_old.schema.json", "old_schema"),
    ("movie_new.schema.json", "new_schema"),
    ("movie_new.validator.json", "new_schema"),
])
def test_example_json_files_match_python_models(filename, key):
    document = load_model(str(ROOT / "examples/engine" / filename))
    assert isinstance(document, SchemaDocument)
    assert SchemaTranslator().translate(document) == SNAPSHOT[key]


def test_pydantic_json_schema_export_round_trips():
    """A JSON Schema exported by another tool (here Pydantic itself) gives the same result as direct translation."""
    class Imdb(BaseModel):
        rating: float
        votes: Optional[int] = None

    class Movie(BaseModel):
        id: str = Field(alias="_id")
        title: str
        runtime: Optional[int]
        rated: Literal["G", "PG", "PG-13", "R"]
        single: Literal["only"]
        genres: list[str]
        imdb: Imdb
        cast: list[Imdb]
        maybe: Optional[Imdb] = None

    exported = Movie.model_json_schema(by_alias=True)
    direct = SchemaTranslator().translate(Movie)
    converted = convert(exported)
    assert converted == {**direct, "properties": {**direct["properties"], "single": {"enum": ["only"]}}}


# --- Type mapping --------------------------------------------------------------------------

@pytest.mark.parametrize("json_type, bson", [
    ("string", "string"),
    ("integer", ["int", "long"]),
    ("number", ["double", "int", "long", "decimal"]),
    ("boolean", "bool"),
    ("null", "null"),
])
def test_json_types_map_to_bson(json_type, bson):
    schema = convert({"type": "object", "properties": {"x": {"type": json_type}}})
    assert schema["properties"]["x"] == {"bsonType": bson}


def test_type_lists_and_nullable_forms():
    schema = convert({"type": "object", "properties": {
        "a": {"type": ["integer", "null"]},
        "b": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "c": {"oneOf": [{"type": "null"}, {"type": "boolean"}]},
        "d": {"type": ["string", "null"], "enum": ["x", "y"]},
    }})
    props = schema["properties"]
    assert props["a"] == {"bsonType": ["int", "long", "null"]}
    assert props["b"] == {"bsonType": ["string", "null"]}
    assert props["c"] == {"bsonType": ["bool", "null"]}
    assert props["d"] == {"enum": ["x", "y", None]}


def test_mongodb_bson_type_schemas_pass_through():
    schema = convert({"bsonType": "object", "required": ["a"], "properties": {
        "a": {"bsonType": "objectId"},
        "b": {"bsonType": ["date", "null"]},
        "c": {"bsonType": "number"},
    }})
    assert schema["properties"]["a"] == {"bsonType": "objectId"}
    assert schema["properties"]["b"] == {"bsonType": ["date", "null"]}
    assert schema["properties"]["c"] == {"bsonType": ["double", "int", "long", "decimal"]}


def test_refs_defs_and_single_allof_are_inlined():
    schema = convert({
        "type": "object",
        "properties": {"imdb": {"$ref": "#/$defs/Imdb"}, "old": {"allOf": [{"$ref": "#/definitions/Old"}]}},
        "required": ["imdb"],
        "$defs": {"Imdb": {"type": "object", "properties": {"rating": {"type": "number"}}, "required": ["rating"]}},
        "definitions": {"Old": {"type": "string"}},
    })
    assert schema["properties"]["imdb"]["required"] == ["rating"]
    assert schema["properties"]["old"] == {"bsonType": "string"}


def test_annotations_are_ignored_and_const_becomes_enum():
    schema = convert({"type": "object", "title": "T", "description": "d", "$schema": "x",
                      "properties": {"k": {"const": "v", "title": "K", "default": "v", "examples": ["v"], "format": "slug"}}})
    assert schema == {"bsonType": "object", "properties": {"k": {"enum": ["v"]}}}


def test_implicit_object_and_array_types():
    schema = convert({"properties": {"tags": {"items": {"type": "string"}}}})
    assert schema["bsonType"] == "object"
    assert schema["properties"]["tags"] == {"bsonType": "array", "items": {"bsonType": "string"}}


def test_load_json_schema_unwraps_validator(tmp_path):
    path = tmp_path / "v.json"
    path.write_text(json.dumps({"$jsonSchema": {"bsonType": "object", "properties": {"a": {"bsonType": "string"}}}}))
    document = load_json_schema(str(path))
    assert document.schema == {"bsonType": "object", "properties": {"a": {"bsonType": "string"}}}


# --- Unsupported input fails clearly -------------------------------------------------------

@pytest.mark.parametrize("schema, message", [
    ({"type": "object", "properties": {"x": {"type": "string", "minLength": 2}}}, r"minLength.*x"),
    ({"type": "object", "additionalProperties": False}, "additionalProperties"),
    ({"type": "object", "properties": {"x": {"anyOf": [{"type": "string"}, {"type": "integer"}]}}}, "or null"),
    ({"type": "object", "properties": {"x": {"$ref": "#/$defs/X"}}, "$defs": {"X": {"$ref": "#/$defs/X"}}}, "Recursive"),
    ({"type": "object", "properties": {"x": {"$ref": "https://example.com/s.json"}}}, "local"),
    ({"type": "object", "properties": {"x": {"$ref": "#/$defs/Missing"}}}, "Unresolvable"),
    ({"type": "object", "properties": {"x": {"type": "float"}}}, "Unknown JSON Schema type"),
    ({"type": "object", "properties": {"x": {"bsonType": "integer"}}}, "Unknown bsonType"),
    ({"type": "object", "properties": {"x": {"type": "string", "bsonType": "string"}}}, "either type or bsonType"),
    ({"type": "object", "properties": {"x": {"type": "array", "items": [{"type": "string"}]}}}, "Tuple-style"),
    ({"type": "object", "properties": {"x": {}}}, "unconstrained"),
    ({"type": "object", "properties": {"$x": {"type": "string"}}}, "stored field name"),
    ({"type": "object", "properties": {"a.b": {"type": "string"}}}, "stored field name"),
    ({"type": "string"}, "top-level"),
    ({"type": "object", "properties": {"x": {"enum": []}}}, "non-empty"),
    ({"type": "object", "properties": {"x": {"allOf": [{"type": "string"}, {"type": "null"}]}}}, "single-entry allOf"),
])
def test_unsupported_json_schema_fails_with_location(schema, message):
    with pytest.raises(TypeError, match=message):
        convert(schema)


def test_invalid_json_file_is_a_value_error(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json")
    with pytest.raises(ValueError, match="not valid JSON"):
        load_json_schema(str(path))
    path.write_text("[1, 2]")
    with pytest.raises(ValueError, match="JSON Schema object"):
        load_json_schema(str(path))
