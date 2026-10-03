"""Engine semantics verified against a real MongoDB server.

The "zoo" is a hand-built corpus where every expected count was worked out by hand (see the table in
docs/engine/schema-impact-plan.md §6.2). Independent oracles (MongoDB's own $jsonSchema counts, find()
id sets and the Python fixture adapter) cross-check the engine so we are not only trusting our own code.
"""

from copy import deepcopy
from pathlib import Path
from typing import Literal, Optional
from uuid import uuid4

import pytest
from bson import Decimal128, Int64
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from schema_guard import server
from schema_guard.demo import SEED, analyze_demo, matches_schema
from schema_guard.engine.diff import compare
from schema_guard.engine.impact import analyze_collection
from schema_guard.engine.models import load_collection_validator, load_model
from schema_guard.engine.translator import SchemaTranslator

pytestmark = pytest.mark.mongo
ROOT = Path(__file__).resolve().parents[3]
MISSING = object()


class Imdb(BaseModel):
    rating: float
    votes: int


class CastMember(BaseModel):
    name: str


class Old(BaseModel):
    id: str = Field(alias="_id")
    title: str
    runtime: Optional[int] = None


class New(BaseModel):
    id: str = Field(alias="_id")
    title: str
    runtime: int
    rated: Literal["G", "PG", "PG-13", "R"]
    genres: list[str]
    imdb: Imdb
    cast: list[CastMember]
    awards_text: Optional[str] = None


T = SchemaTranslator()
OLD, NEW = T.translate(Old), T.translate(New)


def doc(_id, **overrides):
    base = {"_id": _id, "title": "T", "runtime": 100, "rated": "PG", "genres": ["Drama"],
            "imdb": {"rating": 7.5, "votes": 10}, "cast": [{"name": "A"}], "awards_text": "x"}
    base.update(overrides)
    return {k: v for k, v in base.items() if v is not MISSING}


ZOO = [
    doc("z01"),
    doc("z02", runtime=MISSING),
    doc("z03", runtime=None),
    doc("z04", runtime="118"),
    doc("z05", runtime="N/A"),
    doc("z06a", runtime=[90]),
    doc("z06b", runtime=["90"]),
    doc("z07", runtime=90.0),
    doc("z08", runtime=True),
    doc("z09", runtime=Int64(90)),
    doc("z10a", rated="PG13"),
    doc("z10b", rated="NR"),
    doc("z10c", rated="pg"),
    doc("z11", rated=MISSING),
    doc("z12", genres=["Drama", 1]),
    doc("z13", genres=[]),
    doc("z14", genres="Drama"),
    doc("z15", imdb={}),
    doc("z16", imdb={"rating": "", "votes": 5}),
    doc("z17", imdb=None),
    doc("z18", imdb=[{"rating": 1, "votes": 1}]),
    doc("z19", cast=[{"name": "A"}, {}]),
    doc("z20", cast=[{"name": 5}]),
    doc("z21", rated=MISSING, runtime="118", imdb={"rating": "", "votes": 10}),
    doc("z22", awards_text=MISSING),
    doc("z23", awards_text=None),
    doc("z24", imdb={"rating": Decimal128("7.1"), "votes": 10}),
    doc("z25", title=MISSING),
]
VALID = {"z01", "z09", "z13", "z22", "z23", "z24"}
OLD_INVALID = {"z04", "z05", "z06a", "z06b", "z07", "z08", "z21", "z25"}

ROOT_COUNTS = {
    ("title", "missing"): 1,
    ("runtime", "missing"): 1,
    ("runtime", "null_not_allowed"): 1,
    ("runtime", "wrong_type"): 7,
    ("rated", "missing"): 2,
    ("rated", "value_not_allowed"): 3,
    ("genres", "wrong_type"): 1,
    ("genres", "nested_or_array_constraint"): 1,
    ("imdb", "null_not_allowed"): 1,
    ("imdb", "wrong_type"): 1,
    ("imdb", "nested_or_array_constraint"): 3,
    ("cast", "nested_or_array_constraint"): 2,
}
DEEP_COUNTS = {
    ("genres[]", "wrong_type"): 1,
    ("imdb.rating", "missing"): 1,
    ("imdb.votes", "missing"): 1,
    ("imdb.rating", "wrong_type"): 2,
    ("cast[].name", "missing"): 1,
    ("cast[].name", "wrong_type"): 1,
}


