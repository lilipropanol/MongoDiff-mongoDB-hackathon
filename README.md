# MongoDB Atlas mongoDiff

**Preview how a Pydantic model change affects documents already stored in MongoDB.** An Atlas collection dashboard prototype built with LeafyGreen and a shared Python engine and CLI. Independent feature prototype; it is not installed inside Atlas or endorsed by MongoDB.

## What works today

**This is a working starter. The fixture demo is complete; the live Atlas repair workflow is unfinished.**

| Feature | Current state |
| --- | --- |
| Dashboard, API, CLI, model translation and diff | Implemented; focused checks and frontend build passed |
| Demo scan → reviewed repair → rescan | Verified on 12 synthetic documents: 7 failures → 0 |
| Atlas collection analysis | Implemented and read-only; not yet verified against a real MongoDB server or Atlas cluster |
| Default, conversion and mapping plans | Generated for human review; Atlas plans can be exported |
| Apply button | Updates isolated in-memory demo fixtures only |
| Validator | Generated and downloadable; never applied by the app |
| Run history | Local JSON files; not stored in MongoDB yet |
| Live apply, durable backups and restore | Not implemented |
| AI suggestions, PR automation and schema versioning | Not implemented; stretch work |

## What the three people finish

- **You — UI:** keep the demo concise, connect the reviewed live-repair contract when available, then merge everyone's pushed branches and verify the combined app.
- **Schema/impact:** verify queries and actual counts on Atlas; improve nested explanations and missing-default warnings.
- **Fixes/backend:** reviewed live execution with backup, verification and restore; then validator rollout and MongoDB history.

Detailed priorities, ownership, agent prompts, and completion criteria are in [TEAM_HANDOFF.md](TEAM_HANDOFF.md). Check results and gaps are in [docs/VALIDATION.md](docs/VALIDATION.md).

## Run the dashboard

Requires Python 3.10+ and Node.js 20.19+ (Node 22 recommended). No MongoDB account is needed for the demo.

```bash
# From the repository root
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

Build the frontend:

```bash
cd frontend
npm ci
npm run build
cd ..
```

Start the API and built dashboard:

```bash
source .venv/bin/activate
schema-guard-server
```

Open **http://127.0.0.1:8000**. API documentation: **http://127.0.0.1:8000/docs**. If the port is occupied, use `schema-guard-server --port 8001` and open port 8001 instead.

For UI development, run `schema-guard-server` in one terminal and `cd frontend && npm run dev` in another. Open http://127.0.0.1:5173; Vite proxies `/api`, `/docs`, and `/openapi.json` to port 8000. If you change the API port, update those proxy targets in `frontend/vite.config.ts`, or use the built dashboard on the new API port. Restart the Python server after changing backend code, or use `.venv/bin/uvicorn schema_guard.server:app --reload --host 127.0.0.1 --port 8000`.

The public feature name is **mongoDiff**. Existing commands (`schema-guard`, `schema-guard-server`) and the Python package (`schema_guard`) retain their starter identifiers.

## Frontend layout

The dashboard recreates Atlas Data Explorer with **mongoDiff** as its active collection tab. It uses MongoDB's LeafyGreen components and Euclid Circular A typography. Light mode is the default, matching the Atlas reference screenshots. The header moon/sun control switches themes and remembers your choice. The earlier dark-default preference is replaced once; newly selected preferences persist.

Only mongoDiff is implemented. The other collection tabs and global navigation icons provide Atlas context. The tree filters the current configured collection; it does not discover other collections. Scan controls and document issues are separated into LeafyGreen Cards. Model changes, document examples, validator preview and history open LeafyGreen Modals. Document inspection shows flat Atlas-style key/value previews.

The main view shows one scan result, a LeafyGreen table with **Field / Issue / Documents / Details**, the generated operations, and **Apply Fix & Rescan**. Counts always come from reports. **View validator** opens the generated candidate; the API does not compare the installed validator or provide Git/PR linkage. [Frontend plan](docs/FRONTEND_PLAN.md) and [brand guidance](brand.md) describe the implementation.

## Try the complete demo

1. The dashboard loads 12 synthetic movies and reports **7 failures**. The header's **Demo** badge and data-source selector identify these as fixture results.
2. The table summarizes three issue groups: **4** movies with missing/invalid ratings, **2** with string runtimes, and **2** with missing/null runtimes. A movie can appear under both rating and runtime issues; the headline remains the unique failing-document count.
3. Select **Details** for examples. Missing and null remain separate in the detail dialog. The rating group includes both missing and invalid values.
4. Review **Repair plan**. It uses the existing example choices: defaults `rated="PG"`, `runtime=90`; mappings `PG13→PG-13`, `NR→PG`, and `N/A→90`. These are demo decisions, not recommendations for real movies.
5. Select **Apply Fix & Rescan**, then confirm **Apply & Rescan**. The isolated fixture repair returns a fresh report with **0 failures**.
6. **Run history** opens saved reports and the model-change view. **View validator**, report export, and script download remain available.
7. **Reset demo data** restores the seed and scans again.

The streamlined dashboard has no JSON editors. Custom defaults/mappings remain supported by the plan API described in [docs/API.md](docs/API.md); an optional advanced decision dialog is future work. Atlas analysis and exported mechanical plans remain read-only, and the Apply button is disabled for Atlas.

Demo documents and plans are isolated by browser session and kept in server memory. Saved report history is written to ignored `reports/`. After a server restart, run analysis to recreate the fixtures and generate a fresh plan. The temporary copy kept during demo apply is not a durable backup or a restore feature; **Reset demo data** loads the original seed. The fixture adapter does not verify MongoDB's BSON/query semantics.

## Connect Atlas

Copy `.env.example` to `.env` and configure it:

```dotenv
MONGODB_URI=mongodb+srv://...
MONGODB_DATABASE=sample_mflix
MONGODB_COLLECTION=movies
GUARD_OLD_MODEL=examples/models_old.py:Movie
GUARD_NEW_MODEL=examples/models_new.py:Movie
```

Load `sample_mflix` in your Atlas cluster, grant read access to the target collection, and allow your machine's IP in Atlas. Restart the server, select **MongoDB Atlas**, and **Run analysis**. Expect counts determined by your collection, not the fixture's 7 failures. Model paths are trusted server configuration; the API does not accept uploaded Python code or paths.

The scan uses MongoDB `$jsonSchema` and `$facet` for total counts, old-schema violations, newly affected documents, issue reasons, and bounded examples. Issue counts can overlap. It scans the full collection with a 30-second server limit; this is not a snapshot guarantee if concurrent writes occur. Atlas output is real collection data and is never replaced by demo results on failure.

**Atlas analysis and plan generation are read-only.** Live apply, backup/restore, validator application, and MongoDB-backed report storage are pending tasks. Exported scripts are review artifacts; do not run them on production until those paths are implemented and checked.

## CLI

```bash
schema-guard --demo
# Reads MONGODB_URI from .env for a live collection:
schema-guard --database sample_mflix --collection movies \
  --old examples/models_old.py:Movie --new examples/models_new.py:Movie
