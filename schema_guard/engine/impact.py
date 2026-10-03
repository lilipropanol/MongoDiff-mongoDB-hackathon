"""Read-only MongoDB impact analysis: $jsonSchema counts, field-level reasons, nested paths and bounded value summaries.

Pass 1 counts totals, drift and missing-default warnings over every document. Pass 2 starts with
$match on the failing documents (filter early: $facet sends every input document to every branch) and
explains only those. Nested checks are aggregation expressions inside $expr so that MongoDB's implicit
array traversal in query paths ("a.b", {$type: ...}) cannot confuse an array with its elements.
"""

import os
import time

from pymongo.errors import PyMongoError

EXAMPLE_ARRAY_LIMIT = 5
EXAMPLE_STRING_LIMIT = 200
DISTINCT_STRING_LIMIT = 80
SCALAR_TYPES = ["string", "int", "long", "double", "decimal", "bool", "date", "null", "objectId"]
DISTINCT_REASONS = ("wrong_type", "value_not_allowed")
MAX_VERSIONS = 20


def reason_specs(schema: dict) -> list[dict]:
    """Explain root fields, including existing violations of unchanged fields."""
    reasons = []
    required = set(schema.get("required", []))
    for field, rule in schema.get("properties", {}).items():
        if field in required:
            reasons.append({"field": field, "reason": "missing", "query": {field: {"$exists": False}}})
        types = rule.get("bsonType")
        types = ([types] if isinstance(types, str) else types) or []
        allows_null = "null" in types or ("enum" in rule and None in rule["enum"])
        if not allows_null:
            reasons.append({"field": field, "reason": "null_not_allowed", "query": {"$expr": {"$eq": [{"$type": f"${field}"}, "null"]}}})
        if types:
            non_null = [item for item in types if item != "null"]
            query = {"$expr": {"$not": [{"$in": [{"$type": f"${field}"}, non_null + ["missing", "null"]]}]}}
            reasons.append({"field": field, "reason": "wrong_type", "query": query})
        if "enum" in rule:
            query = {"$and": [
                {field: {"$exists": True}},
                {"$expr": {"$ne": [{"$type": f"${field}"}, "null"]}},
                {"$nor": [{"$jsonSchema": {"properties": {field: rule}}}]},
            ]}
            reasons.append({"field": field, "reason": "value_not_allowed", "query": query})
        if "properties" in rule or "items" in rule:
            reasons.append({"field": field, "reason": "nested_or_array_constraint", "query": {"$and": [
                {"$expr": {"$in": [{"$type": f"${field}"}, types]}},
                {"$nor": [{"$jsonSchema": {"properties": {field: rule}}}]},
            ]}})
    return reasons


# ---------------------------------------------------------------------------
# Nested and array-element reasons
# ---------------------------------------------------------------------------

def _types(rule) -> list[str]:
    types = rule.get("bsonType", [])
    return [types] if isinstance(types, str) else list(types)


def _allows_null(rule) -> bool:
    return "null" in _types(rule) or None in rule.get("enum", [])


def _and(*conditions):
    conditions = [c for c in conditions if c is not None]
    return conditions[0] if len(conditions) == 1 else {"$and": conditions}


def _any_element(array_value, var, condition):
    """True when any element of array_value satisfies condition; non-arrays behave as empty arrays."""
    return {"$anyElementTrue": [{"$map": {
        "input": {"$cond": [{"$isArray": array_value}, array_value, []]},
        "as": var,
        "in": condition,
    }}]}


def _field_checks(root, path, value, rule, required, guard, location):
    """Reasons for one value position. guard must be true for the position to exist (e.g. parent is an object)."""
    value_type = {"$type": value}
    specs = []

    def add(reason, condition, distinct=False):
        specs.append({"field": root, "path": path, "location": location, "reason": reason, "rule": rule,
                      "expr": _and(guard, condition), "value": value if distinct else None})

    if required:
        add("missing", {"$eq": [value_type, "missing"]})
    if not _allows_null(rule):
        add("null_not_allowed", {"$eq": [value_type, "null"]})
    types = _types(rule)
    if types:
        allowed = [t for t in types if t != "null"] + ["missing", "null"]
        add("wrong_type", {"$not": [{"$in": [value_type, allowed]}]}, distinct=True)
    if "enum" in rule:
        allowed_values = [v for v in rule["enum"] if v is not None]
        add("value_not_allowed", {"$and": [
            {"$not": [{"$in": [value_type, ["missing", "null"]]}]},
            {"$not": [{"$in": [value, {"$literal": allowed_values}]}]},
        ]}, distinct=True)
    return specs


