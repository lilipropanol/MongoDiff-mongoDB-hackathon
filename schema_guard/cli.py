"""Read-only CLI sharing the same report and impact analysis as the dashboard."""

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from .diff import compare
from .impact import analyze_collection
from .models import load_model
from .report import build_report
from .translator import SchemaTranslator


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="schema-guard", description="Preview Pydantic model changes against MongoDB data")
    parser.add_argument("--uri", default=os.getenv("MONGODB_URI"))
    parser.add_argument("--database", default=os.getenv("MONGODB_DATABASE", "sample_mflix"))
    parser.add_argument("--collection", default=os.getenv("MONGODB_COLLECTION", "movies"))
    parser.add_argument("--old", default="examples/models_old.py:Movie", help="Old model as FILE.py:Class")
    parser.add_argument("--new", default="examples/models_new.py:Movie", help="New model as FILE.py:Class")
    parser.add_argument("--output", default="reports/latest.json")
    parser.add_argument("--examples", type=int, default=3, choices=range(0, 6))
    parser.add_argument("--demo", action="store_true", help="Analyze local fixtures without MongoDB")
    args = parser.parse_args()
    if not args.demo and not args.uri:
        parser.error("provide --uri, set MONGODB_URI, or use --demo")
    try:
        translator = SchemaTranslator()
        old_schema = translator.translate(load_model(args.old))
        new_schema = translator.translate(load_model(args.new))
        changes = compare(old_schema, new_schema)
        if args.demo:
            from .demo import SEED, analyze_demo
            impact = analyze_demo(SEED, old_schema, new_schema)
        else:
            with MongoClient(args.uri, serverSelectionTimeoutMS=5000, socketTimeoutMS=35000) as client:
                impact = analyze_collection(client[args.database][args.collection], new_schema, changes, args.examples, old_schema)
        report = build_report(impact, changes, old_schema, new_schema, "schema_guard_demo" if args.demo else args.database, args.collection, "demo" if args.demo else "atlas")
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, default=str) + "\n")
        pct = (impact["failing"] / impact["total"] * 100) if impact["total"] else 0
        print(f"{'DEMO: ' if args.demo else ''}{impact['failing']:,} of {impact['total']:,} documents fail the new stored schema ({pct:.1f}%).")
        print(f"Newly affected: {impact['newly_failing']:,}; violations of old schema: {impact['preexisting']:,}")
        for reason in impact["reasons"]:
            print(f"  {reason['field']}: {reason['count']:,} {reason['reason']}")
        print(f"Report written to {output}")
    except PyMongoError:
        print("schema-guard: MongoDB scan failed. Check connectivity, permissions and the 30-second scan limit.", file=sys.stderr)
        raise SystemExit(2)
    except (TypeError, ValueError, OSError, RecursionError) as exc:
        print(f"schema-guard: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