```

JSON output defaults to `reports/latest.json`. The CLI and API share translation, diff, impact, and report construction. The CLI has no apply command.

## Contributor guide

Start with **[TEAM_HANDOFF.md](TEAM_HANDOFF.md)** for the three-person split, concrete tasks, agent prompts, merge boundaries, and the finish checklist. Read **[docs/API.md](docs/API.md)** before changing shared request/response shapes. Frontend design tokens and direction are in `brand.md`.

The three roles are **UI**, **schema/impact**, and **fixes/backend**. The UI owner coordinates shared contracts and handles branch merging and final app integration after the contributors push their work.

```text
frontend/src/     React + TypeScript UI; typed API client
schema_guard/     Translation, diff, MongoDB analysis, fix plans, REST API
examples/         Old/new Movie models
tests/            Focused translation and API workflow checks
docs/API.md       Shared API contract
TEAM_HANDOFF.md    Three-person work plan and acceptance criteria
```

## Checks

```bash
source .venv/bin/activate
pytest -q
cd frontend
npm run build
```

Core checks cover required-vs-nullable behavior, aliases, unsupported constraints, fixture repairs, explicit mappings, invalid decisions, stale plans, report history, and missing Atlas configuration. Real MongoDB query integration is a separate check; fixtures are not a MongoDB emulator. See [docs/VALIDATION.md](docs/VALIDATION.md) for checked behavior and the browser smoke command.

## Supported subset and known limits

- Pydantic v2: `str`, `int`, `float`, `bool`, `datetime`, `list[T]`, `Optional[T]`, `Literal[...]`, nested models. Unsupported types and field constraints are reported instead of guessed.
- `Optional[T]` without a default is required but nullable. Defaults make a field optional; they are not silently persisted.
- Ints accept BSON `int` and `long`. Floats accept BSON numeric types; Pydantic can still have different runtime coercion behavior.
- Aliases are used as stored field names. Complex validation aliases, dotted/dollar field names, custom validators, and `extra='forbid'` are unsupported.
- Nested schema validation works; nested changes are grouped under the root field rather than individual paths. Recursive models are unsupported.
- Repair candidates cover explicit defaults, string-to-integer conversions, and string-keyed explicit value mappings. Numeric-key mappings, inferred renames, and removals need further design.
- Custom serializers and other Pydantic configuration are not fully audited. The translator covers the listed stored-schema subset, not every behavior of an application model.
- Constraint translation, default warnings, CI exit policies, Beanie-specific types, durable backups, live repairs, schema versioning, authentication, retention limits, and a production deployment remain unfinished.
- This local prototype binds to `127.0.0.1`. Session identifiers are isolation conveniences, not authentication. Add authentication and authorization before deploying it for a team.

## Technical references

The implementation follows MongoDB's [JSON Schema query documentation](https://www.mongodb.com/docs/manual/reference/operator/query/jsonschema/) and [$facet documentation](https://www.mongodb.com/docs/manual/reference/operator/aggregation/facet/). The local app uses [FastAPI static serving](https://fastapi.tiangolo.com/tutorial/static-files/) and [Vite](https://vite.dev/guide/).
