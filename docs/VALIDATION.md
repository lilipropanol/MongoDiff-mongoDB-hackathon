# Starter validation

These are checks completed on the starter, not proof that future branch changes or a real Atlas deployment work. Documentation-only edits do not change those results. Recheck affected behavior after implementation changes and run the combined checks after merging.

## Checked

- `pytest -q`: 5 passing focused checks.
- `npm run build`: TypeScript check and Vite production build pass.
- Browser smoke check in Chrome: fixture report shows 7 failures; reviewed repair reaches 0; reset restores 7.
- All five dashboard tabs, fix confirmation, run history, and unconfigured Atlas error recovery work.
- Axe checks report no violations for the five desktop views, confirmation dialog, and the run-history view at each checked responsive width. This is not an audit of every state or every view at every width.
- No page overflow across all tabs at 375, 768, and 1280 pixels.
- No browser JavaScript errors during the checked flow.
- CLI fixture analysis reports 12 documents, 7 failures, 5 newly affected documents, and 2 violations of the old stored schema.

## Repeat the checks

From the repository root, with dependencies installed:

```bash
.venv/bin/python -m pytest -q
npm --prefix frontend run build
```

The browser smoke script uses an installed Chrome binary; set `CHROME_PATH` for another location. It expects Atlas to be unconfigured because it checks that setup error. Start an isolated local API in one terminal, overriding the URI for this process without editing `.env`:

```bash
MONGODB_URI='' .venv/bin/schema-guard-server --port 8001
```

In another terminal, run from the repository root:

```bash
node frontend/scripts/smoke.mjs http://127.0.0.1:8001
```

This script exercises fixture repairs, saves session reports under `reports/`, and writes screenshots under `/tmp/`. It does not repair MongoDB documents. If another process uses 8001, choose an unused port and pass the same URL to the script.

## Not verified or not implemented

- **Implemented but not verified on real MongoDB:** Atlas connectivity, permissions, query semantics, and live `sample_mflix` counts. Schema/impact owns this check.
- MongoDB BSON values and cases not present in the fixture adapter.
- Full nested path explanations and unsupported Pydantic configuration/serialization behavior.
- **Not implemented:** durable backup, live execution, restore, existing-validator preservation, and validator rollout. Fixes/backend owns these paths.
- **Not implemented:** MongoDB report storage and CI gate policies (fixes/backend); authentication, live plan expiry, retention/limits, and deployment remain additional work.

The UI owner merges the contributors' pushed branches and verifies the full app. There is no separate integration role. [TEAM_HANDOFF.md](../TEAM_HANDOFF.md) lists priorities and completion criteria.

The built dashboard is Atlas-inspired. It is not an actual extension installed inside Atlas. Fixture success does not validate live MongoDB query semantics.
