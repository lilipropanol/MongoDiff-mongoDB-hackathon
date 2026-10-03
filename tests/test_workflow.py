from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field, field_validator

from schema_guard import server
from schema_guard.demo import matches_schema
from schema_guard.translator import SchemaTranslator


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("GUARD_REPORT_DIR", str(tmp_path))
    monkeypatch.delenv("MONGODB_URI", raising=False)
    server.sessions.clear()
    server.plans.clear()
    return TestClient(server.app)


def test_optional_and_alias_contract():
    class Example(BaseModel):
        id: str = Field(alias="_id")
        nullable_but_required: int | None
        defaulted: int | None = None
        tags: list[str]

    schema = SchemaTranslator().translate(Example)
    assert schema["required"] == ["_id", "nullable_but_required", "tags"]
    assert schema["properties"]["nullable_but_required"]["bsonType"] == ["int", "long", "null"]
    assert not matches_schema({"_id": "x", "tags": ["a"]}, schema)
    assert matches_schema({"_id": "x", "tags": ["a"], "nullable_but_required": None}, schema)
    assert not matches_schema({"_id": "x", "tags": [9], "nullable_but_required": 1}, schema)


def test_unsupported_constraints_are_explicit():
    class Constrained(BaseModel):
        runtime: int = Field(gt=0)

    with pytest.raises(TypeError, match="Unsupported constraints"):
        SchemaTranslator().translate(Constrained)

    class Custom(BaseModel):
        value: str

        @field_validator("value")
        @classmethod
        def validate_value(cls, value):
            return value

    with pytest.raises(TypeError, match="Unsupported custom validator"):
        SchemaTranslator().translate(Custom)


def test_demo_repair_and_rescan(client):
    session = str(uuid4())
    initial = client.post("/api/analyze", json={"session_id": session, "source": "demo"}).json()
    assert (initial["total_docs"], initial["failing"], initial["preexisting"], initial["newly_failing"]) == (12, 7, 2, 5)
    reasons = {(r["field"], r["reason"]): r["count"] for r in initial["reasons"]}
    assert reasons[("runtime", "wrong_type")] == 2
    assert reasons[("rated", "missing")] == 2
    assert sum(reasons.values()) > initial["failing"]  # A document has multiple issues.
    for reason in initial["reasons"]:
        for doc in reason["examples"]:
            assert set(doc) <= {"_id", reason["field"]}

    decisions = {"session_id": session, "defaults": {"rated": "PG", "runtime": 90}, "mappings": {}}
    plan = client.post(f"/api/runs/{initial['id']}/plan", json=decisions).json()
    mechanical = client.post("/api/demo/apply", json={"session_id": session, "plan_id": plan["id"]}).json()
    assert mechanical["failing"] == 2  # N/A and enum outliers survive.

    decisions["mappings"] = {"runtime": {"N/A": 90}, "rated": {"PG13": "PG-13", "NR": "PG"}}
    plan = client.post(f"/api/runs/{mechanical['id']}/plan", json=decisions).json()
    repaired = client.post("/api/demo/apply", json={"session_id": session, "plan_id": plan["id"]}).json()
    assert repaired["failing"] == 0
    assert repaired["reasons"] == []
    history = client.get("/api/runs", params={"session_id": session}).json()
    assert len(history) == 3
    assert history[0]["id"] == repaired["id"]
    reset = client.post("/api/demo/reset", json={"session_id": session}).json()
    assert reset["failing"] == 7


def test_invalid_decisions_and_stale_plan(client):
    session = str(uuid4())
    report = client.post("/api/analyze", json={"session_id": session}).json()
    path = f"/api/runs/{report['id']}/plan"
    invalid = client.post(path, json={"session_id": session, "defaults": {"rated": "INVALID"}})
    assert invalid.status_code == 422
    plan = client.post(path, json={"session_id": session, "defaults": {"rated": "PG"}}).json()
    client.post("/api/analyze", json={"session_id": session})
    assert client.post("/api/demo/apply", json={"session_id": session, "plan_id": plan["id"]}).status_code == 409
    assert client.post(path, json={"session_id": str(uuid4())}).status_code == 404


def test_demo_restore_and_validator_preview(client):
    session = str(uuid4())
    initial = client.post("/api/analyze", json={"session_id": session, "source": "demo"}).json()
    plan = client.post(f"/api/runs/{initial['id']}/plan", json={
        "session_id": session,
        "defaults": {"rated": "PG", "runtime": 90},
        "mappings": {},
    }).json()
    applied = client.post("/api/demo/apply", json={"session_id": session, "plan_id": plan["id"]}).json()
    assert applied["demo_backup_available"] is True

    restored = client.post("/api/demo/restore", json={"session_id": session}).json()
    assert restored["failing"] == 7
    assert restored["preexisting"] == 2
    assert restored["newly_failing"] == 5

    validator = client.get("/api/validator", params={"session_id": session, "run_id": restored["id"]}).json()
    assert validator["validationAction"] == "warn"
    assert "$jsonSchema" in validator["validator"]


def test_unconfigured_atlas_is_actionable(client):
    response = client.post("/api/analyze", json={"session_id": str(uuid4()), "source": "atlas"})
    assert response.status_code == 409
    assert "MONGODB_URI" in response.json()["detail"]
