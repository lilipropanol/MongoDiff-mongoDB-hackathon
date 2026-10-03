"""Isolated fixture adapter, not a replacement for MongoDB query semantics."""

from copy import deepcopy
from datetime import datetime
import re

from .impact import explain, reason_specs, summarize_values

SEED = [
    {"_id": "movie-001", "title": "The Quiet Harbour", "year": 2004, "runtime": 104, "rated": "PG"},
    {"_id": "movie-002", "title": "City in Motion", "year": 2012, "runtime": "118", "rated": "PG-13"},
    {"_id": "movie-003", "title": "Paper Planes", "year": 2008, "runtime": 96},
    {"_id": "movie-004", "title": "Winter Light", "year": 1999, "rated": "PG"},
    {"_id": "movie-005", "title": "A Long Way Home", "year": 2015, "runtime": None, "rated": "R"},
    {"_id": "movie-006", "title": "The Last Frame", "year": 2020, "runtime": "N/A", "rated": "NR"},
    {"_id": "movie-007", "title": "Small Worlds", "year": 2001, "runtime": 88, "rated": "G"},
    {"_id": "movie-008", "title": "Northern Line", "year": 2017, "runtime": 110, "rated": "PG13"},
    {"_id": "movie-009", "title": "Blue Horizon", "year": 2019, "runtime": 122},
    {"_id": "movie-010", "title": "After the Rain", "year": 2010, "runtime": 99, "rated": "PG"},
    {"_id": "movie-011", "title": "Open Roads", "year": 2006, "runtime": 107, "rated": "R"},
    {"_id": "movie-012", "title": "First Light", "year": 2022, "runtime": 101, "rated": "PG-13"},
]


def bson_type(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        if not -(2**63) <= value < 2**63:
            return "unsupported"
        return "int" if -(2**31) <= value < 2**31 else "long"
    if isinstance(value, float):
        return "double"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, datetime):
        return "date"
    return "unsupported"


def matches_schema(value, schema):
    types = schema.get("bsonType")
    if types and bson_type(value) not in (types if isinstance(types, list) else [types]):
        return False
    if "enum" in schema and not any(value == item and bson_type(value) == bson_type(item) for item in schema["enum"]):
        return False
    if isinstance(value, dict):
        if any(key not in value for key in schema.get("required", [])):
            return False
        return all(matches_schema(value[key], rule) for key, rule in schema.get("properties", {}).items() if key in value)
    if isinstance(value, list) and "items" in schema:
        return all(matches_schema(item, schema["items"]) for item in value)
    return True


def analyze_demo(documents, old_schema, new_schema):
    invalid = [d for d in documents if not matches_schema(d, new_schema)]
    reasons = []
    explained = set()
    for spec in reason_specs(new_schema):
        field, kind = spec["field"], spec["reason"]
        rule = new_schema["properties"][field]
        types = rule.get("bsonType", [])
        types = [types] if isinstance(types, str) else types

        def matches(doc):
            if kind == "missing":
                return field not in doc
            if field not in doc:
                return False
            value = doc[field]
            if kind == "null_not_allowed":
                return value is None
            if value is None:
                return False
            if kind == "wrong_type":
                return bson_type(value) not in types
            if kind == "value_not_allowed":
                return not matches_schema(value, rule)
            return bson_type(value) in types and not matches_schema(value, rule)

        affected = [d for d in invalid if matches(d)]
        if not affected:
            continue
        explained.update(d["_id"] for d in affected)
        examples = [{"_id": d["_id"], **({field: d[field]} if field in d else {})} for d in affected[:3]]
        reason = {"field": field, "path": field, "location": "field", "reason": kind,
                  "count": len(affected), "examples": examples, "example_ids": [d["_id"] for d in examples],
                  "count_newly": sum(matches_schema(d, old_schema) for d in affected),
                  "count_preexisting": sum(not matches_schema(d, old_schema) for d in affected)}
        if kind in ("wrong_type", "value_not_allowed"):
            reason.update(summarize_values([d[field] for d in affected]))
        reason["explanation"] = explain(kind, field, rule, reason.get("distinct_values"))
        reasons.append(reason)
    return {"total": len(documents), "failing": len(invalid), "reasons": reasons,
            "preexisting": sum(not matches_schema(d, old_schema) for d in documents),
            "newly_failing": sum(matches_schema(d, old_schema) and not matches_schema(d, new_schema) for d in documents),
            "unclassified": len({d["_id"] for d in invalid} - explained)}


def apply_demo_plan(documents, plan):
    result = deepcopy(documents)
    for op in plan["operations"]:
        field = op["field"]
        for doc in result:
            if op["kind"] == "default":
                missing = "$exists" in op["filter"].get(field, {})
                eligible = (field not in doc) if missing else (field in doc and doc[field] is None)
                if eligible:
                    doc[field] = op["update"]["$set"][field]
            elif op["kind"] == "mapping":
                before = op["filter"]["$expr"]["$eq"][1]["$literal"]
                if doc.get(field) == before:
                    doc[field] = op["update"]["$set"][field]
            elif op["kind"] == "convert":
                value = doc.get(field)
                if isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value):
                    converted = int(value)
                    if -(2**63) <= converted < 2**63:
                        doc[field] = converted
    return result