@pytest.fixture
def zoo(fresh_collection):
    fresh_collection.insert_many(deepcopy(ZOO))
    return fresh_collection


@pytest.fixture
def zoo_result(zoo):
    return analyze_collection(zoo, NEW, compare(OLD, NEW), old_schema=OLD)


def reasons_by(result, location=None):
    return {(r["path"], r["reason"]): r for r in result["reasons"] if location is None or (r["location"] == "field") == (location == "field")}


def ids(collection, query):
    return {d["_id"] for d in collection.find(query, {"_id": 1})}


# --- Exact expected counts ------------------------------------------------------------------

def test_zoo_totals(zoo_result):  # T-I1
    assert (zoo_result["total"], zoo_result["failing"], zoo_result["preexisting"], zoo_result["newly_failing"]) == (28, 22, 8, 14)
    assert zoo_result["unclassified"] == 0


def test_zoo_root_reason_counts(zoo_result):  # T-I1
    got = {(r["field"], r["reason"]): r["count"] for r in zoo_result["reasons"] if r["location"] == "field"}
    assert got == ROOT_COUNTS


def test_zoo_deep_reason_counts(zoo_result):  # T-N1
    got = {(r["path"], r["reason"]): r["count"] for r in zoo_result["reasons"] if r["location"] != "field"}
    assert got == DEEP_COUNTS
    for reason in zoo_result["reasons"]:
        assert reason["field"] in NEW["properties"]
        assert reason["path"].split(".")[0].replace("[]", "") == reason["field"]


# --- Oracles: MongoDB's own answers ---------------------------------------------------------

def test_failing_matches_mongodb_jsonschema(zoo, zoo_result):  # T-I2
    invalid = {"$nor": [{"$jsonSchema": NEW}]}
    assert zoo_result["failing"] == zoo.count_documents(invalid)
    assert ids(zoo, invalid) == {d["_id"] for d in ZOO} - VALID


def test_drift_matches_mongodb_jsonschema(zoo, zoo_result):  # T-I3
    assert zoo_result["preexisting"] == zoo.count_documents({"$nor": [{"$jsonSchema": OLD}]})
    assert zoo_result["newly_failing"] == zoo.count_documents({"$and": [{"$jsonSchema": OLD}, {"$nor": [{"$jsonSchema": NEW}]}]})
    assert ids(zoo, {"$nor": [{"$jsonSchema": OLD}]}) == OLD_INVALID


def test_reason_counts_overlap_but_failing_is_unique(zoo_result):  # T-I4
    root_total = sum(r["count"] for r in zoo_result["reasons"] if r["location"] == "field")
    assert root_total > zoo_result["failing"]
    assert all(r["count"] <= zoo_result["failing"] for r in zoo_result["reasons"])


def test_examples_are_failing_bounded_and_projected(zoo, zoo_result):  # T-I5
    failing = ids(zoo, {"$nor": [{"$jsonSchema": NEW}]})
    for reason in zoo_result["reasons"]:
        assert 1 <= len(reason["examples"]) <= 3
        assert set(reason["example_ids"]) <= failing
        for example in reason["examples"]:
            assert set(example) <= {"_id", reason["field"]}
            value = example.get(reason["field"])
            if isinstance(value, list):
                assert len(value) <= 5


