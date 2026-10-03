# MongoDiff — three-person handoff

## Current integrated state (2026-10-03)

The UI owner has merged `engine/atlas-analysis` and the latest UI branch into `feature/schema-guard-atlas-ui`. The three build roles remain UI, schema/impact engine, and fixes/backend; integration is coordinated by the UI owner after branch pushes, not a separate role.

- **Integrated:** language-neutral JSON Schema/model input, collection-validator input, deterministic breaking/compatible diff, bounded two-pass impact analysis, nested/list paths, distinct bad values, per-reason old/new counts, explanations, default warnings, schema-version analysis, measurement command, and optional lexical/Voyage/Atlas Vector Search suggestions.
- **UI integration:** issue inspection shows nested paths, counts, explanations, bounded values and advisory candidates. The **Voyage AI suggestions** button opts in for demo or Atlas data. **Use suggestion** adds a human choice to the regenerated repair preview; application still requires confirmation. Warnings and schema-version summaries appear when supplied by the report.
- **Safety:** Atlas scan and plan remain read-only. Fixture apply/restore affects only in-memory demo data. Atlas Vector Search can write only to its explicitly configured separate vocabulary collection. Suggestions never apply repairs.
- **Still to verify:** run the combined checks; measure against the event Atlas cluster with the measurement command; verify Voyage and Vector Search credentials on a disposable namespace. Do not quote Atlas findings until measured.

## Starting point

**The starter is built; the full live Atlas workflow is not.** The dashboard, API, CLI, translated schemas, diff, fix plans, validator export, and local JSON history already exist. Build on these modules rather than recreating them. It is a feature prototype displayed in an Atlas-like shell, not an actual Atlas extension.

The UI uses the actual LeafyGreen kit in an Atlas collection shell: light/dark themes, compact scan output, nested issue paths, new/pre-existing counts, value and example inspection, a script-only remediation panel, and model/validator/history dialogs. AI candidates are opt-in and advisory. See [frontend plan](docs/FRONTEND_PLAN.md), [brand guidance](brand.md), and [current checks](docs/VALIDATION.md).

The verified fixture demo works without credentials: 12 documents → 7 failures → reviewed defaults/mappings → 0 failures. Defaults plus integer-text conversion, without value mappings, leave 2 documents for review. Counts are calculated from fixture documents.

| Remaining deliverable | Current gap | Owner |
| --- | --- | --- |
| Verified Atlas impact report | Engine has real-MongoDB integration coverage; measure the event Atlas collection before quoting results | Schema/impact + UI |
| Optional advanced decisions | Custom decisions are supported by API; streamlined dashboard has no custom mapping editor | You — UI |
| Reviewed live repair with backup, rescan and restore | Apply only changes in-memory fixtures; durable backup/restore does not exist | Fixes/backend |
| Validator rollout | Only the command preview/export exists | Fixes/backend |
| MongoDB-backed history | Reports currently live in local JSON files | Fixes/backend |
| Working combined app | Branches are merged; combined checks and final Atlas configuration still need verification | You — UI |

Live query verification and the UI decision flow come first. If you implement live writes, complete backup and restore before offering live Apply. Validator rollout and MongoDB history follow that workflow. AI, PR automation and schema versioning are stretch work.

## Ownership and merge boundaries

| Person | Owns | First deliverable | Files to own |
| --- | --- | --- | --- |
| 1 — UI (you) | Dashboard experience, demo presentation, and final branch merging/app integration | Better decision form and clear scan/repair states, followed by a working merged app | `frontend/`, `brand.md`; cross-component fixes during final integration |
| 2 — schema and impact | Translation, comparison, and accurate live-data explanations | A verified scan on the actual Atlas dataset | `schema_guard/translator.py`, `diff.py`, `impact.py`, `models.py`; translation/query checks |
| 3 — fixes/backend | Repair execution, backups, validator rollout, backend API and persistence | Reviewed fixes on a disposable collection with verification | `schema_guard/fixes.py`, `server.py`, `report.py`, `cli.py`, `demo.py`; backend/API checks |

You (Person 1, UI) coordinate shared API contracts, own `frontend/src/types.ts`, and handle final integration after contributors push their branches. Persons 2 and 3 implement their assigned modules and backend endpoints on their own branches. Announce proposed contract changes before editing and agree on them with you. Coordinate changes to `pyproject.toml`, shared tests, and this handoff; nominate one editor per shared file at a time.

Suggested branches: `ui/decision-flow`, `engine/atlas-analysis`, `backend/reviewed-apply`. Each agent should start by reading README, this handoff, and `docs/API.md`.

