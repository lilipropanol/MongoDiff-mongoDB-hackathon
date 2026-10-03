"""Local dashboard API. Atlas credentials and trusted model paths stay on the server."""

from copy import deepcopy
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
from threading import RLock
from uuid import UUID, uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from .demo import SEED, analyze_demo, apply_demo_plan
from .diff import compare
from .fixes import make_plan
from .impact import analyze_collection
from .models import load_model
from .report import build_report
from .translator import SchemaTranslator

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
app = FastAPI(title="Atlas Schema Guard", version="0.1.0")
lock = RLock()
sessions = {}
plans = {}
logger = logging.getLogger(__name__)


class RunRequest(BaseModel):
    session_id: UUID
    source: str = Field(default="demo", pattern="^(demo|atlas)$")


class PlanRequest(BaseModel):
    session_id: UUID
    defaults: dict = Field(default_factory=dict)
    mappings: dict[str, dict] = Field(default_factory=dict)


class ApplyRequest(BaseModel):
    session_id: UUID
    plan_id: UUID


def report_dir():
    path = Path(os.getenv("GUARD_REPORT_DIR", str(ROOT / "reports")))
    path.mkdir(parents=True, exist_ok=True)
    return path


def schemas(source):
    # HTTP clients cannot submit executable Python or arbitrary file paths.
    old_spec = os.getenv("GUARD_OLD_MODEL", str(ROOT / "examples/models_old.py") + ":Movie") if source == "atlas" else str(ROOT / "examples/models_old.py") + ":Movie"
    new_spec = os.getenv("GUARD_NEW_MODEL", str(ROOT / "examples/models_new.py") + ":Movie") if source == "atlas" else str(ROOT / "examples/models_new.py") + ":Movie"
    translator = SchemaTranslator()
    old, new = translator.translate(load_model(old_spec)), translator.translate(load_model(new_spec))
    return old, new, old_spec, new_spec


def save_report(report):
    # Do not include URI or credentials in artifacts or API responses.
    serial = json.loads(json.dumps(report, default=str))
    path = report_dir() / f"{report['id']}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(serial, indent=2) + "\n")
    tmp.replace(path)
    return serial


def read_report(run_id, session_id):
    path = report_dir() / f"{run_id}.json"
    if not path.exists():
        raise HTTPException(404, "Run not found. Run an analysis first.")
    report = json.loads(path.read_text())
    if report.get("session_id") != str(session_id):
        raise HTTPException(404, "Run not found in this session.")
    return report


def run_analysis(session_id, source):
    old, new, old_spec, new_spec = schemas(source)
    changes = compare(old, new)
    if source == "demo":
        session = sessions.setdefault(str(session_id), {"documents": deepcopy(SEED), "latest_run": None})
        impact = analyze_demo(session["documents"], old, new)
        database, collection = "schema_guard_demo", "movies"
    else:
        uri = os.getenv("MONGODB_URI")
        if not uri:
            raise HTTPException(409, "Atlas is not configured. Set MONGODB_URI in the server .env and restart it.")
        database, collection = os.getenv("MONGODB_DATABASE", "sample_mflix"), os.getenv("MONGODB_COLLECTION", "movies")
        with MongoClient(uri, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000, socketTimeoutMS=35000) as client:
            impact = analyze_collection(client[database][collection], new, changes, old_schema=old)
    report = build_report(impact, changes, old, new, database, collection, source, str(session_id))
    report["model_sources"] = {"old": Path(old_spec.rsplit(":", 1)[0]).read_text(), "new": Path(new_spec.rsplit(":", 1)[0]).read_text()}
    saved = save_report(report)
    if source == "demo":
        session["latest_run"] = saved["id"]
    return saved


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/config")
def config():
    return {"atlas_configured": bool(os.getenv("MONGODB_URI")), "database": os.getenv("MONGODB_DATABASE", "sample_mflix"),
            "collection": os.getenv("MONGODB_COLLECTION", "movies"), "live_apply_available": False}


@app.post("/api/analyze")
def analyze(request: RunRequest):
    try:
        if request.source == "demo":
            with lock:
                return run_analysis(request.session_id, request.source)
        return run_analysis(request.session_id, request.source)
    except PyMongoError:
        logger.warning("MongoDB scan failed (connection, permissions, query, or scan timeout)")
        raise HTTPException(502, "MongoDB scan failed. Check connectivity, collection permissions, and server logs. The scan has a 30-second limit.")
    except (ValueError, TypeError, OSError, RecursionError) as exc:
        raise HTTPException(422, f"Model or report configuration error: {exc}")


@app.get("/api/runs")
def history(session_id: UUID):
    reports = []
    for path in sorted(report_dir().glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:200]:
        try:
            report = json.loads(path.read_text())
            if report.get("session_id") == str(session_id) and "id" in report:
                reports.append(report)
        except (json.JSONDecodeError, OSError):
            continue
    return reports[:30]


@app.post("/api/runs/{run_id}/plan")
def plan(run_id: UUID, request: PlanRequest):
    report = read_report(run_id, request.session_id)
    try:
        result = make_plan(report, request.defaults, request.mappings)
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc))
    result["id"] = str(uuid4())
    result["session_id"] = str(request.session_id)
    with lock:
        plans[result["id"]] = result
    return result


@app.post("/api/demo/apply")
def demo_apply(request: ApplyRequest):
    with lock:
        candidate = plans.get(str(request.plan_id))
        if not candidate or candidate["session_id"] != str(request.session_id):
            raise HTTPException(404, "Plan not found. Preview a plan again.")
        report = read_report(candidate["run_id"], request.session_id)
        if report["source"] != "demo":
            raise HTTPException(403, "This endpoint only modifies demo fixtures. Atlas execution is not implemented.")
        state = sessions.get(str(request.session_id))
        if not state or state["latest_run"] != report["id"]:
            raise HTTPException(409, "The plan is stale. Run analysis and preview the plan again.")
        previous = deepcopy(state["documents"])
        state["documents"] = apply_demo_plan(previous, candidate)
        try:
            result = run_analysis(request.session_id, "demo")
        except Exception:
            state["documents"] = previous
            raise
        state["backup"] = previous
        plans.pop(str(request.plan_id), None)
        result["demo_backup_available"] = True
        return result


@app.post("/api/demo/reset")
def demo_reset(request: RunRequest):
    with lock:
        sessions[str(request.session_id)] = {"documents": deepcopy(SEED), "latest_run": None}
        return run_analysis(request.session_id, "demo")


# Serve the built UI from the same origin; development uses Vite's /api proxy.
frontend = ROOT / "frontend/dist"
if frontend.is_dir():
    app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")


@app.get("/", include_in_schema=False)
def index():
    if (frontend / "index.html").exists():
        return FileResponse(frontend / "index.html")
    return {"message": "Run npm install && npm run build in frontend/, then restart the server. Or use the Vite dev server at port 5173.", "api_docs": "/docs"}


def main():
    import argparse
    import uvicorn
    parser = argparse.ArgumentParser(description="Run the local Schema Guard dashboard")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run("schema_guard.server:app", host="127.0.0.1", port=args.port)
