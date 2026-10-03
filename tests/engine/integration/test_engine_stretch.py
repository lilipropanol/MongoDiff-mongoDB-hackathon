"""Stretch features on a real MongoDB: array bad values, schema versioning, real time limits, measurement tool."""

import json
from copy import deepcopy
from pathlib import Path
from typing import Literal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from pymongo.errors import ExecutionTimeout

from schema_guard import server
from schema_guard.demo import SEED
from schema_guard.engine import measure as measure_tool
from schema_guard.engine.diff import compare
from schema_guard.engine.impact import analyze_collection
from schema_guard.engine.translator import SchemaTranslator

from test_engine_mongo import NEW, OLD, ZOO, doc, reasons_by

pytestmark = pytest.mark.mongo
ROOT = Path(__file__).resolve().parents[3]
T = SchemaTranslator()


# --- Bad values for array elements ----------------------------------------------------------

def test_array_element_distinct_values(fresh_collection):
    fresh_collection.insert_many(deepcopy(ZOO) + [
        doc("x1", genres=["Drama", 1, 1, 2.5]),        # 1 appears twice in one document: counted once
        doc("x2", genres=[1, "Comedy"]),
        doc("x3", cast=[{"name": 5}, {"name": "B"}, {"name": True}]),
    ])
    reasons = reasons_by(analyze_collection(fresh_collection, NEW, []))
    genres = {(v["value"], v["bson_type"]): v["count"] for v in reasons[("genres[]", "wrong_type")]["distinct_values"]}
    assert genres == {(1, "int"): 3, (2.5, "double"): 1}  # z12, x1, x2 contain 1
    names = {(v["value"], v["bson_type"]): v["count"] for v in reasons[("cast[].name", "wrong_type")]["distinct_values"]}
    assert names == {(5, "int"): 2, (True, "bool"): 1}  # z20, x3
    for key in (("genres[]", "wrong_type"), ("cast[].name", "wrong_type")):
        assert all(v["mappable"] is False for v in reasons[key]["distinct_values"])
        assert reasons[key]["distinct_value_count"] == len(reasons[key]["distinct_values"])


def test_array_element_enum_outliers(fresh_collection):
    class M(BaseModel):
        tags: list[Literal["a", "b"]]

    fresh_collection.insert_many([{"_id": 1, "tags": ["a", "zz"]}, {"_id": 2, "tags": ["zz", "yy", "zz"]}, {"_id": 3, "tags": ["b"]}])
    reason = reasons_by(analyze_collection(fresh_collection, T.translate(M), []))[("tags[]", "value_not_allowed")]
    assert reason["count"] == 2
    assert {(v["value"], v["count"]) for v in reason["distinct_values"]} == {("zz", 2), ("yy", 1)}


def test_arrays_nested_in_arrays_do_not_offer_values(fresh_collection):
    class M(BaseModel):
        grid: list[list[int]]

    fresh_collection.insert_one({"_id": 1, "grid": [[1, "x"]]})
    reason = reasons_by(analyze_collection(fresh_collection, T.translate(M), []))[("grid[][]", "wrong_type")]
    assert "distinct_values" not in reason and reason["count"] == 1


# --- Schema versioning -----------------------------------------------------------------------

def test_per_version_breakdown(fresh_collection):
    docs = [dict(doc(f"v1-{i}", runtime="90"), schemaVersion=1) for i in range(3)]
    docs += [dict(doc(f"v2-{i}"), schemaVersion=2) for i in range(4)]
    docs += [doc("none", rated="NR")]
    fresh_collection.insert_many(docs)
    result = analyze_collection(fresh_collection, NEW, compare(OLD, NEW), old_schema=OLD)
    versioning = result["versioning"]
    assert versioning["field"] == "schemaVersion" and versioning["versioned"] is True
    rows = {row["version"]: row for row in versioning["versions"]}
    assert rows[1] == {"version": 1, "total": 3, "failing": 3, "newly_failing": 0}  # "90" also broke the old schema
    assert rows[2] == {"version": 2, "total": 4, "failing": 0, "newly_failing": 0}
    assert rows[None] == {"version": None, "total": 1, "failing": 1, "newly_failing": 1}
    assert versioning["bump_recommended"] is True
    assert "runtime" in versioning["breaking_changes"]
    assert "Bump `schemaVersion`" in versioning["message"]


def test_unversioned_collection_recommends_adding_a_version_field(fresh_collection):
    fresh_collection.insert_many(deepcopy(ZOO))
    versioning = analyze_collection(fresh_collection, NEW, compare(OLD, NEW), old_schema=OLD)["versioning"]
    assert versioning["versioned"] is False and versioning["versions"] == []
    assert versioning["bump_recommended"] is True
    assert "no `schemaVersion` field" in versioning["message"]


def test_custom_and_disabled_version_field(fresh_collection, monkeypatch):
    fresh_collection.insert_many([dict(doc("a"), v="2024-01"), dict(doc("b", runtime=None), v="2024-02")])
    result = analyze_collection(fresh_collection, NEW, [], version_field="v")
    assert {row["version"]: row["failing"] for row in result["versioning"]["versions"]} == {"2024-01": 0, "2024-02": 1}
    assert result["versioning"]["bump_recommended"] is False
    monkeypatch.setenv("GUARD_VERSION_FIELD", "")
    assert "versioning" not in analyze_collection(fresh_collection, NEW, [])
    with pytest.raises(ValueError, match="version_field"):
        analyze_collection(fresh_collection, NEW, [], version_field="a.b")


