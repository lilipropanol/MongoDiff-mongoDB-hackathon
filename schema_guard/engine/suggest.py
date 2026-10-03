"""Optional mapping and rename *suggestions*. They never become decisions and never change counts.

Off unless GUARD_SUGGESTIONS is set:
  GUARD_SUGGESTIONS=lexical        offline string similarity only (difflib), no network
  GUARD_SUGGESTIONS=voyage         Voyage AI embeddings: one batched request per scan
  GUARD_SUGGESTIONS=voyage-rerank  Voyage AI reranker: usually more accurate for "which allowed value did
                                   they mean?", but one request per bad value (capped at MAX_RERANK_CALLS)
  GUARD_SUGGESTIONS=atlas-vector   MongoDB Atlas Vector Search: Voyage embeddings stored in the collection
                                   named by GUARD_VECTOR_COLLECTION, matched with $vectorSearch (vector_search.py)
Both Voyage modes need VOYAGE_API_KEY and fall back to lexical on any error.

Tuning without code changes: VOYAGE_MIN_SCORE (threshold for the active Voyage mode), VOYAGE_EMBED_MODEL,
VOYAGE_RERANK_MODEL, VOYAGE_API_URL (default ai.mongodb.com for Atlas-issued keys; api.voyageai.com for voyageai.com keys).

Privacy: only distinct bad values (already truncated), allowed enum values and field names are sent.
Never document ids, documents, examples or the database URI.
"""

import difflib
import json
import math
import os
import re
import urllib.error
import urllib.request

