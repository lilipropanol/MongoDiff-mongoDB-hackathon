"""Reviewable plans only. Live MongoDB execution is a separate task."""

import hashlib
import json


def _schema_fingerprint(schema: dict) -> str:
    payload = json.dumps(schema, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def make_plan(report: dict, defaults: dict, mappings: dict) -> dict:
    operations, unresolved = [], []
    props = report["new_schema"].get("properties", {})
    from .demo import matches_schema
    for field, value in defaults.items():
        if field not in props:
            raise ValueError(f"Default refers to unknown field: {field}")
        if not matches_schema({field: value}, {"properties": {field: props[field]}}):
            raise ValueError(f"Default for {field} does not match the proposed stored schema")
    for field, pairs in mappings.items():
        if field not in props or not isinstance(pairs, dict):
            raise ValueError(f"Invalid value mapping for {field}")
        for target in pairs.values():
            if not matches_schema({field: target}, {"properties": {field: props[field]}}):
                raise ValueError(f"Mapped value for {field} does not match the proposed schema")
    for reason in report["reasons"]:
        field, kind = reason["field"], reason["reason"]
        rule = props[field]
        if kind in ("missing", "null_not_allowed") and field in defaults:
            query = {field: {"$exists": False}} if kind == "missing" else {"$expr": {"$eq": [{"$type": f"${field}"}, "null"]}}
            operations.append({"field": field, "kind": "default", "description": f"Set {field} to the reviewed default", "filter": query, "update": {"$set": {field: defaults[field]}}, "count": reason["count"]})
        elif kind == "wrong_type" and set(rule.get("bsonType", []) if isinstance(rule.get("bsonType"), list) else [rule.get("bsonType")]) == {"int", "long"}:
            operations.append({"field": field, "kind": "convert", "description": f"Convert integer text in {field}; preserve values that cannot convert", "filter": {"$expr": {"$eq": [{"$type": f"${field}"}, "string"]}},
                               "update": [{"$set": {field: {"$convert": {"input": f"${field}", "to": "long", "onError": f"${field}", "onNull": f"${field}"}}}}], "count": None})
            unresolved.append({"field": field, "reason": kind, "count": reason["count"], "message": "Only integer text is converted; verify remaining values after applying."})
        elif kind == "value_not_allowed" and mappings.get(field):
            unresolved.append({"field": field, "reason": kind, "count": reason["count"], "message": "Unmapped values remain for review."})
        else:
            unresolved.append({"field": field, "reason": kind, "count": reason["count"], "message": "Provide a default or mapping, or review the source document."})
    for field, pairs in mappings.items():
        for before, after in pairs.items():
            operations.append({"field": field, "kind": "mapping", "description": f"Map {field}: {before} → {after}", "filter": {"$expr": {"$eq": [f"${field}", {"$literal": before}]}}, "update": {"$set": {field: after}}, "count": None})
    script = ["// REVIEW ONLY — do not run on production without backup and approval.",
              f"const targetDb = db.getSiblingDB({json.dumps(report['database'])});",
              f"const movies = targetDb.getCollection({json.dumps(report['collection'])});"]
    for op in operations:
        script.append(f"// {op['description']}\nmovies.updateMany({json.dumps(op['filter'])}, {json.dumps(op['update'])});")
    return {"run_id": report["id"], "operations": operations, "unresolved": unresolved,
            "script": "\n\n".join(script), "live_execution_available": False,
            "execution_contract": {
                "requires_backup": True,
                "reviewed": True,
                "schema_fingerprint": {
                    "database": report.get("database"),
                    "collection": report.get("collection"),
                    "old_schema": _schema_fingerprint(report.get("old_schema", {})),
                    "new_schema": _schema_fingerprint(report.get("new_schema", {})),
                },
                "one_reviewed_plan_per_execution": True,
                "notes": [
                    "Plan generation is review-only until a live apply contract is approved.",
                    "Live writes require a durable backup and fresh verification scan before execution.",
                ],
            },
            "notes": ["Candidate operations are not a guarantee that all affected documents are repairable.", "Live writes, backups, rollback, and validator application require further implementation."]}
