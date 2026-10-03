"""Guards that teammates' unchanged code still works with the engine's richer output.

These tests only *call* report.py, fixes.py, demo.py, server.py and the connector modules; they never modify them.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from bson import Decimal128, Int64, ObjectId
from fastapi.testclient import TestClient

from schema_guard import diff as diff_connector
from schema_guard import impact as impact_connector
from schema_guard import models as models_connector
from schema_guard import server, translator as translator_connector
from schema_guard.demo import SEED, analyze_demo
from schema_guard.engine import diff, impact, models, translator
from schema_guard.fixes import make_plan
from schema_guard.report import build_report

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = json.loads((ROOT / "tests/engine/fixtures/engine_starter_snapshot.json").read_text())

ENGINE_IMPACT = {
    "total": 4, "failing": 3, "preexisting": 1, "newly_failing": 2, "unclassified": 0,
    "reasons": [
        {"field": "rated", "reason": "value_not_allowed", "count": 2, "example_ids": ["a"], "examples": [{"_id": ObjectId(), "rated": "PG13"}],
         "path": "rated", "location": "field", "count_newly": 2, "count_preexisting": 0, "explanation": "x",
         "distinct_values": [{"value": "PG13", "bson_type": "string", "count": 2, "mappable": True}],
         "distinct_value_count": 1, "distinct_values_limited": False},
        {"field": "runtime", "reason": "wrong_type", "count": 1, "example_ids": ["b"], "examples": [{"_id": "b", "runtime": Decimal128("1.5")}],
         "path": "runtime", "location": "field", "explanation": "y",
         "distinct_values": [{"value": Decimal128("1.5"), "bson_type": "decimal", "count": 1, "mappable": False}]},
        {"field": "runtime", "reason": "missing", "count": 1, "example_ids": ["c"], "examples": [{"_id": "c"}],
         "path": "runtime", "location": "field", "explanation": "z"},
    ],
    "warnings": [{"field": "awards", "path": "awards", "kind": "missing_defaulted_field", "count": 1, "message": "m"}],
    "scan": {"duration_ms": 3, "max_time_ms": 30000, "examples": 3, "distinct_limit": 10, "two_pass": True,
             "collection_exists": True, "snapshot": False},
}


def nested_impact():
    """A report reason located deep inside a root field, as produced for nested models."""
    data = json.loads(json.dumps(ENGINE_IMPACT, default=str))
    data["reasons"].append({"field": "rated", "reason": "wrong_type", "count": 1, "example_ids": [], "examples": [],
                            "path": "rated.inner[]", "location": "array_element", "explanation": "deep"})
    return data


def test_connectors_re_export_engine_objects():
    assert translator_connector.SchemaTranslator is translator.SchemaTranslator
    assert diff_connector.compare is diff.compare
    assert impact_connector.analyze_collection is impact.analyze_collection
    assert impact_connector.reason_specs is impact.reason_specs
    assert models_connector.load_model is models.load_model


def test_build_report_keeps_existing_keys():  # U-C2
    report = build_report(ENGINE_IMPACT, [], SNAPSHOT["old_schema"], SNAPSHOT["new_schema"], "db", "movies", "atlas")
    assert (report["total_docs"], report["failing"], report["preexisting"], report["newly_failing"]) == (4, 3, 1, 2)
    assert report["reasons"] is ENGINE_IMPACT["reasons"]  # new per-reason keys flow through unchanged
    assert report["warnings"] == ENGINE_IMPACT["warnings"]
    assert report["scan"] == ENGINE_IMPACT["scan"]


def test_make_plan_accepts_engine_reasons_including_nested_paths():  # U-C1 (F1)
    report = build_report(nested_impact(), [], SNAPSHOT["old_schema"], SNAPSHOT["new_schema"], "db", "movies", "atlas")
    plan = make_plan(report, {"runtime": 90}, {"rated": {"PG13": "PG-13"}})
    kinds = {(op["field"], op["kind"]) for op in plan["operations"]}
    assert ("runtime", "default") in kinds and ("rated", "mapping") in kinds
    assert all("." not in op["field"] for op in plan["operations"])


def test_report_with_bson_values_serializes_like_the_server():  # U-C3
    impact_data = dict(ENGINE_IMPACT)
    impact_data["reasons"] = ENGINE_IMPACT["reasons"] + [{
        "field": "runtime", "reason": "wrong_type", "count": 1, "example_ids": [], "path": "runtime", "location": "field",
        "examples": [{"_id": ObjectId(), "runtime": Int64(5), "when": datetime.now(timezone.utc)}],
        "distinct_values": [{"value": datetime(2020, 1, 1), "bson_type": "date", "count": 1, "mappable": False}]}]
    report = build_report(impact_data, diff.compare(SNAPSHOT["old_schema"], SNAPSHOT["new_schema"]),
                          SNAPSHOT["old_schema"], SNAPSHOT["new_schema"], "db", "movies", "atlas")
    assert json.loads(json.dumps(report, default=str))["failing"] == 3


def test_demo_adapter_results_unchanged():  # U-C4
    result = analyze_demo(SEED, SNAPSHOT["old_schema"], SNAPSHOT["new_schema"])
    assert (result["total"], result["failing"], result["preexisting"], result["newly_failing"]) == (12, 7, 2, 5)
    assert {(r["field"], r["reason"]): r["count"] for r in result["reasons"]} == {
        ("runtime", "missing"): 1, ("runtime", "null_not_allowed"): 1, ("runtime", "wrong_type"): 2,
        ("rated", "missing"): 2, ("rated", "value_not_allowed"): 2}


def test_server_demo_flow_with_engine_diff(tmp_path, monkeypatch):
    monkeypatch.setenv("GUARD_REPORT_DIR", str(tmp_path))
    monkeypatch.delenv("MONGODB_URI", raising=False)
    monkeypatch.delenv("GUARD_SUGGESTIONS", raising=False)
    server.sessions.clear()
    server.plans.clear()
    client = TestClient(server.app)
    session = str(uuid4())
    report = client.post("/api/analyze", json={"session_id": session, "source": "demo"}).json()
    assert report["failing"] == 7
    assert all("compatibility" in change for change in report["changes"])
    plan = client.post(f"/api/runs/{report['id']}/plan", json={"session_id": session, "defaults": {"rated": "PG", "runtime": 90},
                                                               "mappings": {"runtime": {"N/A": 90}, "rated": {"PG13": "PG-13", "NR": "PG"}}}).json()
    repaired = client.post("/api/demo/apply", json={"session_id": session, "plan_id": plan["id"]}).json()
    assert repaired["failing"] == 0


def test_cli_accepts_json_schema_sources(tmp_path, monkeypatch, capsys):
    from schema_guard import cli
    output = tmp_path / "report.json"
    monkeypatch.setattr("sys.argv", ["schema-guard", "--demo", "--old", str(ROOT / "examples/engine/movie_old.schema.json"),
                                     "--new", str(ROOT / "examples/engine/movie_new.schema.json"), "--output", str(output)])
    cli.main()
    assert "7 of 12" in capsys.readouterr().out
    assert json.loads(output.read_text())["failing"] == 7