def test_versioning_same_in_two_pass_and_single_pass(fresh_collection):
    fresh_collection.insert_many([dict(doc(f"{i}", runtime="1" if i % 2 else 1), schemaVersion=i % 3) for i in range(30)])
    two = analyze_collection(fresh_collection, NEW, compare(OLD, NEW), old_schema=OLD, two_pass=True)["versioning"]
    one = analyze_collection(fresh_collection, NEW, compare(OLD, NEW), old_schema=OLD, two_pass=False)["versioning"]
    assert two == one


# --- Real time limits (server-side maxTimeMS) -----------------------------------------------

def test_scan_time_limit_is_enforced_by_the_server(fresh_collection, always_time_out):
    fresh_collection.insert_many(deepcopy(ZOO))
    with pytest.raises(ExecutionTimeout):
        analyze_collection(fresh_collection, NEW, [], max_time_ms=1000)


def test_server_turns_a_timeout_into_a_clean_502(fresh_collection, mongo_uri, tmp_path, monkeypatch, always_time_out):
    fresh_collection.insert_many(deepcopy(SEED))
    monkeypatch.setenv("MONGODB_URI", mongo_uri)
    monkeypatch.setenv("MONGODB_DATABASE", fresh_collection.database.name)
    monkeypatch.setenv("MONGODB_COLLECTION", fresh_collection.name)
    monkeypatch.setenv("GUARD_REPORT_DIR", str(tmp_path))
    response = TestClient(server.app).post("/api/analyze", json={"session_id": str(uuid4()), "source": "atlas"})
    assert response.status_code == 502
    assert "30-second" in response.json()["detail"]
    assert mongo_uri not in response.text


# --- Measurement tool ------------------------------------------------------------------------

def test_measure_all_checks_pass_on_the_zoo(fresh_collection):
    fresh_collection.insert_many(deepcopy(ZOO))
    measurement = measure_tool.measure(fresh_collection, OLD, NEW, runs=3)
    assert measurement["all_checks_passed"], measurement["checks"]
    assert len(measurement["checks"]) == 9 and measurement["runs"] == 3
    assert measurement["result"]["failing"] == 22
    assert measurement["server_version"]
    assert measurement["current_validator"]["exists"] is True
    text = measure_tool.summary(measurement)
    assert "22 of 28 documents" in text and "[FAIL]" not in text


def test_measure_detects_a_wrong_count(fresh_collection, monkeypatch):
    fresh_collection.insert_many(deepcopy(ZOO))
    real = measure_tool.analyze_collection

    def off_by_one(*args, **kwargs):
        result = real(*args, **kwargs)
        result["failing"] += 1
        return result

    monkeypatch.setattr(measure_tool, "analyze_collection", off_by_one)
    measurement = measure_tool.measure(fresh_collection, OLD, NEW, runs=1)
    failed = [c["check"] for c in measurement["checks"] if not c["passed"]]
    assert failed == ["failing == count_documents($nor new schema)"]
    assert measurement["all_checks_passed"] is False


def test_measure_detects_non_reproducible_counts(fresh_collection, monkeypatch):
    fresh_collection.insert_many(deepcopy(ZOO))
    real = measure_tool.analyze_collection
    calls = []

    def drifting(*args, **kwargs):
        calls.append(1)
        result = real(*args, **kwargs)
        result["total"] += len(calls) - 1  # simulates concurrent writes between runs
        return result

    monkeypatch.setattr(measure_tool, "analyze_collection", drifting)
    checks = {c["check"]: c["passed"] for c in measure_tool.measure(fresh_collection, OLD, NEW, runs=2)["checks"]}
    assert checks["reproducible across runs"] is False


def test_measure_command_line_is_read_only_and_never_saves_the_uri(fresh_collection, mongo_uri, tmp_path, monkeypatch, capsys):
    fresh_collection.insert_many(deepcopy(ZOO))
    before = list(fresh_collection.find().sort("_id"))
    monkeypatch.setenv("MONGODB_URI", mongo_uri)
    out = tmp_path / "m.json"
    code = measure_tool.main(["--database", fresh_collection.database.name, "--collection", fresh_collection.name,
                              "--old", str(ROOT / "examples/engine/movie_old.schema.json"),
                              "--new", str(ROOT / "examples/engine/movie_new.schema.json"), "--out", str(out)])
    printed = capsys.readouterr().out
    assert code == 0, printed
    assert list(fresh_collection.find().sort("_id")) == before
    saved = out.read_text()
    assert mongo_uri not in saved and mongo_uri not in printed
    assert json.loads(saved)["all_checks_passed"] is True
    assert "PASS" in printed


def test_measure_command_line_reports_connection_problems(monkeypatch, capsys):
    monkeypatch.setenv("MONGODB_URI", "mongodb://127.0.0.1:1/?serverSelectionTimeoutMS=200&directConnection=true")
    assert measure_tool.main(["--runs", "1"]) == 2
    assert "MongoDB request failed" in capsys.readouterr().err