def _deep(specs, root, path, value, rule, depth):
    if "properties" in rule:
        parent_is_object = {"$eq": [{"$type": value}, "object"]}
        required = set(rule.get("required", []))
        for key, child in rule["properties"].items():
            child_path, child_value = f"{path}.{key}", f"{value}.{key}"
            location = "array_element" if "[]" in child_path else "nested"
            specs.extend(_field_checks(root, child_path, child_value, child, key in required, parent_is_object, location))
            _deep(specs, root, child_path, child_value, child, depth)
    if "items" in rule:
        var = f"e{depth}"
        element, element_path = f"$${var}", f"{path}[]"
        inner = _field_checks(root, element_path, element, rule["items"], False, None, "array_element")
        _deep(inner, root, element_path, element, rule["items"], depth + 1)
        array = {"$cond": [{"$isArray": value}, value, []]}
        for spec in inner:
            # Offending element values for one level of array (not arrays nested inside arrays): $filter then
            # $map, so the distinct-value facet only $unwinds the bad elements instead of every element.
            if spec["value"] and "$$" not in value:
                spec["values_expr"] = {"$map": {"input": {"$filter": {"input": array, "as": var, "cond": spec["expr"]}},
                                                "as": var, "in": spec["value"]}}
            spec["expr"] = _any_element(value, var, spec["expr"])
            spec["value"] = None
            spec["location"] = "array_element"
        specs.extend(inner)


def deep_reason_specs(schema: dict) -> list[dict]:
    """Reasons below root fields: nested object fields (a.b) and array elements (a[], a[].b).

    Every spec keeps "field" as the root field (fixes.make_plan looks it up in the root properties)
    and adds "path" with the exact location.
    """
    specs = []
    for field, rule in schema.get("properties", {}).items():
        _deep(specs, field, field, f"${field}", rule, 0)
    return specs


def warning_specs(schema: dict) -> list[dict]:
    """Optional fields (they have a default in the model) that may be missing in storage; not array elements."""
    specs = []

    def walk(rule, path, value, guard):
        required = set(rule.get("required", []))
        for key, child in rule.get("properties", {}).items():
            child_path = f"{path}.{key}" if path else key
            child_value = f"{value}.{key}" if value else f"${key}"
            if key not in required:
                specs.append({"field": child_path.split(".")[0], "path": child_path,
                              "expr": _and(guard, {"$eq": [{"$type": child_value}, "missing"]})})
            if "properties" in child:
                walk(child, child_path, child_value, {"$eq": [{"$type": child_value}, "object"]})

    walk(schema, "", "", None)
    return specs


# ---------------------------------------------------------------------------
# Explanations and value summaries
# ---------------------------------------------------------------------------

def explain(reason: str, path: str, rule: dict, distinct_values=None) -> str:
    types = [t for t in _types(rule) if t != "null"]
    if reason == "missing":
        return f"`{path}` is required by the new model but absent from the stored document."
    if reason == "null_not_allowed":
        return f"`{path}` is stored as null, but the new model does not allow null."
    if reason == "wrong_type":
        text = f"`{path}` is stored with a BSON type the new model does not accept (expected {', '.join(types)})."
        seen = {v["bson_type"] for v in (distinct_values or [])}
        if "string" in seen and set(types) & {"int", "long", "double", "decimal"}:
            text += (" MongoDB checks BSON types strictly: text such as \"118\" fails even though Pydantic's"
                     " default (lax) mode would convert it when reading.")
        if "double" in seen and set(types) <= {"int", "long"}:
            text += " A double such as 90.0 is not an int in BSON, although Pydantic accepts it."
        if "array" in seen:
            text += " Some documents store an array here instead of a single value."
        return text
    if reason == "value_not_allowed":
        allowed = ", ".join(repr(v) for v in rule.get("enum", []) if v is not None)
        return f"`{path}` holds a value outside the allowed set ({allowed})."
    if reason == "nested_or_array_constraint":
        return f"Something inside `{path}` violates the nested rules; see the nested issues for exact paths."
    return f"`{path}`: {reason}."


def _py_bson_type(value) -> str:
    from datetime import datetime
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
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
    return type(value).__name__


def _finish_value(value, bson_type, count, location):
    entry = {"value": value if bson_type in SCALAR_TYPES else None, "bson_type": bson_type, "count": count,
             "mappable": bson_type == "string" and location == "field"}
    if isinstance(entry["value"], str) and len(entry["value"]) > DISTINCT_STRING_LIMIT:
        entry["value"] = entry["value"][:DISTINCT_STRING_LIMIT]
        entry["truncated"] = True
    return entry


def summarize_values(values, limit: int = 10, location: str = "field") -> dict:
    """Pure-Python equivalent of the distinct-value facet, for adapters that hold documents in memory."""
    groups = {}
    for value in values:
        bson_type = _py_bson_type(value)
        key = (bson_type, repr(value) if bson_type in SCALAR_TYPES else None)
        groups.setdefault(key, [value if bson_type in SCALAR_TYPES else None, 0])[1] += 1
    ordered = sorted(groups.items(), key=lambda item: (-item[1][1], item[0][0], str(item[1][0])))
    entries = [_finish_value(v, t, n, location) for (t, _), (v, n) in ordered[:limit]]
    return {"distinct_values": entries, "distinct_value_count": len(groups), "distinct_values_limited": len(groups) > limit}


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def _count_stage(match):
    return [{"$match": match}, {"$count": "n"}]


