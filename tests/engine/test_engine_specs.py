"""Reason, nested-reason and warning generation (no database needed)."""

import json
from pathlib import Path
from typing import Literal, Optional

import pytest
from pydantic import BaseModel

from schema_guard.engine.impact import (analyze_collection, deep_reason_specs, explain, reason_specs,
                                        summarize_values, warning_specs)
from schema_guard.engine.translator import SchemaTranslator

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = json.loads((ROOT / "tests/engine/fixtures/engine_starter_snapshot.json").read_text())


class Imdb(BaseModel):
    rating: float
    votes: Optional[int] = None


class Person(BaseModel):
    name: str
    roles: list[Literal["actor", "director"]]


class Movie(BaseModel):
    title: str
    imdb: Imdb
    genres: list[str]
    cast: list[Person]
    grid: list[list[int]]
    awards: Optional[str] = None


SCHEMA = SchemaTranslator().translate(Movie)
DEEP = deep_reason_specs(SCHEMA)


def keys(specs):
    return {(s["field"], s["path"], s["location"], s["reason"]) for s in specs}


def test_root_reason_specs_unchanged_for_starter_schemas():  # U-R1 (protects demo.py)
    assert reason_specs(SNAPSHOT["new_schema"]) == SNAPSHOT["reason_specs_new"]
    assert reason_specs(SNAPSHOT["old_schema"]) == SNAPSHOT["reason_specs_old"]


def test_root_reason_specs_never_contain_nested_paths():
    assert all("." not in s["field"] and "[]" not in s["field"] for s in reason_specs(SCHEMA))


def test_deep_specs_paths_and_locations():  # U-R2
    assert keys(DEEP) == {
        ("imdb", "imdb.rating", "nested", "missing"),
        ("imdb", "imdb.rating", "nested", "null_not_allowed"),
        ("imdb", "imdb.rating", "nested", "wrong_type"),
        ("imdb", "imdb.votes", "nested", "wrong_type"),
        ("genres", "genres[]", "array_element", "null_not_allowed"),
        ("genres", "genres[]", "array_element", "wrong_type"),
        ("cast", "cast[]", "array_element", "null_not_allowed"),
        ("cast", "cast[]", "array_element", "wrong_type"),
        ("cast", "cast[].name", "array_element", "missing"),
        ("cast", "cast[].name", "array_element", "null_not_allowed"),
        ("cast", "cast[].name", "array_element", "wrong_type"),
        ("cast", "cast[].roles", "array_element", "missing"),
        ("cast", "cast[].roles", "array_element", "null_not_allowed"),
        ("cast", "cast[].roles", "array_element", "wrong_type"),
        ("cast", "cast[].roles[]", "array_element", "null_not_allowed"),
        ("cast", "cast[].roles[]", "array_element", "value_not_allowed"),
        ("grid", "grid[]", "array_element", "null_not_allowed"),
        ("grid", "grid[]", "array_element", "wrong_type"),
        ("grid", "grid[][]", "array_element", "null_not_allowed"),
        ("grid", "grid[][]", "array_element", "wrong_type"),
    }


def test_every_deep_spec_field_is_a_root_property():
    assert {s["field"] for s in DEEP} <= set(SCHEMA["properties"])


def _walk(node, found):
    if isinstance(node, dict):
        for key, value in node.items():
            found.append(key)
            _walk(value, found)
    elif isinstance(node, list):
        for item in node:
            _walk(item, found)


def test_deep_specs_use_only_aggregation_expressions():  # U-R3
    query_only = {"$exists", "$elemMatch", "$jsonSchema", "$nor", "$size", "$all", "$regex"}
    for spec in DEEP:
        found = []
        _walk(spec["expr"], found)
        assert not set(found) & query_only, spec["path"]


def test_nested_arrays_use_distinct_variables():  # U-R4
    spec = next(s for s in DEEP if s["path"] == "grid[][]" and s["reason"] == "wrong_type")
    text = json.dumps(spec["expr"])
    assert '"as": "e0"' in text and '"as": "e1"' in text
    assert "$$e1" in text


def test_nested_object_checks_are_guarded_by_parent_type():
    spec = next(s for s in DEEP if s["path"] == "imdb.rating" and s["reason"] == "missing")
    assert {"$eq": [{"$type": "$imdb"}, "object"]} in spec["expr"]["$and"]


