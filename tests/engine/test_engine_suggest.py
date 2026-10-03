"""Voyage AI / lexical suggestions with a fake HTTP transport (no network)."""

import copy
import hashlib
import json
import os
import random
import urllib.error

import pytest

from schema_guard.engine import suggest
from schema_guard.fixes import make_plan


def suggestion_report():
    """A saved-report-shaped dict with enum outliers at a root field and a nested field."""
    def value(v, n, mappable=True):
        return {"value": v, "bson_type": "string", "count": n, "mappable": mappable}

    return {
        "id": "r1", "database": "db", "collection": "movies", "source": "atlas",
        "total_docs": 10, "failing": 6, "preexisting": 1, "newly_failing": 5, "unclassified": 0,
        "new_schema": SCHEMA, "scan": {},
        "reasons": [
            {"field": "rated", "reason": "value_not_allowed", "count": 4, "path": "rated", "location": "field",
             "example_ids": ["movie-001"], "examples": [{"_id": "movie-001", "title": "The Quiet Harbour", "rated": "PG13"}],
             "distinct_values": [value("PG13", 2), value("pg", 1), value("NOT RATED", 1)]},
            {"field": "imdb", "reason": "value_not_allowed", "count": 1, "path": "imdb.label", "location": "nested",
             "example_ids": [], "examples": [], "distinct_values": [value("goood", 1, mappable=False)]},
            {"field": "runtime", "reason": "missing", "count": 1, "path": "runtime", "location": "field",
             "example_ids": [], "examples": []},
        ],
    }

SCHEMA = {"bsonType": "object", "properties": {
    "rated": {"enum": ["G", "PG", "PG-13", "R"]},
    "imdb": {"bsonType": "object", "properties": {"label": {"enum": ["good", "bad"]}}},
    "runtime": {"bsonType": ["int", "long"]},
}}


class FakeVoyage:
    """Embeds by keyword so that 'PG13' ≈ 'PG-13' and 'NOT RATED' is far from everything."""

    def __init__(self, fail=None):
        self.calls, self.fail = [], fail

    def __call__(self, url, payload, api_key, timeout):
        self.calls.append({"url": url, "payload": copy.deepcopy(payload), "api_key": api_key, "timeout": timeout})
        if self.fail:
            raise self.fail
        return {"data": [{"index": i, "embedding": self.vector(text)} for i, text in enumerate(payload["input"])]}

    @staticmethod
    def vector(text, dims=32):
        """Known synonyms share a direction; every other text gets its own deterministic pseudo-random direction."""
        value = text.split(":", 1)[-1].strip().lower().replace("-", "").replace(" ", "")
        anchor = {"pg13": 0, "pg": 0, "goood": 1, "good": 1}.get(value)
        if anchor is None and ("duration" in text or "runtime" in text):
            anchor = 2
        if anchor is not None:
            vec = [0.0] * dims
            vec[anchor] = 1.0
            return vec
        rng = random.Random(hashlib.sha256(text.encode()).digest())
        return [0.0, 0.0, 0.0] + [rng.gauss(0, 1) for _ in range(dims - 3)]


ENV = {"GUARD_SUGGESTIONS": "voyage", "VOYAGE_API_KEY": "test-key"}


def test_off_by_default_makes_no_call_and_changes_nothing():  # U-S1
    report = suggestion_report()
    fake = FakeVoyage()
    before = copy.deepcopy(report)
    suggest.maybe_enrich(report, SCHEMA, [], env={}, transport=fake)
    assert report == before and fake.calls == []


def test_lexical_mode_is_offline():  # U-S7
    report = suggestion_report()
    fake = FakeVoyage()
    suggest.maybe_enrich(report, SCHEMA, [], env={"GUARD_SUGGESTIONS": "lexical"}, transport=fake)
    values = {v["value"]: v["suggestions"] for v in report["reasons"][0]["distinct_values"]}
    assert fake.calls == []
    assert values["PG13"][0] == {"target": "PG-13", "score": 1.0, "source": "lexical"}
    assert values["pg"][0]["target"] == "PG"
    assert values["NOT RATED"] == []
    assert report["scan"]["suggestions"] == {"provider": "lexical", "model": None, "status": "ok", "fallback_reason": None}


