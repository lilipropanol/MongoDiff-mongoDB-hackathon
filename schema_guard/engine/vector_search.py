"""MongoDB Atlas Vector Search for mapping suggestions (GUARD_SUGGESTIONS=atlas-vector).

1. One Voyage AI embeddings call turns allowed values (e.g. "rated value: PG-13") and bad values into vectors.
2. Allowed-value vectors are upserted into a dedicated vocabulary collection that you name explicitly with
   GUARD_VECTOR_COLLECTION ("database.collection"). Nothing is written unless it is set, and it may never be
   the collection being scanned. Bad values themselves are only used as query vectors and are not stored.
3. A vectorSearch index (cosine similarity, pre-filter fields "group" and "model") is created if missing,
   and the engine waits until it is queryable.
4. Each bad value runs $vectorSearch, pre-filtered to its field's allowed values. vectorSearchScore for
   cosine is (1 + cos) / 2; it is converted back to cosine so thresholds match the in-memory embedder.

If Atlas Vector Search is unavailable (local MongoDB without search, missing permissions, index still
building), suggestions fall back to in-memory cosine similarity on the same vectors, with the reason recorded.
"""

import hashlib
import time
from datetime import datetime, timezone

from pymongo import UpdateOne
from pymongo.errors import PyMongoError
from pymongo.operations import SearchIndexModel

INDEX_NAME = "schema_guard_suggestions"
DEFAULT_DATABASE = "schema_guard"
MAX_QUERIES = 50
MIN_CANDIDATES = 100
CANDIDATE_FACTOR = 20  # MongoDB guidance: numCandidates at least 20x the limit for good recall
DEFAULT_INDEX_WAIT_SECONDS = 60
POLL_SECONDS = 2


class VectorSearchUnavailable(Exception):
    """Atlas Vector Search cannot be used right now; callers fall back to in-memory similarity."""


def vector_namespace(env) -> tuple[str, str] | None:
    value = (env.get("GUARD_VECTOR_COLLECTION") or "").strip()
    if not value:
        return None
    # Database names cannot contain dots but collection names can, so split at the first dot.
    database, dot, collection = value.partition(".")
    if not dot:
        database, collection = DEFAULT_DATABASE, value
    if not collection or collection.startswith("system.") or "$" in value:
        raise ValueError(f"GUARD_VECTOR_COLLECTION must look like 'database.collection', got {value!r}")
    return database, collection


def index_definition(dimensions: int) -> dict:
    return {"fields": [
        {"type": "vector", "path": "embedding", "numDimensions": dimensions, "similarity": "cosine"},
        {"type": "filter", "path": "group"},
        {"type": "filter", "path": "model"},
    ]}


def vector_search_pipeline(query_vector, group: str, model: str, limit: int) -> list[dict]:
    limit = max(1, limit)
    return [
        {"$vectorSearch": {
            "index": INDEX_NAME, "path": "embedding", "queryVector": query_vector,
            "numCandidates": min(10000, max(MIN_CANDIDATES, limit * CANDIDATE_FACTOR)), "limit": limit,
            "filter": {"group": group, "model": model},
        }},
        {"$project": {"_id": 0, "text": 1, "score": {"$meta": "vectorSearchScore"}}},
    ]


def document_id(model: str, text: str) -> str:
    return hashlib.sha256(f"{model}\x00{text}".encode()).hexdigest()[:24]