def _example_projection(field):
    ref = f"${field}"
    bounded = {"$switch": {"branches": [
        {"case": {"$isArray": ref}, "then": {"$slice": [ref, EXAMPLE_ARRAY_LIMIT]}},
        {"case": {"$eq": [{"$type": ref}, "string"]}, "then": {"$substrCP": [ref, 0, EXAMPLE_STRING_LIMIT]}},
    ], "default": ref}}
    return {"$project": {"_id": 1, field: bounded}}


def _scalar_or_null(value):
    return {"$cond": [{"$in": [{"$type": value}, SCALAR_TYPES]}, value, None]}


def _distinct_stages(spec):
    """Stages grouping offending values by (value, BSON type); counts are documents containing the value."""
    if spec["value"]:
        value = spec["value"]
        return [{"$group": {"_id": {"v": _scalar_or_null(value), "t": {"$type": value}}, "n": {"$sum": 1}}}]
    # Array elements: unwind only the offending elements, count each document once per value.
    return [{"$project": {"_v": spec["values_expr"]}}, {"$unwind": "$_v"},
            {"$group": {"_id": {"v": _scalar_or_null("$_v"), "t": {"$type": "$_v"}, "d": "$_id"}}},
            {"$group": {"_id": {"v": "$_id.v", "t": "$_id.t"}, "n": {"$sum": 1}}}]


def _version_group(field):
    return [{"$group": {"_id": f"${field}", "n": {"$sum": 1}}}, {"$sort": {"n": -1, "_id": 1}}, {"$limit": MAX_VERSIONS}]


def _versioning(field, data, changes):
    """Per-version breakdown and a version-bump recommendation (MongoDB schema versioning pattern)."""
    rows = {}
    for key, column in (("versions_total", "total"), ("versions_failing", "failing"), ("versions_newly", "newly_failing")):
        for group in data.get(key, []):
            rows.setdefault(repr(group["_id"]), {"version": group["_id"], "total": 0, "failing": 0, "newly_failing": 0})[column] = group["n"]
    versions = sorted(rows.values(), key=lambda row: (-row["total"], str(row["version"])))
    versioned = any(row["version"] is not None for row in versions)
    breaking = list(dict.fromkeys(c["field"] for c in changes or [] if c.get("compatibility") == "breaking"))
    if not breaking:
        message = "Only backward-compatible changes: no schema version bump is needed."
    elif versioned:
        message = (f"{len(breaking)} breaking change(s). Bump `{field}` for the new shape and migrate older versions;"
                   " failing documents per version are listed.")
    else:
        message = (f"{len(breaking)} breaking change(s), and documents have no `{field}` field. Consider adding one so old"
                   " and new shapes can coexist while you migrate (MongoDB schema versioning pattern).")
    return {"field": field, "versioned": versioned, "versions": versions if versioned else [],
            "bump_recommended": bool(breaking), "breaking_changes": breaking, "message": message}


def _validate_limits(examples, distinct_limit, max_time_ms):
    if not 0 <= examples <= 5:
        raise ValueError("examples must be between 0 and 5")
    if not 0 <= distinct_limit <= 50:
        raise ValueError("distinct_limit must be between 0 and 50")
    if not 1000 <= max_time_ms <= 60000:
        raise ValueError("max_time_ms must be between 1000 and 60000")


def _collection_exists(collection):
    try:
        return bool(collection.database.list_collection_names(filter={"name": collection.name}))
    except (PyMongoError, AttributeError, TypeError):
        return None