def test_voyage_payload_contains_only_values_targets_and_field_names():  # U-S2
    report = suggestion_report()
    fake = FakeVoyage()
    suggest.maybe_enrich(report, SCHEMA, [], env=ENV, transport=fake)
    assert len(fake.calls) == 1  # one batched request per scan
    call = fake.calls[0]
    assert call["url"] == "https://api.voyageai.com/v1/embeddings"
    assert call["payload"]["model"] == "voyage-4-lite"
    sent = json.dumps(call["payload"])
    for secret in ("movie-001", "mongodb+srv", "_id", "example", "Quiet Harbour"):
        assert secret not in sent
    assert set(call["payload"]["input"]) >= {"rated value: PG13", "rated value: PG-13", "imdb.label value: goood"}


def test_voyage_suggestions_sorted_bounded_and_thresholded():  # U-S3
    report = suggestion_report()
    suggest.maybe_enrich(report, SCHEMA, [], env=ENV, transport=FakeVoyage())
    rated = {v["value"]: v["suggestions"] for v in report["reasons"][0]["distinct_values"]}
    assert rated["PG13"][0]["target"] == "PG-13"
    assert rated["PG13"][0]["source"] in ("voyage-embed", "lexical")
    assert all(len(s) <= suggest.MAX_SUGGESTIONS for s in rated.values())
    for suggestions in rated.values():
        assert [s["score"] for s in suggestions] == sorted((s["score"] for s in suggestions), reverse=True)
    assert rated["NOT RATED"] == []
    nested = report["reasons"][1]["distinct_values"][0]["suggestions"]
    assert nested[0]["target"] == "good"
    assert report["scan"]["suggestions"]["provider"] == "voyage"
    assert report["scan"]["suggestions"]["model"] == "voyage-4-lite"


@pytest.mark.parametrize("failure", [
    urllib.error.URLError("down"),
    TimeoutError(),
    urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None),
    KeyError("data"),
])
def test_voyage_failure_falls_back_to_lexical(failure):  # U-S4
    report = suggestion_report()
    suggest.maybe_enrich(report, SCHEMA, [], env=ENV, transport=FakeVoyage(fail=failure))
    status = report["scan"]["suggestions"]
    assert status["status"] == "fallback" and status["provider"] == "lexical"
    assert "Voyage request failed" in status["fallback_reason"]
    assert report["reasons"][0]["distinct_values"][0]["suggestions"][0]["source"] == "lexical"


def test_malformed_voyage_response_falls_back():
    def bad(url, payload, api_key, timeout):
        return {"data": [{"index": 0, "embedding": [1.0]}]}  # fewer embeddings than texts

    report = suggestion_report()
    suggest.maybe_enrich(report, SCHEMA, [], env=ENV, transport=bad)
    assert report["scan"]["suggestions"]["status"] == "fallback"


def test_voyage_mode_without_key_falls_back():
    report = suggestion_report()
    fake = FakeVoyage()
    suggest.maybe_enrich(report, SCHEMA, [], env={"GUARD_SUGGESTIONS": "voyage"}, transport=fake)
    assert fake.calls == []
    assert report["scan"]["suggestions"]["fallback_reason"] == "VOYAGE_API_KEY is not set"


def test_custom_model_and_url_are_used():
    fake = FakeVoyage()
    env = {**ENV, "VOYAGE_EMBED_MODEL": "voyage-4", "VOYAGE_API_URL": "https://example.test/v1/"}
    suggest.maybe_enrich(suggestion_report(), SCHEMA, [], env=env, transport=fake)
    assert fake.calls[0]["url"] == "https://example.test/v1/embeddings"
    assert fake.calls[0]["payload"]["model"] == "voyage-4"


