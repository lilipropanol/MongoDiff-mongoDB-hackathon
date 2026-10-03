# Starter validation

These are checks completed on the starter, not proof that future branch changes or a real Atlas deployment work. Documentation-only edits do not change those results. Recheck affected behavior after implementation changes and run the combined checks after merging.

## Combined branch integration — 2026-10-03

Merged `origin/feature/schema-guard-atlas-ui` and `origin/engine/atlas-analysis` into `feature/schema-guard-atlas-ui`, then connected the additive engine report fields and per-scan suggestion opt-in to the UI.

- `.venv/bin/python -m pytest -q`: **171 passed, 51 skipped**. The skipped real-Mongo/Atlas tests require integration services or credentials not enabled in this environment. The suite does not replace a measurement against the event's Atlas collection.
- `npm --prefix frontend run build`: **passed**. Vite still reports the existing large JavaScript chunk warning (~1.33 MB, 381 KB gzip).
- `node frontend/scripts/smoke.mjs http://127.0.0.1:8002`: **passed** against the isolated API (`MONGODB_URI=''`): demo repair 7 → 0, reset, inspection, support dialogs, themes, accessibility, and 375/768/1280px layouts.
- `GET /api/config` on that isolated server confirmed Atlas and suggestions are not configured; no credentials were used.

The UI now renders per-path counts and new/pre-existing attribution when present, bounded bad values, explanations, optional-default warnings, schema-version summaries, breaking/compatible labels, and opt-in suggestion status/results. `GUARD_OLD_MODEL=collection-validator` uses the installed collection `$jsonSchema` as the old schema. No live Atlas scan or Voyage/Atlas Vector Search request was made, so provider results and live counts remain unverified.

## Continuation checks — 2026-10-03

The interrupted MongoDiff UI work was reviewed against the running, demo-only managed preview. The Cards and simplified document Modals were already present in the latest commit; this continuation fixes collection-filter labeling, mobile explorer focus/open-state announcements/Escape handling, and the missing browser icon. The workspace initials now match MongoDiff.

- `.venv/bin/python -m pytest -q`: **12 passed**. New checks cover mismatched input/output aliases, matching aliases, field/model serializers (including nested models), and refusal to apply an Atlas plan through the fixture endpoint without constructing a MongoDB client.
- `npm --prefix frontend run build`: **passed**. The existing large-bundle warning remains; no dependency upgrades were made.
- `node frontend/scripts/smoke.mjs http://127.0.0.1:8000`: **passed**. In addition to the existing flow below, this now checks unexpected console errors, missing/null document inspection at 375/768/1280px, and mobile explorer keyboard focus and Escape. The expected unconfigured-Atlas 409 is excluded from console-error assertions, not from the error-state checks.
- Managed setup is versioned in `.hoplite/settings.json`; the preview overrides `MONGODB_URI` only for its process and never edits `.env`.

Atlas integration and live writes remain outside these checks. Atlas examples are count-bounded, not payload-size-bounded; large field values can still exceed MongoDB aggregation result limits. This needs real-server verification alongside the other Atlas limits below.

## Current frontend checks

The Atlas/LeafyGreen redesign passed `npm --prefix frontend run build` and `node frontend/scripts/smoke.mjs http://127.0.0.1:8002` against an isolated API with `MONGODB_URI=''`.

- Atlas shell with one active MongoDiff tab; the other collection tabs are disabled context.
- Actual fixture counts: 7 failures → reviewed repair → fresh verification at 0; reset restores 7.
- One scan-result sentence replaces the status cards. The four-column LeafyGreen table has exactly three demo issue rows, with real counts 4/2/2; missing/null remain separate inside grouped inspection. No issue search or JSON forms on the main page. Collection filtering remains available.
- MongoDiff naming throughout the interface. Scan controls and the issue table are separate LeafyGreen Cards; details and repair confirmation use LeafyGreen Modal. Document examples are flat key/value Cards, with missing/null distinctions preserved. Model changes, proposed validator, run history, and document details open supporting modals. LeafyGreen Select switches the source; LeafyGreen Banner presents scan errors and verified results.
- Default light appearance, including an old saved dark preference; optional dark mode and new theme preferences survive reload.
- The downloaded/displayed script matches every API-plan filter/update, checked by a dry execution against a recording database stub. Confirmation cancellation and the unconfigured Atlas error work.
- Axe reports no violations in the checked desktop themes/dialogs, repair confirmation, repaired report, Atlas error, and light workspace/validator/history states at 375, 768 and 1280px. The simplified summary and LeafyGreen table retain the approved Atlas palette and shell. This is not an audit of every possible state.
- No page overflow at those widths, including the supporting dialogs; tables and code have their own keyboard-accessible scrolling.
- No browser JavaScript errors during the checked flow.
- Screenshots: `/tmp/schema-guard-atlas-dark.png`, `/tmp/schema-guard-atlas-light.png`, `/tmp/schema-guard-repaired.png`, `/tmp/schema-guard-mobile.png`.

Python files were not changed in the frontend redesign. The earlier starter checks remain: five focused Python checks passed, and CLI fixture analysis reported 12 documents, 7 failures, 5 newly affected and 2 violations of the old schema. Re-run Python checks after backend branches are merged.

## Frontend implementation limits

- The main UI uses explicit demo presets reviewed through the script and confirmation. Custom repair decisions are API-only; an optional advanced dialog is future work.
- Git/PR linkage and installed-validator comparison have no API fields yet. They are omitted from the main page. **View validator** shows only the generated validator candidate.
- The tree shows only the configured collection, rather than discovering the cluster. Global navigation and other collection tabs are visual context.
- Euclid fonts use MongoDB's referenced CDN; system fonts are the offline fallback.
- LeafyGreen requires React 18-compatible component types here. `vite.config.ts` uses a browser-only Emotion server adapter to avoid Node stream imports; it does not replace LeafyGreen's CSS engine. SSR is not supported by that adapter.
- Vite reports a large JavaScript chunk (about 1.33 MB, 380 KB gzipped). Dependency splitting/lazy loading is a later performance task; attempts must be checked for LeafyGreen dependency cycles.

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
- Nested array-inside-array value summaries and unsupported Pydantic configuration/serialization behavior.
- **Not implemented:** durable backup, live execution, restore, existing-validator preservation, and validator rollout. Fixes/backend owns these paths.
- **Not implemented:** MongoDB report storage and CI gate policies (fixes/backend); authentication, live plan expiry, retention/limits, and deployment remain additional work.

The UI owner merges the contributors' pushed branches and verifies the full app. There is no separate integration role. [TEAM_HANDOFF.md](../TEAM_HANDOFF.md) lists priorities and completion criteria.

The built dashboard is Atlas-inspired. It is not an actual extension installed inside Atlas. Fixture success does not validate live MongoDB query semantics.