def analyze_collection(collection, new_schema: dict, changes: list[dict], examples: int = 3, old_schema: dict | None = None,
                       *, distinct_limit: int = 10, max_time_ms: int = 30000, two_pass: bool = True,
                       version_field: str | None = None) -> dict:
    _validate_limits(examples, distinct_limit, max_time_ms)
    if version_field is None:
        version_field = os.getenv("GUARD_VERSION_FIELD", "schemaVersion")
    if version_field and (version_field.startswith("$") or "." in version_field):
        raise ValueError("version_field must be a plain top-level field name")
    started = time.monotonic()
    invalid = {"$nor": [{"$jsonSchema": new_schema}]}

    def within_failing(query):
        # In two-pass mode the pipeline already starts with $match: invalid.
        return query if two_pass else {"$and": [invalid, query]}

    root_specs = reason_specs(new_schema)
    deep_specs = deep_reason_specs(new_schema)
    warnings = warning_specs(new_schema)
    order = list(new_schema.get("properties", {}))
    specs = []
    for field in order:
        specs += [dict(s, path=field, location="field", rule=new_schema["properties"][field],
                       value=f"${field}" if s["reason"] in DISTINCT_REASONS else None)
                  for s in root_specs if s["field"] == field]
        specs += [s for s in deep_specs if s["field"] == field]

    totals = {"total": [{"$count": "n"}], "failing": _count_stage(invalid)}
    if old_schema:
        totals["preexisting"] = _count_stage({"$nor": [{"$jsonSchema": old_schema}]})
        totals["newly_failing"] = _count_stage({"$and": [{"$jsonSchema": old_schema}, invalid]})
    for i, warning in enumerate(warnings):
        totals[f"w{i}"] = _count_stage({"$expr": warning["expr"]})
    if version_field:
        totals["versions_total"] = _version_group(version_field)

    details = {}
    if version_field:
        details["versions_failing"] = [{"$match": within_failing({})}, *_version_group(version_field)]
        if old_schema:
            details["versions_newly"] = [{"$match": within_failing({"$jsonSchema": old_schema})}, *_version_group(version_field)]
    for i, spec in enumerate(specs):
        query = spec["query"] if "query" in spec else {"$expr": spec["expr"]}
        match = {"$match": within_failing(query)}
        details[f"r{i}_count"] = [match, {"$count": "n"}]
        if old_schema:
            details[f"r{i}_newly"] = [match, {"$match": {"$jsonSchema": old_schema}}, {"$count": "n"}]
        if examples:
            details[f"r{i}_examples"] = [match, {"$limit": examples}, _example_projection(spec["field"])]
        if (spec["value"] or spec.get("values_expr")) and distinct_limit:
            stages = _distinct_stages(spec)
            details[f"r{i}_values"] = [match, *stages, {"$sort": {"n": -1, "_id.t": 1, "_id.v": 1}}, {"$limit": distinct_limit}]
            details[f"r{i}_value_count"] = [match, *stages, {"$count": "n"}]
    unexplained = {"$nor": [s["query"] for s in root_specs]} if root_specs else {}
    details["unclassified"] = [{"$match": within_failing(unexplained)}, {"$count": "n"}]

    if two_pass:
        data = next(collection.aggregate([{"$facet": totals}], maxTimeMS=max_time_ms), {})
        data.update(next(collection.aggregate([{"$match": invalid}, {"$facet": details}], maxTimeMS=max_time_ms), {}))
    else:
        data = next(collection.aggregate([{"$facet": {**totals, **details}}], maxTimeMS=max_time_ms), {})

    def count(key):
        return data[key][0]["n"] if data.get(key) else 0

    output = []
    for i, spec in enumerate(specs):
        n = count(f"r{i}_count")
        if not n:
            continue
        docs = data.get(f"r{i}_examples", [])
        reason = {"field": spec["field"], "reason": spec["reason"], "count": n,
                  "example_ids": [str(d["_id"]) for d in docs], "examples": docs,
                  "path": spec["path"], "location": spec["location"]}
        if old_schema:
            reason["count_newly"] = count(f"r{i}_newly")
            reason["count_preexisting"] = n - reason["count_newly"]
        if f"r{i}_values" in data:
            values = [_finish_value(g["_id"].get("v"), g["_id"]["t"], g["n"], spec["location"]) for g in data[f"r{i}_values"]]
            total_values = count(f"r{i}_value_count")
            reason.update(distinct_values=values, distinct_value_count=total_values,
                          distinct_values_limited=total_values > len(values))
        reason["explanation"] = explain(spec["reason"], spec["path"], spec["rule"], reason.get("distinct_values"))
        output.append(reason)

    warning_output = []
    for i, warning in enumerate(warnings):
        n = count(f"w{i}")
        if n:
            warning_output.append({"field": warning["field"], "path": warning["path"], "kind": "missing_defaulted_field", "count": n,
                                   "message": (f"`{warning['path']}` is missing in {n} stored document(s). The model fills its default when"
                                               " reading, but MongoDB queries, indexes and validators see the field as absent.")})

    result = {"total": count("total"), "failing": count("failing"), "preexisting": count("preexisting"),
              "newly_failing": count("newly_failing"), "unclassified": count("unclassified"), "reasons": output,
              "warnings": warning_output,
              "scan": {"duration_ms": round((time.monotonic() - started) * 1000), "max_time_ms": max_time_ms,
                       "examples": examples, "distinct_limit": distinct_limit, "two_pass": two_pass,
                       "collection_exists": _collection_exists(collection), "snapshot": False}}
    if version_field:
        result["versioning"] = _versioning(version_field, data, changes)
    from . import suggest
    suggest.maybe_enrich(result, new_schema, changes, collection=collection)
    return result
