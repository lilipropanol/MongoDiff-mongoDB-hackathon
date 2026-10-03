"""Stable report construction shared by the CLI, API, and demo adapter."""

from datetime import datetime, timezone
from uuid import uuid4


def build_report(impact: dict, changes: list[dict], old_schema: dict, new_schema: dict,
                 database: str, collection: str, source: str, session_id: str = "cli") -> dict:
    return {
        "id": str(uuid4()), "session_id": session_id, "run_at": datetime.now(timezone.utc).isoformat(),
        "source": source, "database": database, "collection": collection,
        "total_docs": impact["total"], "failing": impact["failing"],
        "preexisting": impact.get("preexisting", 0), "newly_failing": impact.get("newly_failing", 0),
        "unclassified": impact.get("unclassified", 0), "changes": changes, "reasons": impact["reasons"],
        "warnings": impact.get("warnings", []),
        "scan": impact.get("scan"),
        "versioning": impact.get("versioning"),
        "old_schema": old_schema, "new_schema": new_schema, "new_validator": {"$jsonSchema": new_schema},
        "notes": ["Issue counts overlap: one document can violate several fields.",
                  "Stored BSON types are checked strictly; Pydantic may coerce some values during reads."],
    }
