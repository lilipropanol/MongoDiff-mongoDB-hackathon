"""Read-only measurement of a live collection, with independent cross-checks, for numbers you can quote.

    .venv/bin/python -m schema_guard.engine.measure                 # uses MONGODB_URI etc. from .env
    .venv/bin/python -m schema_guard.engine.measure --runs 3 --old a.json --new b.json

Runs the impact scan several times (counts must not change between runs), cross-checks every headline
number against MongoDB's own count_documents queries, confirms example ids exist and really fail, and
writes a dated JSON result under reports/. Never writes to MongoDB and never prints or saves the URI.
Exit code: 0 all checks passed, 1 a check failed, 2 configuration or connection problem.
"""

import argparse
import json
import os
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from .diff import compare
from .impact import analyze_collection
from .models import load_collection_validator, load_model
from .translator import SchemaTranslator

ROOT = Path(__file__).resolve().parents[2]


def _stable(result):
    """The scan result without fields that legitimately differ between runs."""
    clean = deepcopy(result)
    clean.get("scan", {}).pop("duration_ms", None)
    return json.loads(json.dumps(clean, default=str, sort_keys=True))


def _check(name, passed, detail=""):
    return {"check": name, "passed": bool(passed), "detail": detail}


def measure(collection, old_schema: dict, new_schema: dict, runs: int = 2, examples: int = 3) -> dict:
    """Scan `runs` times and cross-check against MongoDB. Read-only; usable on any pymongo collection."""
    if runs < 1:
        raise ValueError("runs must be at least 1")
    changes = compare(old_schema, new_schema)
    results = [analyze_collection(collection, new_schema, changes, examples, old_schema) for _ in range(runs)]
    first = results[0]
    invalid = {"$nor": [{"$jsonSchema": new_schema}]}
    checks = [
        _check("reproducible across runs", all(_stable(r) == _stable(first) for r in results[1:]),
               f"{runs} run(s)"),
        _check("total == count_documents({})", first["total"] == collection.count_documents({})),
        _check("failing == count_documents($nor new schema)", first["failing"] == collection.count_documents(invalid)),
        _check("preexisting == count_documents($nor old schema)",
               first["preexisting"] == collection.count_documents({"$nor": [{"$jsonSchema": old_schema}]})),
        _check("newly_failing == count_documents(old AND NOT new)",
               first["newly_failing"] == collection.count_documents({"$and": [{"$jsonSchema": old_schema}, invalid]})),
        _check("every reason count <= failing", all(r["count"] <= first["failing"] for r in first["reasons"])),
        _check("new + preexisting split adds up",
               all(r.get("count_newly", 0) + r.get("count_preexisting", 0) == r["count"] for r in first["reasons"])),
        _check("distinct value counts <= reason count",
               all(sum(v["count"] for v in r.get("distinct_values", [])) <= r["count"] for r in first["reasons"])),
    ]
    example_ids = [doc["_id"] for reason in first["reasons"] for doc in reason["examples"]]
    failing_examples = collection.count_documents({"$and": [{"_id": {"$in": example_ids}}, invalid]}) if example_ids else 0
    checks.append(_check("example ids exist and fail the new schema", failing_examples == len(set(map(repr, example_ids))),
                         f"{failing_examples}/{len(set(map(repr, example_ids)))}"))
    try:
        version = collection.database.client.server_info().get("version")
    except PyMongoError:
        version = None
    try:
        _, validator = load_collection_validator(collection)
    except (PyMongoError, ValueError) as exc:
        validator = {"error": type(exc).__name__}
    return {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "database": collection.database.name, "collection": collection.name,
        "server_version": version, "current_validator": validator,
        "runs": runs, "durations_ms": [r["scan"]["duration_ms"] for r in results],
        "all_checks_passed": all(c["passed"] for c in checks), "checks": checks,
        "result": first,
    }


def summary(measurement: dict) -> str:
    result = measurement["result"]
    lines = [f"{measurement['database']}.{measurement['collection']} on MongoDB {measurement['server_version'] or 'unknown'}"
             f" — measured {measurement['measured_at']}",
             f"  {result['failing']:,} of {result['total']:,} documents fail the new schema"
             f" ({result['newly_failing']:,} newly affected, {result['preexisting']:,} violate the old schema)",
             f"  scan time per run (ms): {', '.join(map(str, measurement['durations_ms']))}"]
    for reason in result["reasons"][:15]:
        lines.append(f"  {reason['path']}: {reason['count']:,} {reason['reason']}")
    lines.append("Checks:")
    lines += [f"  [{'PASS' if c['passed'] else 'FAIL'}] {c['check']}{' (' + c['detail'] + ')' if c['detail'] else ''}"
              for c in measurement["checks"]]
    return "\n".join(lines)


def main(argv=None) -> int:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(prog="schema_guard.engine.measure", description=__doc__.splitlines()[0])
    parser.add_argument("--database", default=os.getenv("MONGODB_DATABASE", "sample_mflix"))
    parser.add_argument("--collection", default=os.getenv("MONGODB_COLLECTION", "movies"))
    parser.add_argument("--old", default=os.getenv("GUARD_OLD_MODEL", str(ROOT / "examples/models_old.py") + ":Movie"))
    parser.add_argument("--new", default=os.getenv("GUARD_NEW_MODEL", str(ROOT / "examples/models_new.py") + ":Movie"))
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--out", default=None, help="JSON output path (default reports/engine-measure-<timestamp>.json)")
    args = parser.parse_args(argv)
    uri = os.getenv("MONGODB_URI")
    if not uri:
        print("measure: set MONGODB_URI in .env (use a read-only database user)", file=sys.stderr)
        return 2
    try:
        translator = SchemaTranslator()
        old_schema, new_schema = translator.translate(load_model(args.old)), translator.translate(load_model(args.new))
        with MongoClient(uri, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000, socketTimeoutMS=35000) as client:
            measurement = measure(client[args.database][args.collection], old_schema, new_schema, runs=args.runs)
    except PyMongoError:
        print("measure: MongoDB request failed. Check connectivity, permissions and the 30-second scan limit.", file=sys.stderr)
        return 2
    except (TypeError, ValueError, OSError) as exc:
        print(f"measure: {exc}", file=sys.stderr)
        return 2
    measurement["models"] = {"old": args.old, "new": args.new}
    text = json.dumps(measurement, indent=2, default=str)
    if uri in text:
        print("measure: refusing to save output that contains the database URI", file=sys.stderr)
        return 2
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(args.out) if args.out else ROOT / "reports" / f"engine-measure-{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n")
    print(summary(measurement))
    print(f"Saved {out}")
    return 0 if measurement["all_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