### Branch handoff and final integration

1. Each contributor implements and checks their assigned work on their own branch.
2. Each contributor pushes their branch and shares its name, completed changes, checks run, API/report changes, and remaining gaps.
3. After the branches are pushed, you merge them, resolve conflicts, connect UI controls to the delivered backend behavior, and run the combined Python, frontend build, and browser checks.
4. Contributors help resolve issues in their modules while you own the merged app and final demo.

Each pushed branch should include a short handoff:

```text
Branch: fixes/backend
Completed behavior: Added demo backup/restore flow, stale-plan enforcement, reviewed execution metadata, and a validator preview endpoint. Atlas analysis remains read-only and verified against the live sample_mflix.movies collection.
Changed files: schema_guard/fixes.py, schema_guard/server.py, tests/test_workflow.py
API/report changes (or none): Added execution_contract metadata to plans, /api/demo/restore, and /api/validator; existing /api/analyze and /api/demo/apply semantics remain stable.
Checks run and results: .venv\Scripts\python.exe -m pytest -q -> 6 passed, 1 warning.
Remaining gaps: live apply against a disposable MongoDB collection, durable backup persistence beyond demo memory, MongoDB-backed history, and UI wiring for live confirmation.
How the UI owner can try it: run the server, use demo analysis/apply flow, then call restore to validate the review/undo path; keep live Atlas writes disabled until the next contract is approved.
```

### Final integration note

Person 1 is currently working on the local UI branch and should push their branch before the final merge. The backend and engine branches are already integrated on `ui/integration` and verified together on Python. The UI owner should merge the final UI branch into the same integration branch only after confirming the shared contract in `docs/API.md`, `frontend/src/types.ts`, and the report fields produced by the engine/backend. The final sequence is: push UI branch, merge UI into `ui/integration`, rerun the Python checks and the frontend build, then run the smoke browser pass with a Chrome/Chromium binary available locally. Do not enable live MongoDB writes until the reviewed backup/execute/restore contract is validated on a disposable collection.

### Shared integration handoff: backend + engine

```text
Branch: ui/integration
Completed behavior: Backend + engine work has been merged and verified together. Atlas analysis is read-only and works against the configured sample_mflix.movies collection, the reviewed demo repair flow is restored safely, and the plan contract includes backup/staleness metadata. Python checks pass on the integrated branch.
Changed files: schema_guard/fixes.py, schema_guard/server.py, tests/test_workflow.py, schema_guard/impact.py, schema_guard/translator.py, schema_guard/diff.py, plus the engine branch additions under schema_guard/engine/ and docs/engine/.
API/report changes (or none): Shared API contract remains read-only for Atlas; added execution_contract metadata to plans, /api/demo/restore, and /api/validator. No live writable Atlas endpoint is enabled yet.
Checks run and results: .venv\Scripts\python.exe -m pytest -q -> 130 passed, 35 skipped, 1 warning. npm --prefix frontend run build -> passed after installing frontend dependencies. Browser smoke remains blocked only by missing Chrome/Chromium in the environment.
Remaining gaps: final UI merge, Chrome/Chromium runtime for smoke test, and any contract adjustments required once Person 1 pushes the UI branch.
How the UI owner can try it: pull the integration branch, merge the UI branch into it, then run the app with the same local .env and verify the demo and Atlas analysis loops. Keep live writes disabled until the disposable-collection backup and restore flow is validated.
```

### Interrupted UI session continuation

- Branch: `hoplite/poseidonia-c1e6cab1`.
- Completed: reviewed the existing MongoDiff Cards/Modals and source across UI, API, CLI, and engine; fixed LeafyGreen filter labeling, mobile explorer keyboard focus/Escape/open state, and browser icon/workspace initials; added repeatable demo-only managed preview setup.
- Safety fixes: reject mismatched input/stored aliases and custom serializers instead of generating a misleading schema. Added regression coverage proving the fixture apply endpoint rejects Atlas plans.
- API/report changes: none. Unsupported model configurations now fail explicitly.
- Checks: 12 Python tests, production frontend build, and full Chrome/Axe smoke passed, including fixture repair 7 → 0, reset, themes, supporting modals, and 375/768/1280px inspection.
- Remaining: the live Atlas/repair/integration roadmap below is unchanged. Large Atlas example payloads still need bounds and real-server verification; no MongoDB writes were added or executed.
- Try it: open the managed preview, or run the isolated API/browser commands in `docs/VALIDATION.md`.

