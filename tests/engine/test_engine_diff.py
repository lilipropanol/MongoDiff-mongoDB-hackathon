"""Schema diff: root entries unchanged from the starter, nested paths, details and compatibility labels."""

import json
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel

from schema_guard.engine.diff import compare
from schema_guard.engine.translator import SchemaTranslator

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = json.loads((ROOT / "tests/engine/fixtures/engine_starter_snapshot.json").read_text())
NEW_KEYS = {"details", "compatibility", "compatibility_reason", "parent"}


def t(model):
    return SchemaTranslator().translate(model)


def by(changes, field, kind):
    found = [c for c in changes if c["field"] == field and c["kind"] == kind]
    assert len(found) == 1, f"expected one {kind} at {field}, got {changes}"
    return found[0]


def test_starter_root_entries_keep_their_shape():  # U-D1
    changes = compare(SNAPSHOT["old_schema"], SNAPSHOT["new_schema"])
    stripped = [{k: v for k, v in c.items() if k not in NEW_KEYS} for c in changes]
    assert stripped == SNAPSHOT["changes"]


class ImdbOld(BaseModel):
    rating: float
    votes: int
    id: Optional[int] = None


class ImdbNew(BaseModel):
    rating: str
    votes: Optional[int] = None
    id: int
    source: str


class Cast(BaseModel):
    name: str


class CastNew(BaseModel):
    name: int


class Old(BaseModel):
    imdb: ImdbOld
    genres: list[str]
    cast: list[Cast]
    rated: Literal["G", "PG", "R"]
    runtime: Optional[int]
    legacy: str
    shape: ImdbOld


class New(BaseModel):
    imdb: ImdbNew
    genres: list[int]
    cast: list[CastNew]
    rated: Literal["G", "PG", "PG-13"]
    runtime: int
    shape: str
    added_optional: Optional[str] = None


CHANGES = compare(t(Old), t(New))


def test_nested_field_type_change_has_path_and_parent():  # U-D2
    change = by(CHANGES, "imdb.rating", "type_or_constraint_changed")
    assert change["parent"] == "imdb"
    assert change["details"]["types_added"] == ["string"]
    assert set(change["details"]["types_removed"]) == {"double", "int", "long", "decimal"}
    assert by(CHANGES, "imdb.source", "added")["parent"] == "imdb"


def test_nested_required_changes():  # U-D3
    assert by(CHANGES, "imdb.id", "became_required")["parent"] == "imdb"
    assert by(CHANGES, "imdb.votes", "became_optional")["compatibility"] == "compatible"


def test_array_element_change():  # U-D4
    change = by(CHANGES, "genres[]", "type_or_constraint_changed")
    assert change["parent"] == "genres"
    assert change["details"]["types_added"] == ["int", "long"]
    assert change["details"]["types_removed"] == ["string"]


def test_field_inside_array_of_models():  # U-D5
    change = by(CHANGES, "cast[].name", "type_or_constraint_changed")
    assert change["parent"] == "cast"


def test_enum_added_and_removed():  # U-D6
    details = by(CHANGES, "rated", "type_or_constraint_changed")["details"]
    assert details["enum_added"] == ["PG-13"]
    assert details["enum_removed"] == ["R"]


def test_nullability_change():  # U-D7
    change = by(CHANGES, "runtime", "type_or_constraint_changed")
    assert change["details"]["nullable"] == {"old": True, "new": False}
    assert change["compatibility"] == "breaking"


def test_object_replaced_by_scalar_does_not_recurse():  # U-D8
    change = by(CHANGES, "shape", "type_or_constraint_changed")
    assert "parent" not in change
    assert not any(c["field"].startswith("shape.") for c in CHANGES)


def test_identical_schemas_have_no_changes():  # U-D9
    assert compare(t(Old), t(Old)) == []


def test_bool_and_number_enum_values_are_different():
    # Python says True == 1; MongoDB does not. This change must not be missed.
    changes = compare({"properties": {"x": {"enum": [1]}}}, {"properties": {"x": {"enum": [True]}}})
    assert changes[0]["details"] == {"enum_added": [True], "enum_removed": [1]}


def test_int_and_double_enum_values_are_the_same_number():
    # MongoDB compares numbers by value, so 1 → 1.0 is not a stored-data change.
    assert compare({"properties": {"x": {"enum": [1]}}}, {"properties": {"x": {"enum": [1.0]}}}) == []


def test_restricting_to_enum_and_lifting_enum():
    to_enum = compare({"properties": {"x": {"bsonType": "string"}}}, {"properties": {"x": {"enum": ["a"]}}})[0]
    lifted = compare({"properties": {"x": {"enum": ["a"]}}}, {"properties": {"x": {"bsonType": "string"}}})[0]
    assert to_enum["details"]["restricted_to"] == ["a"] and to_enum["compatibility"] == "breaking"
    assert lifted["details"]["enum_lifted"] is True and lifted["compatibility"] == "compatible"


def test_compatibility_labels_follow_schema_versioning_rules():
    assert by(CHANGES, "added_optional", "added")["compatibility"] == "compatible"
    assert by(CHANGES, "legacy", "removed")["compatibility"] == "breaking"
    assert by(CHANGES, "imdb.source", "added")["compatibility"] == "breaking"  # new required field needs a backfill
    assert by(CHANGES, "imdb.id", "became_required")["compatibility"] == "breaking"
    widened = compare({"properties": {"x": {"bsonType": ["int", "long"]}}},
                      {"properties": {"x": {"bsonType": ["int", "long", "null"]}}})[0]
    assert widened["compatibility"] == "compatible"
    assert all(c["compatibility_reason"] for c in CHANGES)


def test_every_change_has_a_compatibility_label():
    assert {c["compatibility"] for c in CHANGES} <= {"breaking", "compatible"}
