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

## Checks

Run from the repository root:

```bash
.venv/bin/python -m pytest -q
npm --prefix frontend run build
# From the root, with the server running:
node frontend/scripts/smoke.mjs http://127.0.0.1:8000
```

The browser smoke check expects an API server with Atlas unconfigured. See docs/VALIDATION.md for an isolated command that leaves your .env unchanged.