def test_example_strings_and_arrays_are_truncated(fresh_collection):
    fresh_collection.insert_one(doc("big", runtime="x" * 1000, genres=[1] * 50))
    result = analyze_collection(fresh_collection, NEW, [])
    runtime = reasons_by(result)[("runtime", "wrong_type")]["examples"][0]["runtime"]
    genres = reasons_by(result)[("genres", "nested_or_array_constraint")]["examples"][0]["genres"]
    assert len(runtime) == 200 and len(genres) == 5


def test_unclassified_matches_independent_python_computation(zoo, zoo_result):  # T-I6
    from schema_guard.engine.impact import reason_specs
    failing = ids(zoo, {"$nor": [{"$jsonSchema": NEW}]})
    explained = set()
    for spec in reason_specs(NEW):
        explained |= ids(zoo, {"$and": [{"$nor": [{"$jsonSchema": NEW}]}, spec["query"]]})
    assert zoo_result["unclassified"] == len(failing - explained) == 0


def test_query_type_matches_array_elements_but_engine_does_not(zoo, zoo_result):  # T-I7
    # The pitfall: query-language $type also matches arrays that *contain* a string.
    assert "z06b" in ids(zoo, {"runtime": {"$type": "string"}})
    values = reasons_by(zoo_result)[("runtime", "wrong_type")]["distinct_values"]
    assert {"value": None, "bson_type": "array", "count": 2, "mappable": False} in values


def test_scan_is_read_only(zoo):  # T-I8
    before = list(zoo.find().sort("_id"))
    indexes = zoo.index_information()
    analyze_collection(zoo, NEW, compare(OLD, NEW), old_schema=OLD)
    assert list(zoo.find().sort("_id")) == before
    assert zoo.index_information() == indexes


def strip_timing(result):
    clean = deepcopy(result)
    clean["scan"].pop("duration_ms")
    clean["scan"].pop("two_pass")
    return clean


def test_scan_is_deterministic(zoo):  # T-I9
    first = analyze_collection(zoo, NEW, [], old_schema=OLD)
    second = analyze_collection(zoo, NEW, [], old_schema=OLD)
    assert strip_timing(first) == strip_timing(second)


def test_python_fixture_adapter_agrees_except_known_gaps(zoo):  # T-I10
    mongo_failing = ids(zoo, {"$nor": [{"$jsonSchema": NEW}]})
    python_failing = {d["_id"] for d in zoo.find() if not matches_schema(d, NEW)}
    # Known gap: the fixture adapter does not know BSON Decimal128, which MongoDB accepts for float.
    assert mongo_failing ^ python_failing == {"z24"}


# --- Nested-path guards ---------------------------------------------------------------------

def test_no_nested_reasons_when_parent_is_null_or_array(zoo, zoo_result):  # T-N2
    nested_ids = set()
    for reason in zoo_result["reasons"]:
        if reason["path"].startswith("imdb."):
            nested_ids |= set(reason["example_ids"])
    assert not nested_ids & {"z17", "z18"}


def test_non_array_value_does_not_produce_element_reasons(zoo_result):  # T-N3
    element = reasons_by(zoo_result)[("genres[]", "wrong_type")]
    assert element["count"] == 1 and element["example_ids"] == ["z12"]


# --- Drift split, distinct values, warnings ------------------------------------------------

def test_per_reason_new_vs_preexisting_split(zoo_result):  # T-L5
    reasons = reasons_by(zoo_result)
    assert (reasons[("runtime", "wrong_type")]["count_newly"], reasons[("runtime", "wrong_type")]["count_preexisting"]) == (0, 7)
    assert (reasons[("rated", "missing")]["count_newly"], reasons[("rated", "missing")]["count_preexisting"]) == (1, 1)
    assert (reasons[("imdb.rating", "wrong_type")]["count_newly"], reasons[("imdb.rating", "wrong_type")]["count_preexisting"]) == (1, 1)
    assert (reasons[("title", "missing")]["count_newly"], reasons[("title", "missing")]["count_preexisting"]) == (0, 1)
    for reason in zoo_result["reasons"]:
        assert reason["count_newly"] + reason["count_preexisting"] == reason["count"]