class AtlasVectorSearch:
    """Provider used by suggest.enrich; scores come from $vectorSearch when available."""

    def __init__(self, env, transport, scanned_collection, sleep=time.sleep, clock=time.monotonic):
        from .suggest import Embedder
        self.env, self.scanned = env, scanned_collection
        self.embedder = Embedder(env, transport)
        self.model, self.minimum = self.embedder.model, self.embedder.minimum
        self.sleep, self.clock = sleep, clock
        self.scores = {}
        self.degraded = None

    @property
    def source(self):
        return "voyage-embed" if self.degraded else "atlas-vector-search"

    def source_of(self, query, document):
        return "atlas-vector-search" if (query, document) in self.scores else "voyage-embed"

    def score(self, query, document):
        if (query, document) in self.scores:
            return self.scores[(query, document)]
        return self.embedder.score(query, document)

    def prepare(self, jobs):
        self.embedder.prepare(jobs)  # one Voyage call; raises (and the caller falls back to lexical) on failure
        value_jobs = [(query, documents, group) for query, documents, group in jobs if group != "renames" and documents]
        try:
            target = self._target_collection()
            stats = self._run(target, value_jobs)
        except (VectorSearchUnavailable, PyMongoError, ValueError) as exc:
            self.degraded = f"Atlas Vector Search unavailable ({type(exc).__name__}: {exc}); used in-memory vector similarity"
            return {"status": "fallback", "fallback_reason": self.degraded[:300], "method": "voyage-embed"}
        return {"method": "atlas-vector-search", **stats}

    def _target_collection(self):
        if self.scanned is None:
            raise VectorSearchUnavailable("no MongoDB collection in this run")
        namespace = vector_namespace(self.env)
        if namespace is None:
            raise VectorSearchUnavailable("set GUARD_VECTOR_COLLECTION to allow writing suggestion vectors")
        database, collection = namespace
        if (database, collection) == (self.scanned.database.name, self.scanned.name):
            raise ValueError("GUARD_VECTOR_COLLECTION must not be the collection being scanned")
        return self.scanned.database.client[database][collection]

    def _run(self, target, value_jobs):
        vectors = self.embedder.vectors
        dimensions = len(next(iter(vectors.values()))) if vectors else 0
        if not dimensions:
            raise VectorSearchUnavailable("no embeddings to index")
        now = datetime.now(timezone.utc)
        operations, seen = [], set()
        for _, documents, group in value_jobs:
            for text in documents:
                if text in vectors and (group, text) not in seen:
                    seen.add((group, text))
                    operations.append(UpdateOne(
                        {"_id": document_id(self.model, text)},
                        {"$setOnInsert": {"text": text, "group": group, "model": self.model, "dimensions": dimensions,
                                          "embedding": vectors[text], "created_at": now}},
                        upsert=True))
        upserted = target.bulk_write(operations, ordered=False).upserted_count if operations else 0
        self._ensure_index(target, dimensions)
        queried = 0
        for query, documents, group in value_jobs[:MAX_QUERIES]:
            if query not in vectors:
                continue
            for hit in target.aggregate(vector_search_pipeline(vectors[query], group, self.model, len(documents))):
                if hit.get("text") in documents:
                    self.scores[(query, hit["text"])] = 2 * float(hit["score"]) - 1
            queried += 1
        return {"vector_collection": f"{target.database.name}.{target.name}", "index": INDEX_NAME,
                "vectors_upserted": upserted, "semantic_jobs": {"scored": queried, "total": len(value_jobs)}}

    def _ensure_index(self, target, dimensions):
        existing = list(target.list_search_indexes(INDEX_NAME))
        if not existing:
            target.create_search_index(SearchIndexModel(definition=index_definition(dimensions), name=INDEX_NAME, type="vectorSearch"))
        else:
            fields = (existing[0].get("latestDefinition") or existing[0].get("definition") or {}).get("fields", [])
            indexed = next((f.get("numDimensions") for f in fields if f.get("type") == "vector"), dimensions)
            if indexed != dimensions:
                raise VectorSearchUnavailable(f"index {INDEX_NAME} has {indexed} dimensions but the model produces {dimensions};"
                                              " use a new GUARD_VECTOR_COLLECTION or drop the index")
        wait = float(self.env.get("GUARD_VECTOR_INDEX_WAIT", DEFAULT_INDEX_WAIT_SECONDS))
        deadline = self.clock() + wait
        while True:
            status = list(target.list_search_indexes(INDEX_NAME))
            if status and status[0].get("queryable"):
                return
            if self.clock() >= deadline:
                raise VectorSearchUnavailable(f"index {INDEX_NAME} is still building; try again shortly")
            self.sleep(POLL_SECONDS)


def make_provider(env, transport, collection):
    return AtlasVectorSearch(env, transport, collection)


__all__ = ["AtlasVectorSearch", "VectorSearchUnavailable", "index_definition", "vector_search_pipeline",
           "vector_namespace", "document_id", "INDEX_NAME"]