def test_suggestions_never_change_plans_or_counts():  # U-S5, U-S6
    plain, enriched = suggestion_report(), suggestion_report()
    suggest.maybe_enrich(enriched, SCHEMA, [], env=ENV, transport=FakeVoyage())
    for key in ("total_docs", "failing", "preexisting", "newly_failing", "unclassified"):
        assert plain[key] == enriched[key]
    assert [r["count"] for r in plain["reasons"]] == [r["count"] for r in enriched["reasons"]]
    decisions = ({"runtime": 90}, {"rated": {"PG13": "PG-13"}})
    assert make_plan(plain, *decisions)["operations"] == make_plan(enriched, *decisions)["operations"]


def test_rename_candidates():  # U-S8
    changes = [
        {"field": "runtime", "kind": "removed", "old": {"bsonType": ["int", "long"]}},
        {"field": "duration_minutes", "kind": "added", "new": {"bsonType": ["int", "long"]}, "required": True},
        {"field": "poster", "kind": "added", "new": {"bsonType": "string"}, "required": False},
        {"field": "imdb.score", "kind": "removed", "old": {"bsonType": "double"}, "parent": "imdb"},
        {"field": "imdb.scores", "kind": "added", "new": {"bsonType": "double"}, "parent": "imdb"},
    ]
    suggest.enrich({"reasons": []}, SCHEMA, changes, mode="voyage", env=ENV, transport=FakeVoyage())
    assert changes[0]["rename_candidates"][0]["to"] == "duration_minutes"
    assert changes[0]["rename_candidates"][0]["source"] == "voyage-embed"
    assert all(c["to"] != "poster" for c in changes[0]["rename_candidates"])  # incompatible type
    assert changes[3]["rename_candidates"] == [{"to": "imdb.scores", "score": pytest.approx(0.909, abs=0.01), "source": "lexical"}]


def test_lexical_score_basics():
    assert suggest.lexical_score("PG13", "PG-13") == 1.0
    assert suggest.lexical_score("", "x") == 0.0
    assert suggest.lexical_score("abc", "xyz") < 0.5


@pytest.mark.skipif(not os.getenv("VOYAGE_API_KEY") or not os.getenv("SCHEMA_GUARD_LIVE_VOYAGE"),
                    reason="live Voyage check: set VOYAGE_API_KEY and SCHEMA_GUARD_LIVE_VOYAGE=1")
def test_live_voyage_smoke():  # L-S1
    report = suggestion_report()
    suggest.maybe_enrich(report, SCHEMA, [], env={**os.environ, "GUARD_SUGGESTIONS": "voyage"})
    assert report["scan"]["suggestions"]["status"] == "ok", report["scan"]["suggestions"]
    rated = {v["value"]: v["suggestions"] for v in report["reasons"][0]["distinct_values"]}
    assert rated["PG13"] and rated["PG13"][0]["target"] == "PG-13"


# --- Voyage reranker (GUARD_SUGGESTIONS=voyage-rerank) ----------------------------------------

class FakeRerank:
    """Scores 'PG-13' highest for PG13-like queries; records every call."""

    def __init__(self, fail=None):
        self.calls, self.fail = [], fail

    def __call__(self, url, payload, api_key, timeout):
        self.calls.append({"url": url, "payload": copy.deepcopy(payload)})
        if self.fail:
            raise self.fail
        query = payload["query"].split(":", 1)[-1].strip().lower().replace("-", "")
        scored = []
        for index, document in enumerate(payload["documents"]):
            value = document.split(":", 1)[-1].strip().lower().replace("-", "")
            scored.append({"index": index, "relevance_score": 0.95 if value == query else (0.7 if value.startswith(query[:2]) else 0.1)})
        scored.sort(key=lambda item: -item["relevance_score"])
        return {"data": scored[:payload["top_k"]]}