def test_distinct_values_only_for_scalar_positions_outside_arrays():
    with_values = {(s["path"], s["reason"]) for s in DEEP if s["value"]}
    assert with_values == {("imdb.rating", "wrong_type"), ("imdb.votes", "wrong_type")}


def test_enum_values_are_literal_in_expressions():
    spec = next(s for s in DEEP if s["path"] == "cast[].roles[]" and s["reason"] == "value_not_allowed")
    assert {"$literal": ["actor", "director"]} in json.loads(json.dumps(spec["expr"]))["$anyElementTrue"][0]["$map"]["in"]["$anyElementTrue"][0]["$map"]["in"]["$and"][1]["$not"][0]["$in"]


def test_warning_specs_cover_optional_root_and_nested_fields():
    paths = {w["path"]: w for w in warning_specs(SCHEMA)}
    assert set(paths) == {"imdb.votes", "awards"}
    assert paths["imdb.votes"]["field"] == "imdb"
    assert paths["awards"]["expr"] == {"$eq": [{"$type": "$awards"}, "missing"]}


@pytest.mark.parametrize("kwargs, message", [
    ({"examples": 6}, "examples"),
    ({"examples": -1}, "examples"),
    ({"distinct_limit": -1}, "distinct_limit"),
    ({"distinct_limit": 51}, "distinct_limit"),
    ({"max_time_ms": 0}, "max_time_ms"),
    ({"max_time_ms": 60001}, "max_time_ms"),
])
def test_limits_are_validated(kwargs, message):  # U-R5
    with pytest.raises(ValueError, match=message):
        analyze_collection(None, SCHEMA, [], **kwargs)


class FakeCollection:
    """Records aggregate calls; returns empty facet results."""
    name = "movies"

    def __init__(self):
        self.calls = []

    def aggregate(self, pipeline, **kwargs):
        self.calls.append((pipeline, kwargs))
        return iter([{}])


def test_max_time_ms_is_passed_to_every_aggregate():
    collection = FakeCollection()
    result = analyze_collection(collection, SCHEMA, [], max_time_ms=1234)
    assert [kwargs for _, kwargs in collection.calls] == [{"maxTimeMS": 1234}, {"maxTimeMS": 1234}]
    assert result["scan"]["max_time_ms"] == 1234
    assert result["scan"]["collection_exists"] is None  # unknown without listCollections


def test_two_pass_filters_failing_documents_first():
    collection = FakeCollection()
    analyze_collection(collection, SCHEMA, [])
    first, second = (pipeline for pipeline, _ in collection.calls)
    assert list(first[0]) == ["$facet"]
    assert second[0] == {"$match": {"$nor": [{"$jsonSchema": SCHEMA}]}}


def test_single_pass_runs_one_aggregate():
    collection = FakeCollection()
    analyze_collection(collection, SCHEMA, [], two_pass=False)
    assert len(collection.calls) == 1


def test_explanations_mention_strict_bson_vs_pydantic():
    rule = {"bsonType": ["int", "long"]}
    text = explain("wrong_type", "runtime", rule, [{"bson_type": "string"}, {"bson_type": "double"}, {"bson_type": "array"}])
    assert "strictly" in text and "Pydantic" in text and "90.0" in text and "array" in text
    assert "outside the allowed set ('G', 'PG')" in explain("value_not_allowed", "rated", {"enum": ["G", "PG", None]})
    for reason in ("missing", "null_not_allowed", "nested_or_array_constraint"):
        assert "runtime" in explain(reason, "runtime", rule)


def test_summarize_values_matches_facet_shape():
    summary = summarize_values(["118", "118", "N/A", 1, "1", None, [1], {"a": 1}, "x" * 100], limit=4)
    values = summary["distinct_values"]
    assert values[0] == {"value": "118", "bson_type": "string", "count": 2, "mappable": True}
    assert summary["distinct_value_count"] == 8
    assert summary["distinct_values_limited"] is True
    assert len(values) == 4
    full = summarize_values(["x" * 100, [1], 1, "1"], limit=10)["distinct_values"]
    text = next(v for v in full if v["bson_type"] == "string" and v.get("truncated"))
    assert len(text["value"]) == 80
    assert next(v for v in full if v["bson_type"] == "array")["value"] is None
    assert {(v["value"], v["bson_type"]) for v in full} >= {(1, "int"), ("1", "string")}
    assert summarize_values(["a"], location="nested")["distinct_values"][0]["mappable"] is False
