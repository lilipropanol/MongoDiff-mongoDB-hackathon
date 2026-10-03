"""Structural schema changes; intentionally reports supported direct field changes."""


def compare(old_schema: dict, new_schema: dict, prefix: str = "") -> list[dict]:
    old_props, new_props = old_schema.get("properties", {}), new_schema.get("properties", {})
    old_req, new_req = set(old_schema.get("required", [])), set(new_schema.get("required", []))
    changes = []
    for field in sorted(old_props.keys() | new_props.keys()):
        path = f"{prefix}.{field}" if prefix else field
        if field not in old_props:
            changes.append({"field": path, "kind": "added", "new": new_props[field], "required": field in new_req})
        elif field not in new_props:
            changes.append({"field": path, "kind": "removed", "old": old_props[field]})
        else:
            before, after = old_props[field], new_props[field]
            if before != after:
                changes.append({"field": path, "kind": "type_or_constraint_changed", "old": before, "new": after})
            if field not in old_req and field in new_req:
                changes.append({"field": path, "kind": "became_required", "new": after})
    return changes
