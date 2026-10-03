"""MongoDB Atlas Vector Search suggestions (GUARD_SUGGESTIONS=atlas-vector) with fake Atlas and Voyage."""

import copy
import json

import pytest
from pymongo.errors import OperationFailure

from schema_guard.engine import suggest, vector_search
from schema_guard.engine.vector_search import INDEX_NAME, index_definition, vector_search_pipeline, vector_namespace
from schema_guard.fixes import make_plan

SCHEMA = {"bsonType": "object", "properties": {"rated": {"enum": ["G", "PG", "PG-13", "R"]}}}
ANCHORS = {"pg13": [1.0, 0.0, 0.0], "pg": [0.8, 0.6, 0.0], "g": [0.0, 1.0, 0.0], "r": [0.0, 0.0, 1.0],
           "notrated": [-0.6, -0.6, 0.53],"runtime": [0.0, 0.7, 0.7], "durationminutes": [0.0, 0.7, 0.7]}


def key(text):
    return text.split(":", 1)[-1].split("(")[0].replace("field", "").strip().lower().replace("-", "").replace(" ", "").replace("_", "")


class FakeVoyage:
    def __init__(self, fail=None):
        self.calls, self.fail = [], fail

    def __call__(self, url, payload, api_key, timeout):
        self.calls.append({"url": url, "payload": copy.deepcopy(payload)})
        if self.fail:
            raise self.fail
        return {"data": [{"index": i, "embedding": ANCHORS.get(key(t), [0.3, 0.3, 0.3])} for i, t in enumerate(payload["input"])]}


class FakeTarget:
    """A fake Atlas collection with search-index commands and an in-process $vectorSearch."""

    def __init__(self, database, name, queryable_after=0, index_dims=None, fail_search=False):
        self.database, self.name = database, name
        self.docs, self.indexes, self.pipelines, self.created = {}, [], [], []
        self.polls_left, self.fail_search = queryable_after, fail_search
        if index_dims:
            self.indexes.append({"name": INDEX_NAME, "queryable": True,
                                 "latestDefinition": index_definition(index_dims)})

    def bulk_write(self, operations, ordered=False):
        upserted = 0
        for op in operations:
            doc_id = op._filter["_id"]
            if doc_id not in self.docs:
                self.docs[doc_id] = {"_id": doc_id, **op._doc["$setOnInsert"]}
                upserted += 1
        return type("Result", (), {"upserted_count": upserted})()

    def list_search_indexes(self, name=None):
        if self.fail_search:
            raise OperationFailure("$listSearchIndexes requires Atlas Search")
        for index in self.indexes:
            if not index["queryable"]:
                if self.polls_left <= 0:
                    index["queryable"] = True
                self.polls_left -= 1
        return iter([i for i in self.indexes if name in (None, i["name"])])

    def create_search_index(self, model):
        document = model.document
        self.created.append(document)
        self.indexes.append({"name": document["name"], "queryable": self.polls_left <= 0, "latestDefinition": document["definition"]})
        return document["name"]

    def aggregate(self, pipeline):
        self.pipelines.append(pipeline)
        stage = pipeline[0]["$vectorSearch"]
        hits = []
        for doc in self.docs.values():
            if all(doc.get(k) == v for k, v in stage["filter"].items()):
                cos = suggest._cosine(stage["queryVector"], doc["embedding"])
                hits.append({"text": doc["text"], "score": (1 + cos) / 2})
        return iter(sorted(hits, key=lambda h: -h["score"])[:stage["limit"]])


class FakeClient:
    def __init__(self):
        self.collections = {}
        self.target_kwargs = {}

    def __getitem__(self, database):
        client = self

        class Database:
            name = database

            def __getitem__(self, collection):
                full = (database, collection)
                if full not in client.collections:
                    client.collections[full] = FakeTarget(self, collection, **client.target_kwargs)
                return client.collections[full]

        db = Database()
        db.client = self
        return db


def scanned(client=None, database="sample_mflix", name="movies"):
    client = client or FakeClient()
    db = client[database]
    return type("Scanned", (), {"name": name, "database": db})()


ENV = {"GUARD_SUGGESTIONS": "atlas-vector", "VOYAGE_API_KEY": "k", "GUARD_VECTOR_COLLECTION": "schema_guard.vocab",
       "GUARD_VECTOR_INDEX_WAIT": "5"}


def report():
    values = [{"value": v, "bson_type": "string", "count": n, "mappable": True} for v, n in (("PG13", 3), ("NOT RATED", 1))]
    return {"id": "r", "database": "sample_mflix", "collection": "movies", "source": "atlas", "new_schema": SCHEMA,
            "total_docs": 9, "failing": 4, "preexisting": 0, "newly_failing": 4, "unclassified": 0, "scan": {},
            "reasons": [{"field": "rated", "reason": "value_not_allowed", "count": 4, "path": "rated", "location": "field",
                         "example_ids": ["movie-001"], "examples": [{"_id": "movie-001", "rated": "PG13"}], "distinct_values": values}]}