def test_distinct_values_for_wrong_type(zoo_result):  # T-V1
    reason = reasons_by(zoo_result)[("runtime", "wrong_type")]
    got = {(v["value"], v["bson_type"]): v["count"] for v in reason["distinct_values"]}
    assert got == {("118", "string"): 2, (None, "array"): 2, ("N/A", "string"): 1, (90.0, "double"): 1, (True, "bool"): 1}
    assert [v["count"] for v in reason["distinct_values"]] == sorted((v["count"] for v in reason["distinct_values"]), reverse=True)
    assert reason["distinct_value_count"] == 5 and reason["distinct_values_limited"] is False
    assert "strictly" in reason["explanation"] and "90.0" in reason["explanation"]


def test_distinct_values_keep_types_apart(fresh_collection):  # T-V2
    fresh_collection.insert_many([doc("a", runtime="1"), doc("b", runtime="1"), doc("c", runtime=1.5)])
    values = reasons_by(analyze_collection(fresh_collection, NEW, []))[("runtime", "wrong_type")]["distinct_values"]
    assert {(v["value"], v["bson_type"], v["count"]) for v in values} == {("1", "string", 2), (1.5, "double", 1)}


def test_distinct_limit_reports_true_total(zoo):  # T-V3
    result = analyze_collection(zoo, NEW, [], distinct_limit=2)
    reason = reasons_by(result)[("runtime", "wrong_type")]
    assert len(reason["distinct_values"]) == 2
    assert reason["distinct_values_limited"] is True and reason["distinct_value_count"] == 5


def test_mappable_only_for_root_strings(zoo_result):  # T-V4
    for reason in zoo_result["reasons"]:
        for value in reason.get("distinct_values", []):
            assert value["mappable"] == (value["bson_type"] == "string" and reason["location"] == "field")
    rated = reasons_by(zoo_result)[("rated", "value_not_allowed")]["distinct_values"]
    assert {v["value"] for v in rated} == {"PG13", "NR", "pg"} and all(v["mappable"] for v in rated)
    nested = reasons_by(zoo_result)[("imdb.rating", "wrong_type")]["distinct_values"]
    assert nested == [{"value": "", "bson_type": "string", "count": 2, "mappable": False}]


def test_distinct_values_never_contain_documents(zoo_result):  # T-V5
    for reason in zoo_result["reasons"]:
        for value in reason.get("distinct_values", []):
            assert set(value) <= {"value", "bson_type", "count", "mappable", "truncated"}
            assert not isinstance(value["value"], (dict, list))


def test_long_bad_strings_truncated_but_grouped_exactly(fresh_collection):  # T-V6
    long_a, long_b = "a" * 500, "a" * 499 + "b"
    fresh_collection.insert_many([doc("1", runtime=long_a), doc("2", runtime=long_a), doc("3", runtime=long_b)])
    values = reasons_by(analyze_collection(fresh_collection, NEW, []))[("runtime", "wrong_type")]["distinct_values"]
    assert sorted(v["count"] for v in values) == [1, 2]
    assert all(len(v["value"]) == 80 and v["truncated"] for v in values)


def test_missing_defaulted_field_is_a_warning_not_a_failure(zoo_result):  # T-W1
    assert zoo_result["warnings"] == [{"field": "awards_text", "path": "awards_text", "kind": "missing_defaulted_field", "count": 1,
                                       "message": zoo_result["warnings"][0]["message"]}]
    assert "default" in zoo_result["warnings"][0]["message"]


def test_nested_optional_warning_only_where_parent_is_object(fresh_collection):  # T-W2
    class Info(BaseModel):
        note: Optional[str] = None

    class M(BaseModel):
        info: Optional[Info] = None

    schema = T.translate(M)
    fresh_collection.insert_many([{"_id": 1, "info": {}}, {"_id": 2, "info": None}, {"_id": 3}, {"_id": 4, "info": {"note": "x"}}])
    warnings = {w["path"]: w["count"] for w in analyze_collection(fresh_collection, schema, [])["warnings"]}
    assert warnings == {"info": 1, "info.note": 1}


