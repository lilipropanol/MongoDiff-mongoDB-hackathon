"""One MongoDB $facet scan, exact field checks, and bounded example projections."""


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


def analyze_collection(collection, new_schema: dict, changes: list[dict], examples: int = 3, old_schema: dict | None = None) -> dict:
    if not 0 <= examples <= 5:
        raise ValueError("examples must be between 0 and 5")
    invalid = {"$nor": [{"$jsonSchema": new_schema}]}
    reasons = reason_specs(new_schema)
    facets = {"total": [{"$count": "n"}], "failing": [{"$match": invalid}, {"$count": "n"}]}
    if old_schema:
        facets["preexisting"] = [{"$match": {"$nor": [{"$jsonSchema": old_schema}]}}, {"$count": "n"}]
        facets["newly_failing"] = [{"$match": {"$and": [{"$jsonSchema": old_schema}, invalid]}}, {"$count": "n"}]
    for i, reason in enumerate(reasons):
        match = {"$match": {"$and": [invalid, reason["query"]]}}
        facets[f"r{i}_count"] = [match, {"$count": "n"}]
        if examples:
            facets[f"r{i}_examples"] = [match, {"$limit": examples}, {"$project": {"_id": 1, reason["field"]: 1}}]
    unexplained = {"$and": [invalid, {"$nor": [r["query"] for r in reasons]}]} if reasons else invalid
    facets["unclassified"] = [{"$match": unexplained}, {"$count": "n"}]
    data = next(collection.aggregate([{"$facet": facets}], maxTimeMS=30000), {})

    def count(key):
        return data[key][0]["n"] if data.get(key) else 0

    output = []
    for i, spec in enumerate(reasons):
        if not count(f"r{i}_count"):
            continue
        docs = data.get(f"r{i}_examples", [])
        output.append({"field": spec["field"], "reason": spec["reason"], "count": count(f"r{i}_count"),
                       "example_ids": [str(d["_id"]) for d in docs], "examples": docs})
    return {"total": count("total"), "failing": count("failing"), "preexisting": count("preexisting"),
            "newly_failing": count("newly_failing"), "unclassified": count("unclassified"), "reasons": output}