def run(env=ENV, collection="default", transport=None, changes=None, monkeypatch=None):
    collection = scanned() if collection == "default" else collection
    result = report()
    if monkeypatch:
        monkeypatch.setattr(vector_search.AtlasVectorSearch, "__init__", _fast_init(vector_search.AtlasVectorSearch.__init__))
    suggest.maybe_enrich(result, SCHEMA, changes or [], env=env, transport=transport or FakeVoyage(), collection=collection)
    return result, collection


def _fast_init(original):
    def init(self, env, transport, scanned_collection, sleep=None, clock=None):
        ticks = iter(range(10_000))
        original(self, env, transport, scanned_collection, sleep=lambda s: None, clock=lambda: next(ticks))
    return init


def target_of(collection, database="schema_guard", name="vocab"):
    return collection.database.client.collections.get((database, name))


# --- Happy path: real $vectorSearch flow ------------------------------------------------------

def test_vector_search_end_to_end(monkeypatch):
    result, collection = run(monkeypatch=monkeypatch)
    target = target_of(collection)
    # Vocabulary documents: only allowed values, never bad values, ids or examples.
    texts = sorted(d["text"] for d in target.docs.values())
    assert texts == ["rated value: G", "rated value: PG", "rated value: PG-13", "rated value: R"]
    stored = json.dumps([{k: v for k, v in d.items() if k != "created_at"} for d in target.docs.values()])
    for secret in ("PG13", "NOT RATED", "movie-001"):
        assert f'"{secret}"' not in stored and f": {secret}\"" not in stored
    assert all(d["group"] == "rated" and d["model"] == "voyage-4-lite" and d["dimensions"] == 3 for d in target.docs.values())
    # Index: vectorSearch type, cosine, pre-filter fields.
    assert target.created == [{"name": INDEX_NAME, "type": "vectorSearch", "definition": index_definition(3)}]
    # Query: $vectorSearch first, pre-filtered, numCandidates >= 20x limit and >= 100.
    stage = target.pipelines[0][0]["$vectorSearch"]
    assert list(target.pipelines[0][0]) == ["$vectorSearch"]
    assert stage["filter"] == {"group": "rated", "model": "voyage-4-lite"}
    assert stage["limit"] == 4 and stage["numCandidates"] == 100 and stage["path"] == "embedding" and stage["index"] == INDEX_NAME
    assert target.pipelines[0][1] == {"$project": {"_id": 0, "text": 1, "score": {"$meta": "vectorSearchScore"}}}
    suggestions = {v["value"]: v["suggestions"] for v in result["reasons"][0]["distinct_values"]}
    assert suggestions["PG13"][0]["target"] == "PG-13"
    assert suggestions["PG13"][0]["source"] in ("atlas-vector-search", "lexical")
    assert any(s["source"] == "atlas-vector-search" for s in suggestions["PG13"])
    assert suggestions["NOT RATED"] == []
    status = result["scan"]["suggestions"]
    assert status["status"] == "ok" and status["method"] == "atlas-vector-search"
    assert status["vector_collection"] == "schema_guard.vocab" and status["index"] == INDEX_NAME
    assert status["vectors_upserted"] == 4 and status["semantic_jobs"] == {"scored": 2, "total": 2}


def test_scores_are_converted_back_to_cosine(monkeypatch):
    result, _ = run(monkeypatch=monkeypatch)
    pg = next(s for s in result["reasons"][0]["distinct_values"][0]["suggestions"] if s["target"] == "PG")
    assert pg["score"] == pytest.approx(0.8, abs=0.001)  # cos([1,0,0],[0.8,0.6,0]) = 0.8, not (1+0.8)/2


def test_index_is_created_once_and_upserts_are_idempotent(monkeypatch):
    client = FakeClient()
    first, collection = run(collection=scanned(client), monkeypatch=monkeypatch)
    second, _ = run(collection=collection, monkeypatch=monkeypatch)
    target = target_of(collection)
    assert len(target.created) == 1 and len(target.docs) == 4
    assert second["scan"]["suggestions"]["vectors_upserted"] == 0


def test_waits_for_index_to_become_queryable(monkeypatch):
    client = FakeClient()
    client.target_kwargs = {"queryable_after": 3}
    result, _ = run(collection=scanned(client), monkeypatch=monkeypatch)
    assert result["scan"]["suggestions"]["method"] == "atlas-vector-search"


def test_one_voyage_call_for_everything(monkeypatch):
    voyage = FakeVoyage()
    run(transport=voyage, monkeypatch=monkeypatch)
    assert len(voyage.calls) == 1 and voyage.calls[0]["url"].endswith("/embeddings")