RERANK_ENV = {"GUARD_SUGGESTIONS": "voyage-rerank", "VOYAGE_API_KEY": "test-key"}


def test_rerank_sends_one_request_per_bad_value_with_safe_payload():
    fake = FakeRerank()
    report = suggestion_report()
    suggest.maybe_enrich(report, SCHEMA, [], env=RERANK_ENV, transport=fake)
    assert len(fake.calls) == 4  # PG13, pg, NOT RATED, goood
    assert {c["url"] for c in fake.calls} == {"https://api.voyageai.com/v1/rerank"}
    first = fake.calls[0]["payload"]
    assert first["model"] == "rerank-2.5" and first["top_k"] == 3
    assert first["query"] == "rated value: PG13"
    assert first["documents"] == ["rated value: G", "rated value: PG", "rated value: PG-13", "rated value: R"]
    sent = json.dumps([c["payload"] for c in fake.calls])
    for secret in ("movie-001", "Quiet Harbour", "_id", "example"):
        assert secret not in sent


def test_rerank_suggestions_and_status():
    report = suggestion_report()
    suggest.maybe_enrich(report, SCHEMA, [], env=RERANK_ENV, transport=FakeRerank())
    rated = {v["value"]: v["suggestions"] for v in report["reasons"][0]["distinct_values"]}
    assert rated["PG13"][0]["target"] == "PG-13"
    assert rated["NOT RATED"] == []  # every score below the rerank threshold
    status = report["scan"]["suggestions"]
    assert status["provider"] == "voyage" and status["model"] == "rerank-2.5" and status["method"] == "voyage-rerank"
    assert status["semantic_jobs"] == {"scored": 4, "total": 4}


def test_rerank_calls_are_capped(monkeypatch):
    monkeypatch.setattr(suggest, "MAX_RERANK_CALLS", 2)
    fake = FakeRerank()
    report = suggestion_report()
    suggest.maybe_enrich(report, SCHEMA, [], env=RERANK_ENV, transport=fake)
    assert len(fake.calls) == 2
    assert report["scan"]["suggestions"]["semantic_jobs"] == {"scored": 2, "total": 4}
    goood = report["reasons"][1]["distinct_values"][0]["suggestions"]
    assert goood and goood[0]["source"] == "lexical"  # unscored jobs still get offline suggestions


def test_rerank_failure_falls_back():
    report = suggestion_report()
    suggest.maybe_enrich(report, SCHEMA, [], env=RERANK_ENV, transport=FakeRerank(fail=TimeoutError()))
    assert report["scan"]["suggestions"]["status"] == "fallback"


def test_min_score_and_models_are_tunable_from_env():
    strict = {**RERANK_ENV, "VOYAGE_MIN_SCORE": "0.99", "VOYAGE_RERANK_MODEL": "rerank-2.5-lite"}
    fake = FakeRerank()
    report = suggestion_report()
    suggest.maybe_enrich(report, SCHEMA, [], env=strict, transport=fake)
    assert fake.calls[0]["payload"]["model"] == "rerank-2.5-lite"
    pg13 = report["reasons"][0]["distinct_values"][0]["suggestions"]
    assert all(s["source"] == "lexical" for s in pg13)  # 0.95 < 0.99, so only the exact text match remains
    bad = {**RERANK_ENV, "VOYAGE_MIN_SCORE": "not-a-number"}
    assert suggest._threshold(bad, 0.5) == 0.5


def test_rerank_rename_candidates():
    changes = [
        {"field": "rated", "kind": "removed", "old": {"bsonType": "string"}},
        {"field": "rating", "kind": "added", "new": {"bsonType": "string"}, "required": True},
    ]
    suggest.enrich({"reasons": []}, SCHEMA, changes, mode="voyage-rerank", env=RERANK_ENV, transport=FakeRerank())
    assert changes[0]["rename_candidates"][0]["to"] == "rating"
