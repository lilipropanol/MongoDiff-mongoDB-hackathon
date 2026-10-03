"""Pydantic → MongoDB $jsonSchema translation: supported subset, audit failures and regression snapshot."""

import json
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Annotated, Any, Literal, Optional
from uuid import UUID

import pytest
from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_serializer
from pydantic.alias_generators import to_camel

from schema_guard.engine.models import load_model
from schema_guard.engine.translator import SchemaTranslator

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = json.loads((ROOT / "tests/engine/fixtures/engine_starter_snapshot.json").read_text())


def translate(model):
    return SchemaTranslator().translate(model)


# --- Supported subset -------------------------------------------------------------------------

@pytest.mark.parametrize("annotation, expected", [
    (str, "string"),
    (int, ["int", "long"]),
    (float, ["double", "int", "long", "decimal"]),
    (bool, "bool"),
    (datetime, "date"),
])
def test_scalars_map_to_exact_bson_types(annotation, expected):  # U-T1
    model = type("M", (BaseModel,), {"__annotations__": {"value": annotation}})
    assert translate(model)["properties"]["value"] == {"bsonType": expected}


def test_optional_without_default_is_required_and_nullable():  # U-T2
    class M(BaseModel):
        runtime: Optional[int]

    schema = translate(M)
    assert schema["required"] == ["runtime"]
    assert schema["properties"]["runtime"]["bsonType"] == ["int", "long", "null"]


def test_optional_with_default_is_not_required():  # U-T3
    class M(BaseModel):
        runtime: Optional[int] = None

    schema = translate(M)
    assert "required" not in schema
    assert schema["properties"]["runtime"]["bsonType"] == ["int", "long", "null"]


def test_literal_and_optional_literal():  # U-T4
    class M(BaseModel):
        rated: Literal["G", "PG"]
        maybe: Optional[Literal["G", "PG"]] = None

    props = translate(M)["properties"]
    assert props["rated"] == {"enum": ["G", "PG"]}
    assert props["maybe"] == {"enum": ["G", "PG", None]}


def test_lists_including_nested_lists_and_models():  # U-T5
    class Item(BaseModel):
        name: str

    class M(BaseModel):
        tags: list[str]
        items: list[Item]
        grid: list[list[int]]

    props = translate(M)["properties"]
    assert props["tags"] == {"bsonType": "array", "items": {"bsonType": "string"}}
    assert props["items"]["items"] == {"bsonType": "object", "properties": {"name": {"bsonType": "string"}}, "required": ["name"]}
    assert props["grid"] == {"bsonType": "array", "items": {"bsonType": "array", "items": {"bsonType": ["int", "long"]}}}


def test_nested_and_optional_nested_models():  # U-T6
    class Imdb(BaseModel):
        rating: float
        votes: Optional[int] = None

    class M(BaseModel):
        imdb: Imdb
        maybe: Optional[Imdb] = None

    props = translate(M)["properties"]
    assert props["imdb"]["bsonType"] == "object"
    assert props["imdb"]["required"] == ["rating"]
    assert props["maybe"]["bsonType"] == ["object", "null"]


def test_aliases_become_stored_keys():  # U-T7
    class M(BaseModel):
        id: str = Field(alias="_id")
        other: int = Field(serialization_alias="otherKey", validation_alias="otherKey")

    class Camel(BaseModel):
        model_config = ConfigDict(alias_generator=to_camel)
        run_time: int

    assert set(translate(M)["properties"]) == {"_id", "otherKey"}
    assert translate(Camel)["properties"] == {"runTime": {"bsonType": ["int", "long"]}}


def test_str_and_int_enums_translate_to_values():  # U-T17
    class Color(str, Enum):
        red = "red"
        blue = "blue"

    class Level(int, Enum):
        low = 1
        high = 2

    class M(BaseModel):
        color: Color
        level: Optional[Level] = None

    props = translate(M)["properties"]
    assert props["color"] == {"enum": ["red", "blue"]}
    assert props["level"] == {"enum": [1, 2, None]}


# --- Audit: unsupported behaviour must fail clearly ------------------------------------------

def test_excluded_field_is_rejected():  # U-T8
    class M(BaseModel):
        secret: str = Field(exclude=True)

    with pytest.raises(TypeError, match="excluded"):
        translate(M)


def test_field_and_model_serializers_are_rejected():  # U-T9
    class F(BaseModel):
        x: int

        @field_serializer("x")
        def as_text(self, value):
            return str(value)

    class Mo(BaseModel):
        x: int

        @model_serializer
        def dump(self):
            return {"y": self.x}

    for model in (F, Mo):
        with pytest.raises(TypeError, match="serializer"):
            translate(model)