def test_renames_use_in_memory_vectors(monkeypatch):
    changes = [{"field": "runtime", "kind": "removed", "old": {"bsonType": "int"}},
               {"field": "duration_minutes", "kind": "added", "new": {"bsonType": "int"}, "required": True}]
    run(changes=changes, monkeypatch=monkeypatch)
    assert changes[0]["rename_candidates"][0] == {"to": "duration_minutes", "score": 1.0, "source": "voyage-embed"}


def test_suggestions_never_change_counts_or_plans(monkeypatch):
    plain = report()
    enriched, _ = run(monkeypatch=monkeypatch)
    assert [r["count"] for r in plain["reasons"]] == [r["count"] for r in enriched["reasons"]]
    assert make_plan(plain, {}, {"rated": {"PG13": "PG-13"}})["operations"] == make_plan(enriched, {}, {"rated": {"PG13": "PG-13"}})["operations"]


# --- Safety and fallbacks ---------------------------------------------------------------------

def test_no_vector_collection_means_no_writes(monkeypatch):
    env = {k: v for k, v in ENV.items() if k != "GUARD_VECTOR_COLLECTION"}
    result, collection = run(env=env, monkeypatch=monkeypatch)
    assert collection.database.client.collections == {}
    status = result["scan"]["suggestions"]
    assert status["status"] == "fallback" and "GUARD_VECTOR_COLLECTION" in status["fallback_reason"]
    assert status["method"] == "voyage-embed"
    assert result["reasons"][0]["distinct_values"][0]["suggestions"][0]["target"] == "PG-13"


def test_refuses_to_write_into_the_scanned_collection(monkeypatch):
    env = {**ENV, "GUARD_VECTOR_COLLECTION": "sample_mflix.movies"}
    result, collection = run(env=env, monkeypatch=monkeypatch)
    assert collection.database.client.collections == {}
    assert "must not be the collection being scanned" in result["scan"]["suggestions"]["fallback_reason"]


def test_local_mongodb_without_search_falls_back(monkeypatch):
    client = FakeClient()
    client.target_kwargs = {"fail_search": True}
    result, _ = run(collection=scanned(client), monkeypatch=monkeypatch)
    status = result["scan"]["suggestions"]
    assert status["status"] == "fallback" and "OperationFailure" in status["fallback_reason"]
    assert all(s["source"] != "atlas-vector-search" for s in result["reasons"][0]["distinct_values"][0]["suggestions"])


def test_index_still_building_falls_back(monkeypatch):
    client = FakeClient()
    client.target_kwargs = {"queryable_after": 10_000}
    result, _ = run(collection=scanned(client), monkeypatch=monkeypatch)
    assert "still building" in result["scan"]["suggestions"]["fallback_reason"]


def test_existing_index_with_other_dimensions_falls_back(monkeypatch):
    client = FakeClient()
    client.target_kwargs = {"index_dims": 1024}
    result, _ = run(collection=scanned(client), monkeypatch=monkeypatch)
    assert "1024 dimensions" in result["scan"]["suggestions"]["fallback_reason"]


def test_no_collection_in_run_falls_back(monkeypatch):
    result, _ = run(collection=None, monkeypatch=monkeypatch)
    assert "no MongoDB collection" in result["scan"]["suggestions"]["fallback_reason"]


def test_voyage_failure_falls_back_to_lexical(monkeypatch):
    result, collection = run(transport=FakeVoyage(fail=TimeoutError()), monkeypatch=monkeypatch)
    status = result["scan"]["suggestions"]
    assert status["provider"] == "lexical" and status["status"] == "fallback"
    assert collection.database.client.collections == {}


def test_missing_key_never_touches_atlas(monkeypatch):
    env = {k: v for k, v in ENV.items() if k != "VOYAGE_API_KEY"}
    result, collection = run(env=env, monkeypatch=monkeypatch)
    assert result["scan"]["suggestions"]["fallback_reason"] == "VOYAGE_API_KEY is not set"
    assert collection.database.client.collections == {}


@pytest.mark.parametrize("value, expected", [
    ("schema_guard.vocab", ("schema_guard", "vocab")),
    ("vocab", ("schema_guard", "vocab")),
    ("a.b.c", ("a", "b.c")),  # database names cannot contain dots; collection names can
    ("", None),
])
def test_vector_namespace(value, expected):
    assert vector_namespace({"GUARD_VECTOR_COLLECTION": value}) == expected


@pytest.mark.parametrize("value", ["db.", "db.system.x", "db.$bad"])
def test_invalid_vector_namespace(value):
    with pytest.raises(ValueError):
        vector_namespace({"GUARD_VECTOR_COLLECTION": value})


def test_pipeline_candidates_scale_with_limit():
    stage = vector_search_pipeline([0.1], "g", "m", 20)[0]["$vectorSearch"]
    assert stage["limit"] == 20 and stage["numCandidates"] == 400
    assert vector_search_pipeline([0.1], "g", "m", 1000)[0]["$vectorSearch"]["numCandidates"] == 10000