# --- Limits, empty and missing collections, equivalence -------------------------------------

def test_empty_collection(mongo_client):  # T-L1
    db = mongo_client["schema_guard_it"]
    name = f"empty_{uuid4().hex[:8]}"
    db.create_collection(name)
    try:
        result = analyze_collection(db[name], NEW, [], old_schema=OLD)
        assert (result["total"], result["failing"], result["reasons"]) == (0, 0, [])
        assert result["scan"]["collection_exists"] is True
    finally:
        db.drop_collection(name)


def test_missing_collection(mongo_client):  # T-L2
    result = analyze_collection(mongo_client["schema_guard_it"][f"nope_{uuid4().hex[:8]}"], NEW, [])
    assert result["total"] == 0 and result["scan"]["collection_exists"] is False


def test_two_pass_equals_single_pass(zoo):  # T-L3
    assert strip_timing(analyze_collection(zoo, NEW, [], old_schema=OLD, two_pass=True)) == \
        strip_timing(analyze_collection(zoo, NEW, [], old_schema=OLD, two_pass=False))


def test_larger_collection_counts_scale_exactly(fresh_collection):
    docs = []
    for i in range(5000):
        kind = i % 5
        docs.append(doc(f"n{i}", **({1: {"runtime": str(i)}, 2: {"rated": "NR"}, 3: {"imdb": {"rating": "", "votes": 1}}}.get(kind, {}))))
    fresh_collection.insert_many(docs)
    result = analyze_collection(fresh_collection, NEW, [])
    reasons = reasons_by(result)
    assert (result["total"], result["failing"]) == (5000, 3000)
    assert reasons[("runtime", "wrong_type")]["count"] == 1000
    assert reasons[("runtime", "wrong_type")]["distinct_value_count"] == 1000
    assert len(reasons[("runtime", "wrong_type")]["distinct_values"]) == 10
    assert reasons[("rated", "value_not_allowed")]["count"] == 1000
    assert reasons[("imdb.rating", "wrong_type")]["count"] == 1000
    assert result["scan"]["duration_ms"] >= 0


# --- Enum equality semantics: our nested $in agrees with $jsonSchema -----------------------

def test_nested_enum_check_agrees_with_jsonschema(fresh_collection, server_version):  # T-I11
    class Inner(BaseModel):
        k: Literal[1, 2]

    class M(BaseModel):
        r: Literal[1, 2]
        o: Inner

    schema = T.translate(M)
    values = [1, 1.0, Int64(1), Decimal128("1"), "1", 3, True]
    fresh_collection.insert_many([{"_id": i, "r": v, "o": {"k": v}} for i, v in enumerate(values)])
    result = analyze_collection(fresh_collection, schema, [])
    reasons = reasons_by(result)
    root_oracle = fresh_collection.count_documents({"$nor": [{"$jsonSchema": {"properties": {"r": schema["properties"]["r"]}}}]})
    nested_oracle = fresh_collection.count_documents({"$nor": [{"$jsonSchema": {"properties": {"o": schema["properties"]["o"]}}}]})
    assert reasons[("r", "value_not_allowed")]["count"] == root_oracle
    assert reasons[("o.k", "value_not_allowed")]["count"] == nested_oracle
    # Recorded behaviour (MongoDB compares numbers by value; bool and string never equal numbers): "1", 3, True fail.
    assert root_oracle == 3, f"MongoDB {server_version} enum semantics changed"


# --- Starter fixtures: the demo numbers match real MongoDB ----------------------------------

