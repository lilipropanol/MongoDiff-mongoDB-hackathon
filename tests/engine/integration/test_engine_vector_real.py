"""Atlas Vector Search mode against real servers.

Local mongod (Community, no Atlas Search): proves the write boundary (only the named vocabulary collection
is written, never the scanned one) and the clean fallback. Live Atlas: opt-in, proves real $vectorSearch.
"""

import os
from copy import deepcopy
from uuid import uuid4

import pytest
from pymongo import MongoClient

from schema_guard.engine import suggest
from schema_guard.engine.impact import analyze_collection
from schema_guard.engine.vector_search import INDEX_NAME

from test_engine_mongo import NEW, OLD, ZOO, reasons_by

pytestmark = pytest.mark.mongo


def fake_voyage(url, payload, api_key, timeout):
    """Deterministic 3-d embeddings: PG13 ≈ PG-13, unrelated values point elsewhere."""
    def vec(text):
        value = text.split(":", 1)[-1].strip().lower().replace("-", "")
        return {"pg13": [1, 0, 0], "pg": [0.8, 0.6, 0], "g": [0, 1, 0], "r": [0, 0, 1]}.get(value, [-0.5, -0.5, 0.7])
    return {"data": [{"index": i, "embedding": vec(t)} for i, t in enumerate(payload["input"])]}


def test_local_mongodb_writes_only_the_vocabulary_and_falls_back(fresh_collection, mongo_client, monkeypatch):
    fresh_collection.insert_many(deepcopy(ZOO))
    before = list(fresh_collection.find().sort("_id"))
    vocab_db, vocab_name = "schema_guard_it", f"vocab_{uuid4().hex[:8]}"
    monkeypatch.setattr(suggest, "post_json", fake_voyage)
    monkeypatch.setenv("GUARD_SUGGESTIONS", "atlas-vector")
    monkeypatch.setenv("VOYAGE_API_KEY", "test-key")
    monkeypatch.setenv("GUARD_VECTOR_COLLECTION", f"{vocab_db}.{vocab_name}")
    try:
        result = analyze_collection(fresh_collection, NEW, [], old_schema=OLD)
        status = result["scan"]["suggestions"]
        # Community mongod has no Atlas Search, so $listSearchIndexes fails and we fall back cleanly.
        assert status["status"] == "fallback" and "OperationFailure" in status["fallback_reason"]
        assert status["method"] == "voyage-embed"
        rated = {v["value"]: v["suggestions"] for v in reasons_by(result)[("rated", "value_not_allowed")]["distinct_values"]}
        assert rated["PG13"][0]["target"] == "PG-13"
        # Write boundary: the scanned collection is untouched; the vocabulary holds only allowed values.
        assert list(fresh_collection.find().sort("_id")) == before
        vocab = list(mongo_client[vocab_db][vocab_name].find({}, {"_id": 0, "text": 1, "group": 1}))
        assert sorted(d["text"] for d in vocab) == ["rated value: G", "rated value: PG", "rated value: PG-13", "rated value: R"]
        assert {d["group"] for d in vocab} == {"rated"}
    finally:
        mongo_client[vocab_db].drop_collection(vocab_name)


def test_local_mongodb_refuses_to_use_the_scanned_collection(fresh_collection, monkeypatch):
    fresh_collection.insert_many(deepcopy(ZOO))
    before = list(fresh_collection.find().sort("_id"))
    monkeypatch.setattr(suggest, "post_json", fake_voyage)
    monkeypatch.setenv("GUARD_SUGGESTIONS", "atlas-vector")
    monkeypatch.setenv("VOYAGE_API_KEY", "test-key")
    monkeypatch.setenv("GUARD_VECTOR_COLLECTION", f"{fresh_collection.database.name}.{fresh_collection.name}")
    result = analyze_collection(fresh_collection, NEW, [])
    assert "must not be the collection being scanned" in result["scan"]["suggestions"]["fallback_reason"]
    assert list(fresh_collection.find().sort("_id")) == before


@pytest.mark.skipif(not (os.getenv("SCHEMA_GUARD_ATLAS_VECTOR_URI") and os.getenv("VOYAGE_API_KEY")),
                    reason="live Atlas Vector Search: set SCHEMA_GUARD_ATLAS_VECTOR_URI (disposable Atlas cluster) and VOYAGE_API_KEY")
def test_live_atlas_vector_search(monkeypatch):  # Person 3 runs this against a disposable Atlas database
    client = MongoClient(os.environ["SCHEMA_GUARD_ATLAS_VECTOR_URI"], serverSelectionTimeoutMS=10000)
    database = f"schema_guard_it_vectors_{uuid4().hex[:8]}"
    data = client[database]["movies"]
    try:
        data.insert_many(deepcopy(ZOO))
        monkeypatch.setenv("GUARD_SUGGESTIONS", "atlas-vector")
        monkeypatch.setenv("GUARD_VECTOR_COLLECTION", f"{database}.vocab")
        monkeypatch.setenv("GUARD_VECTOR_INDEX_WAIT", "180")
        result = analyze_collection(data, NEW, [], old_schema=OLD)
        status = result["scan"]["suggestions"]
        assert status["status"] == "ok", status
        assert status["method"] == "atlas-vector-search" and status["index"] == INDEX_NAME
        rated = {v["value"]: v["suggestions"] for v in reasons_by(result)[("rated", "value_not_allowed")]["distinct_values"]}
        assert rated["PG13"] and rated["PG13"][0]["target"] == "PG-13"
        assert any(s["source"] == "atlas-vector-search" for s in rated["PG13"])
    finally:
        client.drop_database(database)
        client.close()