DEFAULT_MODEL = "voyage-4-lite"
DEFAULT_RERANK_MODEL = "rerank-2.5"
DEFAULT_URL = "https://ai.mongodb.com/v1"  # MongoDB-hosted Voyage AI (Atlas-issued keys); voyageai.com keys use https://api.voyageai.com/v1
LEXICAL_MIN = 0.75
VOYAGE_MIN = 0.6
RERANK_MIN = 0.5
MAX_SUGGESTIONS = 3
MAX_TEXTS = 500
MAX_RERANK_CALLS = 20
TIMEOUT_SECONDS = 10.0
FAILURES = (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError, TypeError, IndexError)


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def lexical_score(a: str, b: str) -> float:
    na, nb = _normalize(a), _normalize(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return difflib.SequenceMatcher(None, na, nb).ratio()


def _cosine(u, v) -> float:
    dot = sum(x * y for x, y in zip(u, v))
    norm = math.sqrt(sum(x * x for x in u)) * math.sqrt(sum(y * y for y in v))
    return dot / norm if norm else 0.0


def post_json(url: str, payload: dict, api_key: str, timeout: float) -> dict:
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def _rule_at(schema: dict, path: str):
    rule = schema
    for part in path.split("."):
        items = part.count("[]")
        rule = rule.get("properties", {}).get(part.replace("[]", ""))
        if rule is None:
            return None
        for _ in range(items):
            rule = rule.get("items")
            if rule is None:
                return None
    return rule


def _types(rule):
    types = rule.get("bsonType", [])
    return set([types] if isinstance(types, str) else types) - {"null"}


def _base_url(env):
    return env.get("VOYAGE_API_URL", DEFAULT_URL).rstrip("/")


def _threshold(env, default):
    try:
        return float(env["VOYAGE_MIN_SCORE"]) if env.get("VOYAGE_MIN_SCORE") else default
    except ValueError:
        return default


class Embedder:
    """Embeds every requested text in one Voyage call, then compares with cosine similarity."""

    source = "voyage-embed"

    def __init__(self, env, transport):
        self.env, self.transport = env, transport
        self.model = env.get("VOYAGE_EMBED_MODEL", DEFAULT_MODEL)
        self.minimum = _threshold(env, VOYAGE_MIN)
        self.vectors = {}

    def prepare(self, jobs):
        texts = []
        for query, documents, *_ in jobs:
            texts += [query, *documents]
        texts = list(dict.fromkeys(texts))[:MAX_TEXTS]
        if not texts:
            return {}
        response = self.transport(f"{_base_url(self.env)}/embeddings", {"input": texts, "model": self.model},
                                  self.env["VOYAGE_API_KEY"], TIMEOUT_SECONDS)
        data = sorted(response["data"], key=lambda item: item["index"])
        if len(data) != len(texts):
            raise ValueError("Voyage returned a different number of embeddings than requested")
        self.vectors = {text: item["embedding"] for text, item in zip(texts, data)}
        return {}

    def source_of(self, query, document):
        return self.source

    def score(self, query, document):
        if query not in self.vectors or document not in self.vectors:
            return None
        return _cosine(self.vectors[query], self.vectors[document])


class Reranker:
    """Scores the candidates for each query with one Voyage rerank call per query (capped)."""

    source = "voyage-rerank"

    def __init__(self, env, transport):
        self.env, self.transport = env, transport
        self.model = env.get("VOYAGE_RERANK_MODEL", DEFAULT_RERANK_MODEL)
        self.minimum = _threshold(env, RERANK_MIN)
        self.scores = {}

    def prepare(self, jobs):
        unique = list(dict.fromkeys((query, tuple(documents)) for query, documents, *_ in jobs if documents))
        for query, documents in unique[:MAX_RERANK_CALLS]:
            response = self.transport(f"{_base_url(self.env)}/rerank",
                                      {"query": query, "documents": list(documents), "model": self.model,
                                       "top_k": min(len(documents), MAX_SUGGESTIONS)},
                                      self.env["VOYAGE_API_KEY"], TIMEOUT_SECONDS)
            for item in response["data"]:
                self.scores[(query, documents[item["index"]])] = float(item["relevance_score"])
        return {"semantic_jobs": {"scored": min(len(unique), MAX_RERANK_CALLS), "total": len(unique)}}

    def source_of(self, query, document):
        return self.source

    def score(self, query, document):
        return self.scores.get((query, document))


def _atlas_vector(env, transport, collection=None):
    from .vector_search import AtlasVectorSearch
    return AtlasVectorSearch(env, transport, collection)


PROVIDERS = {"voyage": Embedder, "voyage-rerank": Reranker, "atlas-vector": _atlas_vector}


def _value_text(field, value):
    return f"{field} value: {value}"


def _rename_text(path, rule):
    return f"field {path} ({', '.join(sorted(_types(rule))) or 'enum'})"


def _value_jobs(result, schema):
    """(distinct value entry, field path, bad value, allowed string targets) for every enum outlier."""
    for reason in result.get("reasons", []):
        if reason.get("reason") != "value_not_allowed":
            continue
        rule = _rule_at(schema, reason.get("path", reason["field"]))
        targets = [v for v in (rule or {}).get("enum", []) if isinstance(v, str)]
        for entry in reason.get("distinct_values", []):
            if targets and isinstance(entry.get("value"), str):
                yield entry, reason.get("path", reason["field"]), entry["value"], targets


def _rename_jobs(changes):
    removed = [c for c in changes if c.get("kind") == "removed"]
    added = [c for c in changes if c.get("kind") == "added"]
    for change in removed:
        parent = change.get("parent")
        old_types = _types(change["old"])
        targets = [a for a in added if a.get("parent") == parent and (not old_types or old_types & _types(a["new"]))]
        if targets:
            yield change, targets


def enrich(result: dict, schema: dict, changes: list[dict] | None = None, *, mode: str = "lexical",
           env=None, transport=None, collection=None) -> dict:
    env = os.environ if env is None else env
    transport = transport or post_json
    changes = changes or []
    status = {"provider": "lexical", "model": None, "status": "ok", "fallback_reason": None}
    value_jobs = list(_value_jobs(result, schema))
    rename_jobs = list(_rename_jobs(changes))
    provider = None
    if mode in PROVIDERS:
        if not env.get("VOYAGE_API_KEY"):
            status.update(status="fallback", fallback_reason="VOYAGE_API_KEY is not set")
        else:
            provider = PROVIDERS[mode](env, transport, collection) if mode == "atlas-vector" else PROVIDERS[mode](env, transport)
            # (query, candidates, group): group is the field path, used as the vector-search pre-filter.
            jobs = [(_value_text(path, bad), [_value_text(path, t) for t in targets], path) for _, path, bad, targets in value_jobs]
            jobs += [(_rename_text(c["field"], c["old"]), [_rename_text(t["field"], t["new"]) for t in targets], "renames")
                     for c, targets in rename_jobs]
            try:
                status.update(provider="voyage", model=provider.model, method=provider.source)
                status.update(provider.prepare(jobs))
            except FAILURES as exc:
                provider = None
                status.pop("method", None)
                status.update(provider="lexical", model=None, status="fallback",
                              fallback_reason=f"Voyage request failed ({type(exc).__name__})")

    for entry, path, bad, targets in value_jobs:
        scored = []
        for target in targets:
            lexical = lexical_score(bad, target)
            query, candidate = _value_text(path, bad), _value_text(path, target)
            semantic = provider.score(query, candidate) if provider else None
            options = [(lexical, "lexical")] if lexical >= LEXICAL_MIN else []
            if semantic is not None and semantic >= provider.minimum:
                options.append((semantic, provider.source_of(query, candidate)))
            if options:
                score, source = max(options, key=lambda o: (o[0], o[1] == "lexical"))
                # Ties on the semantic score are broken by text similarity ("PG13" → "PG-13" over "PG").
                scored.append((score, lexical, {"target": target, "score": round(score, 3), "source": source}))
        scored.sort(key=lambda item: (-item[0], -item[1]))
        entry["suggestions"] = [item[2] for item in scored[:MAX_SUGGESTIONS]]

    for change, targets in rename_jobs:
        candidates = []
        for target in targets:
            score, source = lexical_score(change["field"].split(".")[-1], target["field"].split(".")[-1]), "lexical"
            if provider:
                query, candidate = _rename_text(change["field"], change["old"]), _rename_text(target["field"], target["new"])
                semantic = provider.score(query, candidate)
                if semantic is not None and semantic > score:
                    score, source = semantic, provider.source_of(query, candidate)
            if score >= (provider.minimum if source != "lexical" else LEXICAL_MIN):
                candidates.append({"to": target["field"], "score": round(score, 3), "source": source})
        change["rename_candidates"] = sorted(candidates, key=lambda c: -c["score"])[:MAX_SUGGESTIONS]

    result.setdefault("scan", {})["suggestions"] = status
    return result


def maybe_enrich(result: dict, schema: dict, changes: list[dict] | None, env=None, transport=None, collection=None) -> dict:
    env = os.environ if env is None else env
    mode = (env.get("GUARD_SUGGESTIONS") or "").strip().lower()
    if mode not in ("lexical", *PROVIDERS):
        return result
    return enrich(result, schema, changes, mode=mode, env=env, transport=transport, collection=collection)