def test_demo_seed_counts_match_real_mongodb(fresh_collection):  # T-I12
    old = T.translate(load_model(str(ROOT / "examples/models_old.py") + ":Movie"))
    new = T.translate(load_model(str(ROOT / "examples/models_new.py") + ":Movie"))
    fresh_collection.insert_many(deepcopy(SEED))
    real = analyze_collection(fresh_collection, new, compare(old, new), old_schema=old)
    fixture = analyze_demo(SEED, old, new)
    assert (real["total"], real["failing"], real["preexisting"], real["newly_failing"]) == (12, 7, 2, 5)
    assert {(r["field"], r["reason"]): r["count"] for r in real["reasons"]} == \
        {(r["field"], r["reason"]): r["count"] for r in fixture["reasons"]}


# --- Language-agnostic sources end to end ---------------------------------------------------

def test_existing_collection_validator_is_a_schema_source(mongo_client):
    db = mongo_client["schema_guard_it"]
    name = f"validated_{uuid4().hex[:8]}"
    db.create_collection(name, validator={"$jsonSchema": OLD}, validationLevel="moderate", validationAction="warn")
    try:
        document, settings = load_collection_validator(db[name])
        assert T.translate(document) == OLD
        assert settings == {"exists": True, "validationLevel": "moderate", "validationAction": "warn"}
        db[name].insert_many(deepcopy(ZOO))
        result = analyze_collection(db[name], NEW, [], old_schema=T.translate(document))
        assert (result["failing"], result["preexisting"]) == (22, 8)
    finally:
        db.drop_collection(name)


def test_collection_without_or_with_non_jsonschema_validator(mongo_client):
    db = mongo_client["schema_guard_it"]
    plain, query = f"plain_{uuid4().hex[:8]}", f"query_{uuid4().hex[:8]}"
    db.create_collection(plain)
    db.create_collection(query, validator={"title": {"$type": "string"}})
    try:
        assert load_collection_validator(db[plain])[0] is None
        with pytest.raises(ValueError, match="only a plain \\$jsonSchema"):
            load_collection_validator(db[query])
    finally:
        db.drop_collection(plain)
        db.drop_collection(query)


def test_server_atlas_path_with_json_schema_files(fresh_collection, mongo_uri, tmp_path, monkeypatch):
    """Person 3's unchanged server, pointed at a disposable local MongoDB and language-agnostic schema files."""
    fresh_collection.insert_many(deepcopy(SEED))
    monkeypatch.setenv("MONGODB_URI", mongo_uri)
    monkeypatch.setenv("MONGODB_DATABASE", fresh_collection.database.name)
    monkeypatch.setenv("MONGODB_COLLECTION", fresh_collection.name)
    monkeypatch.setenv("GUARD_OLD_MODEL", str(ROOT / "examples/engine/movie_old.schema.json"))
    monkeypatch.setenv("GUARD_NEW_MODEL", str(ROOT / "examples/engine/movie_new.schema.json"))
    monkeypatch.setenv("GUARD_REPORT_DIR", str(tmp_path))
    monkeypatch.delenv("GUARD_SUGGESTIONS", raising=False)
    report = TestClient(server.app).post("/api/analyze", json={"session_id": str(uuid4()), "source": "atlas"}).json()
    assert (report["total_docs"], report["failing"], report["preexisting"], report["newly_failing"]) == (12, 7, 2, 5)
    rated = next(r for r in report["reasons"] if r["reason"] == "value_not_allowed")
    assert {v["value"] for v in rated["distinct_values"]} == {"PG13", "NR"}
    assert mongo_uri not in str(report)


def test_lexical_suggestions_through_a_real_scan(zoo, monkeypatch):
    monkeypatch.setenv("GUARD_SUGGESTIONS", "lexical")
    result = analyze_collection(zoo, NEW, [], old_schema=OLD)
    rated = {v["value"]: v["suggestions"] for v in reasons_by(result)[("rated", "value_not_allowed")]["distinct_values"]}
    assert rated["PG13"][0]["target"] == "PG-13" and rated["pg"][0]["target"] == "PG"
    assert result["scan"]["suggestions"]["status"] == "ok"