## Person 1 — UI tasks

### Finish first

- [x] Preserve the full scan → preview → confirm → rescan loop in the Atlas/LeafyGreen layout.
- [ ] If needed for live repairs, add an optional advanced decision dialog with typed per-field controls. Keep forms and raw JSON off the main demo view.
- [ ] Show a reason's distinct bad values when the backend provides them; let the human explicitly map or leave each one unresolved.
- [ ] Improve nested issue details and sorting behind inspection; preserve the concise main table.
- [x] Show the actual pre-apply/after-apply failure counts and an indeterminate scan state.
- [ ] Coordinate a live-apply confirmation UI only after Person 3 delivers its backup/execute contract.
- [x] Check the current layout, dialogs, collection filter, confirmation cancellation, error recovery and mobile overflow; repeat these checks after further UI changes.
- [ ] After contributors push, merge their branches, resolve cross-component mismatches, and verify the full app and repeatable demo.

### AI suggestion UI (integrated; opt-in)

- [x] Keep candidates visibly advisory. Issue details show suggestions beside distinct values with target, score and source; rename candidates appear beside model changes.
- [x] Selecting a candidate adds an explicit mapping to the regenerated repair preview. No candidate is auto-selected and selecting one never writes documents. A general custom-value/default editor remains future work.
- [x] The report records provider/fallback status; failed Voyage requests preserve the scan and label lexical fallback.
- [x] Preserve per-scan opt-in and disclose that bounded bad values, allowed values and field names may be sent to the configured provider. Do not send examples, document IDs, whole documents or connection details.
- [x] The report/API types carry suggestion status, per-value suggestions and rename candidates.

Acceptance: candidates are available only where applicable, remain advisory, and show their source and score. Selecting one updates an explicit plan preview without changing counts. Application requires confirmation. Demo provider responses can be cached for retakes and are labelled as saved responses. See [the recording script](docs/DEMO_VIDEO.md).

### Acceptance

Someone unfamiliar with the project can distinguish demo from Atlas data, explain why a document fails, enter a valid decision, review the resulting operations, and observe the new report. No interface control implies live repairs are already supported.

### Agent prompt

> Own the React dashboard in frontend/ and final app integration. Read README, TEAM_HANDOFF.md, docs/API.md and brand.md. Preserve the existing API contract and working demo. Preserve the script-only main view. If live repair requires custom decisions, add a concise optional dialog, plus better issue inspection and clear before/after state. Coordinate API contracts and shared types with the backend contributors. During parallel implementation, keep changes within UI ownership. After contributors push their branches, merge their work, resolve cross-component mismatches, and make the necessary integration changes across the app. Verify the combined Python checks, production build, and browser flow at mobile and desktop widths.

## Person 2 — schema and impact tasks

### Finish first

- [ ] Connect to the actual Atlas sample collection and measure the real counts. Do not promise the illustrative numbers in the pitch.
- [ ] Verify `$jsonSchema`, aggregation `$type`, enum, null, arrays, and nested objects against a real MongoDB server. Array element matching must not be confused with the stored field's type.
- [ ] Make the distinction between new violations and pre-existing drift understandable; strict BSON validation differs from Pydantic's coercive reads.
- [ ] Add recursively useful diff paths and issue locations for nested models.
- [ ] Add warnings for optional/defaulted fields missing in storage, even if reads would synthesize a default.
- [ ] Audit supported Pydantic constraints/configuration and fail clearly whenever behavior cannot be translated faithfully.
- [ ] Provide bounded distinct bad-value counts for mapping controls, without returning full documents.
- [ ] Set defensible scan/timeout/example size limits; report empty collections correctly.

### Acceptance

The live report's unique failing count is independent from overlapping reason counts. Tests include missing fields, nulls, string integers, an unconvertible value, enum outliers, arrays containing mixed types, aliases, and nested required fields. Unsupported models produce a useful error. Observed counts are reproducible on the demo collection.

### Agent prompt

> Own Pydantic translation, deterministic diff, and MongoDB impact analysis. Read the current report/API contract. Verify behavior on real MongoDB, especially field-level $type versus array element matching. Add nested paths, missing-default warnings, and bounded distinct bad values. Preserve old/new violation counts and report unsupported behavior clearly. Coordinate report additions with Persons 1 and 3. Do not implement writes in impact.py.

## Person 3 — fixes/backend tasks

### Finish first

