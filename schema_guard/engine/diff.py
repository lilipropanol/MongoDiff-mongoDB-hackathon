"""Structural schema changes, including nested object fields (a.b) and array elements (a[], a[].b).

Root entries keep the starter's shape. Nested entries use the full path as "field" and add "parent" (the root field).
"""


def compare(old_schema: dict, new_schema: dict, prefix: str = "") -> list[dict]:
    changes = _compare_objects(old_schema, new_schema, prefix, None)
    for change in changes:
        change["compatibility"], change["compatibility_reason"] = classify(change)
    return changes


def classify(change: dict) -> tuple[str, str]:
    """Breaking vs backward-compatible, following MongoDB's schema-versioning guidance."""
    kind = change["kind"]
    if kind == "added":
        if change.get("required"):
            return "breaking", "New required field: existing documents need a backfill or a default before validation."
        return "compatible", "New optional field: old documents and old code are unaffected."
    if kind == "removed":
        return "breaking", "Removed field: stored documents still validate, but code that reads it must change (consider a schema version bump)."
    if kind == "became_required":
        return "breaking", "Field became required: documents without it fail until backfilled."
    if kind == "became_optional":
        return "compatible", "Relaxed validation: required field became optional."
    details = change.get("details", {})
    narrowed = (details.get("types_removed") or details.get("enum_removed") or "restricted_to" in details
                or details.get("nullable", {}).get("new") is False)
    if narrowed:
        return "breaking", "Type or allowed values narrowed: existing values may fail; plan a migration or schema version bump."
    if details:
        return "compatible", "Type or allowed values widened: existing values still validate."
    return "breaking", "Nested structure changed; see the nested entries for details."


def _compare_objects(old_schema, new_schema, prefix, root):
    old_props, new_props = old_schema.get("properties", {}), new_schema.get("properties", {})
    old_req, new_req = set(old_schema.get("required", [])), set(new_schema.get("required", []))
    changes = []
    for field in sorted(old_props.keys() | new_props.keys()):
        path = f"{prefix}.{field}" if prefix else field
        top = root or path
        extra = {"parent": root} if root else {}
        if field not in old_props:
            changes.append({"field": path, "kind": "added", "new": new_props[field], "required": field in new_req, **extra})
        elif field not in new_props:
            changes.append({"field": path, "kind": "removed", "old": old_props[field], **extra})
        else:
            before, after = old_props[field], new_props[field]
            if _canonical(before) != _canonical(after):
                changes.append({"field": path, "kind": "type_or_constraint_changed", "old": before, "new": after,
                                "details": _details(before, after), **extra})
                changes.extend(_nested(before, after, path, top))
            if field not in old_req and field in new_req:
                changes.append({"field": path, "kind": "became_required", "new": after, **extra})
            if field in old_req and field not in new_req:
                changes.append({"field": path, "kind": "became_optional", "new": after, **extra})
    return changes


def _nested(before, after, path, root):
    changes = []
    if "properties" in before and "properties" in after:
        changes.extend(_compare_objects(before, after, path, root))
    if "items" in before and "items" in after and _canonical(before["items"]) != _canonical(after["items"]):
        item_path = f"{path}[]"
        changes.append({"field": item_path, "kind": "type_or_constraint_changed", "old": before["items"],
                        "new": after["items"], "details": _details(before["items"], after["items"]), "parent": root})
        changes.extend(_nested(before["items"], after["items"], item_path, root))
    return changes


def _types(rule):
    types = rule.get("bsonType", [])
    return [types] if isinstance(types, str) else list(types)


def _nullable(rule):
    return "null" in _types(rule) or None in rule.get("enum", [])


def _canonical(value):
    """Compare like MongoDB: numbers by value (1 == 1.0), but booleans never equal numbers (Python says True == 1)."""
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, (int, float)):
        return ("number", value)
    if isinstance(value, dict):
        return ("object", tuple((k, _canonical(v)) for k, v in value.items()))
    if isinstance(value, list):
        return ("array", tuple(_canonical(v) for v in value))
    return (type(value).__name__, value)


def _contains(values, value):
    return any(_canonical(item) == _canonical(value) for item in values)


def _details(before, after) -> dict:
    details = {}
    old_types, new_types = _types(before), _types(after)
    if old_types and new_types:
        added = [t for t in new_types if t not in old_types and t != "null"]
        removed = [t for t in old_types if t not in new_types and t != "null"]
        if added:
            details["types_added"] = added
        if removed:
            details["types_removed"] = removed
    old_enum = [v for v in before.get("enum", []) if v is not None]
    new_enum = [v for v in after.get("enum", []) if v is not None]
    if "enum" in before and "enum" in after:
        added = [v for v in new_enum if not _contains(old_enum, v)]
        removed = [v for v in old_enum if not _contains(new_enum, v)]
        if added:
            details["enum_added"] = added
        if removed:
            details["enum_removed"] = removed
    elif "enum" in after:
        details["restricted_to"] = new_enum
    elif "enum" in before:
        details["enum_lifted"] = True
    if _nullable(before) != _nullable(after):
        details["nullable"] = {"old": _nullable(before), "new": _nullable(after)}
    return details