def test_conflicting_validation_and_serialization_alias():  # U-T10
    class M(BaseModel):
        x: int = Field(validation_alias="a", serialization_alias="b")

    with pytest.raises(TypeError, match="'a'.*'b'"):
        translate(M)


def test_recursive_models_fail_with_clear_message():  # U-T11
    class Node(BaseModel):
        child: Optional["Node"] = None

    class A(BaseModel):
        b: Optional["B"] = None

    class B(BaseModel):
        a: Optional[A] = None

    A.model_rebuild()
    for model in (Node, A):
        with pytest.raises(TypeError, match="Recursive model"):
            translate(model)


def test_translator_is_reusable_after_a_recursion_error():
    class Node(BaseModel):
        child: Optional["Node"] = None

    class Plain(BaseModel):
        x: int

    translator = SchemaTranslator()
    with pytest.raises(TypeError):
        translator.translate(Node)
    assert translator.translate(Plain)["required"] == ["x"]


@pytest.mark.parametrize("field", [
    Field(gt=0),
    Field(strict=True),
])
def test_constraints_are_rejected(field):  # U-T12
    model = type("M", (BaseModel,), {"__annotations__": {"x": int}, "x": field})
    with pytest.raises(TypeError, match="Unsupported constraints"):
        translate(model)


def test_annotated_constraint_is_rejected():
    class M(BaseModel):
        code: Annotated[str, Field(max_length=3)]

    with pytest.raises(TypeError, match="Unsupported constraints"):
        translate(M)


def test_extra_forbid_rejected_at_root_and_nested():  # U-T13
    class Strict(BaseModel):
        model_config = ConfigDict(extra="forbid")
        x: int

    class Outer(BaseModel):
        inner: Strict

    for model in (Strict, Outer):
        with pytest.raises(TypeError, match="extra='forbid'"):
            translate(model)


@pytest.mark.parametrize("annotation", [dict, Any, UUID, Decimal, date, set[str], tuple[int, int], list, int | str])
def test_unsupported_types_name_the_field_path(annotation):  # U-T14
    inner =type("Inner", (BaseModel,), {"__annotations__": {"bad": annotation}})
    outer = type("Outer", (BaseModel,), {"__annotations__": {"wrap": inner}})
    with pytest.raises(TypeError, match=r"wrap\.bad"):
        translate(outer)


@pytest.mark.parametrize("alias", ["$bad", "a.b"])
def test_unsafe_stored_names_rejected(alias):  # U-T15
    model = type("M", (BaseModel,), {"__annotations__": {"x": int}, "x": Field(alias=alias)})
    with pytest.raises(TypeError, match="Unsupported stored field name"):
        translate(model)


def test_custom_validator_still_rejected():
    from pydantic import field_validator

    class M(BaseModel):
        x: int

        @field_validator("x")
        @classmethod
        def check(cls, value):
            return value

    with pytest.raises(TypeError, match="Unsupported custom validator"):
        translate(M)


# --- Regression: starter models translate exactly as before ----------------------------------

def test_starter_example_models_are_unchanged():  # U-T16
    assert translate(load_model(str(ROOT / "examples/models_old.py") + ":Movie")) == SNAPSHOT["old_schema"]
    assert translate(load_model(str(ROOT / "examples/models_new.py") + ":Movie")) == SNAPSHOT["new_schema"]


def test_same_named_model_files_do_not_collide(tmp_path):  # F11
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a/models.py").write_text("from pydantic import BaseModel\nclass M(BaseModel):\n    x: int\n")
    (tmp_path / "b/models.py").write_text("from pydantic import BaseModel\nclass M(BaseModel):\n    y: str\n")
    first = load_model(f"{tmp_path}/a/models.py:M")
    second = load_model(f"{tmp_path}/b/models.py:M")
    assert first.__module__ != second.__module__
    assert set(translate(first)["properties"]) == {"x"}
    assert set(translate(second)["properties"]) == {"y"}


def test_load_model_rejects_bad_specs(tmp_path):
    with pytest.raises(ValueError, match="FILE.py:Class or FILE.json"):
        load_model("no_colon_here.py")
    (tmp_path / "m.py").write_text("X = 1\n")
    with pytest.raises(ValueError, match="not a Pydantic BaseModel"):
        load_model(f"{tmp_path}/m.py:X")
