# Working in this repository

Read README.md, TEAM_HANDOFF.md, docs/API.md, and brand.md before changing shared behavior.

## Current scope

The UI/API/CLI starter and fixture repair demo are implemented. Atlas scans are implemented but not verified against real MongoDB. Apply is demo-only. Durable backups, live apply/restore, validator application, and MongoDB-backed history are unfinished. See README.md for status and TEAM_HANDOFF.md for remaining work.

## Ownership and branch workflow

- UI owner (the user): frontend/ and brand.md; merges contributors' pushed branches and owns final app integration.
- Engine owner: translator.py, diff.py, impact.py, models.py.
- Fixes/backend owner: server.py, report.py, fixes.py, demo.py, cli.py.
- Coordinate shared tests, dependencies, and request/report shapes with the UI owner, who coordinates shared API contracts and updates TypeScript types. Backend contributors propose and implement changes on their own branches.
- Each contributor pushes their branch with a handoff covering changes, checks, contract changes, and unfinished work. The UI owner then merges branches, resolves app integration issues, and runs the combined checks.

## Implementation rules

- Keep Atlas analysis read-only. Existing fixture-only apply must never execute against MongoDB.
- Label fixture results as demo results. Do not invent impact counts, progress percentages, or conversion success counts.
- Keep credentials in local .env; never include them in reports, client bundles, error messages, or screenshots.
- Model modules are executable Python loaded from trusted server configuration. Do not expose arbitrary path/code loading over HTTP.
- Preserve missing-vs-null behavior and differentiate pre-existing drift from newly affected documents.
- Use real MongoDB integration checks for query semantics; the demo adapter is not a MongoDB emulator.
- Run focused Python checks and the frontend build for changes to their respective areas. The browser smoke check requires a running API and Chrome.
- Live apply must be a reviewed immutable plan with backup-before-write, partial failure reporting, rollback design, and a fresh verification run.

## Voyage AI suggestions (Person 3)

### What exists already

The engine can suggest fixes for bad values and renamed fields. The branch `engine/atlas-analysis` includes `schema_guard/engine/suggest.py`. It suggests examples such as `PG13` → `PG-13` for the `rated` field and `runtime` → `duration_minutes` as a possible rename. Suggestions use Voyage AI embeddings with the default model `voyage-4-lite`, and they fall back to offline text matching when needed. Suggestions are advisory only: they never become plan decisions and never change counts. Tests already cover both the Voyage path and the fallback path.

### How it is switched on

```env
GUARD_SUGGESTIONS=voyage        # or "lexical" for offline-only; unset = off (default)
VOYAGE_API_KEY=...              # never commit; .env is git-ignored
# Optional:
VOYAGE_EMBED_MODEL=voyage-4-lite
VOYAGE_API_URL=https://ai.mongodb.com/v1
```

### Where the output appears in reports

- `reasons[].distinct_values[].suggestions: [{target, score, source}]`, up to 3 per bad value
- `changes[].rename_candidates: [{to, score, source}]`
- `scan.suggestions: {provider, model, status, fallback_reason}`

`build_report` now preserves `warnings` and `scan.suggestions` in saved/API reports.

### Tasks

- Live check passed against MongoDB's endpoint, `https://ai.mongodb.com/v1`:

```bash
VOYAGE_API_KEY=... SCHEMA_GUARD_LIVE_VOYAGE=1 .venv/bin/python -m pytest -q tests/engine/test_engine_suggest.py
```

- The endpoint base is configurable with `VOYAGE_API_URL`; the tested MongoDB value is `https://ai.mongodb.com/v1`.

- Tune on real data. Run an Atlas analysis of `sample_mflix.movies` with `GUARD_SUGGESTIONS=voyage` and inspect real suggestions such as `NOT RATED` or `TV-14`. If the suggestions are too eager or too shy, adjust `VOYAGE_MIN` in `schema_guard/engine/suggest.py` (currently `0.6`) and record the chosen value in `docs/engine/PROGRESS.md`.
- Keep `fixes.py` advisory-only: only offer mappings for values with `mappable: true`. The human must still type or pick the mapping.

### Rules to keep

- Off by default. It must stay opt-in because it sends data values to an external service.
- Only these are sent: bad values (trimmed to 80 chars), allowed enum values, and field names. Never send document IDs, full documents, examples, or the database URI. Keep the existing tests passing.
- One batched request per scan. Free tiers may be limited to roughly 3 requests per minute.
- If Voyage fails or times out after 10 seconds, the scan still succeeds with offline suggestions and `status: "fallback"`.
- Do not use Atlas Vector Search or auto-embedding; they require index creation, which is a write, and the scan is read-only.

### Done when

- The live test passes with a real key.
- `scan.suggestions.status` shows `"ok"` in a saved Atlas report.
- The chosen threshold and a few example suggestions are recorded in `docs/engine/PROGRESS.md`.
- `pytest -q` remains green.

Nice to have: a Voyage reranker option such as `rerank-2.5` for better “which allowed value did they mean?” matches, but it should be opt-in because it adds a request per bad value.

## Checks

Run from the repository root:

```bash
.venv/bin/python -m pytest -q
npm --prefix frontend run build
# From the root, with the server running:
node frontend/scripts/smoke.mjs http://127.0.0.1:8000
```

The browser smoke check expects an API server with Atlas unconfigured. See docs/VALIDATION.md for an isolated command that leaves your .env unchanged.