- [ ] Add a disposable demo collection in Atlas/local MongoDB; keep the original sample collection intact for repeatable scans.
- [ ] Back up every document the reviewed operations may touch, including values that matched the old model and optional cleanups. Persist original validator/options if modifying them.
- [ ] Design an execution contract: immutable plan ID, schema/collection fingerprint, explicit confirmation, expiry/staleness checks, and one reviewed plan per execution.
- [ ] Make backup completion a precondition for live updates. Handle backup collisions and partial failures, and report each operation's matched/modified counts.
- [ ] Execute the existing generated default, conversion and mapping operations through the new live path. Preserve the original-value `onError` fallback and decision validation; add matched/modified results and a fresh live scan.
- [ ] Implement and demonstrate restore on the disposable collection. Rollback must explain what happens to concurrent writes and newly inserted documents; no blanket collection overwrite.
- [ ] Apply `warn` validators separately, respecting existing validators and collection options. Move to `error` only as a separately reviewed decision.
- [ ] Persist run/plan/execution history to a MongoDB collection for the MongoDB-native story; local JSON remains a fallback.
- [ ] After the core repair flow, add CI-readable exit policies and an example workflow that runs read-only checks; agree with the team whether pre-existing failures block a change.

### Acceptance

A reviewed repair on a disposable collection first creates a complete backup, reports operation results, and returns a fresh scan. A demonstrated restore returns the original affected documents/options. A stale plan is rejected. No live endpoint writes without an explicit reviewed request.

### Agent prompt

> Own fixes, backend API endpoints, and execution/persistence. Preserve the current read-only Atlas path and isolated fixture demo. Implement reviewed plans with backup-before-write and verification on a disposable MongoDB collection. Add rollback and separate validator rollout while preserving existing options. Agree on endpoint/report additions with the UI owner, who coordinates contracts and final integration. Push your branch with a handoff listing changes, checks, contract changes, and unfinished work. The UI owner merges the branches and integrates the app; help resolve issues in your backend modules. Never apply generated repairs to the original sample collection or production data as part of analysis.

## Shared finish checklist

- [ ] All three branches build against the agreed API contract.
- [ ] Frontend build and focused Python tests pass again on the merged app; starter results are documented in [docs/VALIDATION.md](docs/VALIDATION.md).
- [ ] Live Atlas counts and generated operations have been checked on the chosen dataset.
- [ ] The database URI stays in local environment configuration and out of reports/logs/frontend bundles.
- [ ] The report identifies its source, unique failing count, overlapping issue counts, pre-existing violations, and unresolved problems.
- [ ] The demo can be reset and repeated; an offline fallback is clearly labelled as fixtures.
- [ ] README explains exactly what is built and what is still a prototype.
- [ ] Add the chosen open-source license before publishing; agree on repo/package names.
- [ ] Record a short demo and rehearse the presentation twice.

## Suggested build-window plan

| Elapsed time | UI (you) | Engine | Fixes/backend |
| --- | --- | --- | --- |
| First 20 min | Run concise demo; agree contracts | Connect cluster; measure baseline report | Agree plan/execution contract; disposable collection |
| Next 90 min | Optional decisions; issue details | Real-server query checks; nested reasons | Backup, execute, verify on disposable data |
| Next 60 min | Wire execution states | Default warnings; bad-value summaries | Restore, validator preservation; report persistence |
| Next 40 min | After branches are pushed: merge, connect UI/backend, run combined checks and responsive/a11y pass | Push checked branch with handoff; help resolve engine issues | Push checked branch with handoff; help resolve backend issues |
| Remaining time | Everyone: README, resettable demo, pitch rehearsal and submission |

If time is tight, aim for measured Atlas impact plus exported fixes and the working fixture repair loop. Only describe live execution as built after the backup/repair/restore flow passes on a disposable MongoDB collection. GitHub PR comments, arbitrary model uploads, full advanced type support, deployment, and installation inside the real Atlas dashboard remain stretch work.

## Demo narration

For a verified live scan: “This model change makes runtime required and adds a constrained rating. The tool asks MongoDB how many existing documents violate the new stored shape. It distinguishes old drift from newly affected documents and shows the field-level reasons. I provide decisions for missing/ambiguous values and review deterministic operations.”

For the current repair demo, explicitly say: “This Apply step uses isolated synthetic fixtures. After the reviewed repair, a fresh fixture scan shows the remaining count.” Change that narration to live MongoDB only after the live execution flow is implemented and checked.

Lead with the real-data impact report. Describe a validator as protection for future writes; it does not repair existing data. Mention schema versioning as a possible later repair strategy.
