# Person 2 (schema & impact engine): progress log

Branch: `engine/atlas-analysis` · Last updated: 2026-10-03 · Nothing is committed or pushed yet; you review first.

## Where my code is

| Folder | What |
| --- | --- |
| `schema_guard/engine/` | All engine code: `translator.py`, `json_schema.py`, `diff.py`, `impact.py`, `models.py`, `suggest.py` |
| `tests/engine/` | Unit tests; `integration/` holds the real-MongoDB tests; `fixtures/` holds the starter snapshot |
| `examples/engine/` | Language-agnostic example schemas (JSON Schema, MongoDB validator) |
| `docs/engine/` | The plan (`schema-impact-plan.md`) and this log |

Outside these folders I only changed four **connector** files: `schema_guard/{translator,diff,impact,models}.py`. They contain only re-exports from `schema_guard/engine/`, so `server.py`, `cli.py`, `demo.py` and `fixes.py` (Person 3) keep working unchanged.

**I made no edits to Person 1's or Person 3's files.**

## Done

### Language-agnostic input (new)

- Besides Pydantic `FILE.py:Class`, any `FILE.json` works wherever a model is accepted: CLI `--old/--new`, server `GUARD_OLD_MODEL/GUARD_NEW_MODEL`. Two formats are accepted:
  - standard JSON Schema, as exported by TypeScript/Zod, Java, Go, Pydantic and other tools
  - a MongoDB validator (`{"$jsonSchema": ...}`)
- `load_collection_validator(collection)` reads the validator a collection enforces today (read-only `listCollections`), so the "old schema" can come straight from MongoDB, with no code at all.
- Supported JSON Schema:
  - `type`/`bsonType`, `properties`, `required`, `items`, `enum`, `const`
  - nullable `anyOf`/`oneOf` (`X` or `null`), a single-entry `allOf`, local `$ref` with `$defs`/`definitions`
  - Annotations (`title`, `description`, `default`, `format`, `examples`, …) are ignored.
  - Anything else fails with a message naming the keyword and its path.
- **Proof:** the three files in `examples/engine/` produce exactly the same schema as the Python example models, and a Pydantic model exported to JSON Schema round-trips to the same result.

### Translator audit (Pydantic)

- These now fail clearly, where they previously gave a silently wrong schema:
  - `Field(exclude=True)`
  - field and model serializers
  - a validation alias that differs from the serialization alias
  - recursive models (previously a bare `RecursionError`)
- Error messages name the field path (`wrap.bad`, `imdb.rating`).
- Added support for `str`/`int` `Enum` types.
- Model files with the same name in different folders no longer collide.
- Output for the starter models is unchanged (snapshot test).

### Diff

- Nested paths (`imdb.rating`, `genres[]`, `cast[].name`) with `parent`.
- `details`: types added/removed, enum added/removed, `restricted_to`, `enum_lifted`, nullability change.
- New kind `became_optional`.
- Every change gets `compatibility` (`breaking` | `compatible`) and a reason, following MongoDB's schema-versioning guidance:
  - new required field → backfill
  - removed field → readers break
  - narrowed type → migrate
  - relaxed rule → compatible
- **Bug found by tests and fixed:** Python treats `True == 1`, so a change from `Literal[1]` to `Literal[True]` was invisible. The diff now compares values like MongoDB does: numbers by value, booleans never equal to numbers.

### Impact (the scan)

- **Nested reasons** with an exact `path` and a `location` (`field` | `nested` | `array_element`).
  - `field` stays the root field, because `fixes.make_plan` looks it up and would crash on a dotted path.
  - Nested checks use aggregation expressions, so arrays are never confused with their elements.
- **Distinct bad values** (`distinct_values`, `distinct_value_count`, `distinct_values_limited`):
  - top 10 per reason, kept apart by type (`"1"` vs `1`)
  - scalars only; no documents are returned
  - strings cut to 80 characters
  - `mappable` marks the values that `fixes.make_plan` can map today
- **Drift per reason:** `count_newly` and `count_preexisting`.
- **Plain-language `explanation`** per reason, including strict BSON vs Pydantic's lax reading.
- **Warnings** for optional/defaulted fields missing in storage. These don't count as failures.
- **Limits:** examples 0–5, distinct values 0–50, `maxTimeMS` 1000–60000 per aggregate. Example arrays are cut to 5 items and strings to 200 characters.
- **Two-pass scan:** pass 1 counts everything; pass 2 starts with `$match` on failing documents (MongoDB guidance: `$facet` sends every document to every branch, so filter early).
- **`scan` metadata:** duration, limits, `collection_exists` (empty vs nonexistent collection), and `snapshot: false`.

### Voyage AI suggestions (`suggest.py`, opt-in)

- Off by default.
- `GUARD_SUGGESTIONS=lexical` gives offline text-similarity suggestions.
- `GUARD_SUGGESTIONS=voyage` plus `VOYAGE_API_KEY` uses Voyage embeddings (default `voyage-4-lite`).
  - One batched request per scan, because free tiers can be limited to 3 requests a minute.
  - 10-second timeout; it falls back to lexical on any error.
  - The model and URL are configurable (`VOYAGE_EMBED_MODEL`, `VOYAGE_API_URL`).
- **What it adds:**
  - `distinct_values[].suggestions`, e.g. `PG13` → `PG-13`
  - `changes[].rename_candidates`, e.g. `runtime` → `duration_minutes`
- **Only suggests.** Plans and counts are identical with or without it (tested).
- **Privacy:** only bad values, enum values and field names are sent. Never ids, documents or the URI (tested).
- **Reranker mode** (`GUARD_SUGGESTIONS=voyage-rerank`, default model `rerank-2.5`): usually more accurate for "which allowed value did they mean?".
  - It costs one request per bad value, capped at 20 per scan. Values beyond the cap still get offline suggestions.
  - `scan.suggestions.semantic_jobs` shows how many values were scored.
- **Tunable without code changes:** `VOYAGE_MIN_SCORE` (threshold for the active Voyage mode), `VOYAGE_RERANK_MODEL`.

### MongoDB Atlas Vector Search (`vector_search.py`, `GUARD_SUGGESTIONS=atlas-vector`)

**How it works:**

1. One Voyage AI embeddings call vectorises the allowed values and the bad values.
2. The allowed-value vectors are upserted into a **dedicated vocabulary collection** named explicitly by `GUARD_VECTOR_COLLECTION` (`database.collection`).
3. A `vectorSearch` index (`schema_guard_suggestions`: cosine, pre-filter fields `group` and `model`) is created if missing, and the engine waits until it's queryable.
4. Each bad value runs **`$vectorSearch`** (first stage, pre-filtered to its field, `numCandidates` at least 20× `limit`, as MongoDB guidance says).
5. `vectorSearchScore` is converted back to cosine, so thresholds match the in-memory mode.

**Write boundary:**
- Nothing is written unless `GUARD_VECTOR_COLLECTION` is set.
- It refuses to use the scanned collection.
- Bad values are only query vectors; they are never stored.
- The vocabulary holds only allowed values and field paths.

**Fallback:**
- With no Atlas Search (e.g. local Community `mongod`), the index still building, or a dimension mismatch, it uses in-memory cosine on the same vectors.
- `scan.suggestions` records the reason. Renames always use the in-memory vectors.

**Verification:**
- Unit tests with a fake Atlas cover the index definition, the pipeline shape, the score conversion, idempotent upserts, waiting for the index, and every fallback.
- On the local `mongod`, tests prove the write boundary and the fallback.
- The live Atlas test is opt-in: `SCHEMA_GUARD_ATLAS_VECTOR_URI` plus `VOYAGE_API_KEY`, on a disposable cluster.

### Stretch goals (added later the same day)

- **Bad values for array items.** `genres[]`, `cast[].name` and enum lists (`tags[]`) now get `distinct_values` too.
  - Counts are documents containing the value; a value repeated inside one document counts once.
  - Uses `$filter`/`$map` before `$unwind`, so only bad elements are expanded (MongoDB aggregation guidance).
  - Arrays nested in arrays (`grid[][]`) are still not offered.
- **Schema versioning analysis.** New top-level `versioning`:
  - a per-version breakdown (`total`, `failing`, `newly_failing`) when documents carry `schemaVersion`; the field is configurable via `GUARD_VERSION_FIELD` or `version_field=`, and `""` turns it off
  - `bump_recommended` and `breaking_changes`, taken from the diff's compatibility labels
  - a plain-English message, e.g. "no `schemaVersion` field — consider adding one so old and new shapes can coexist"
  - Analysis only; adding or migrating versions writes data, so that's Person 3's side.
- **Real time-limit test.** The local test `mongod` starts with test commands enabled. The `maxTimeAlwaysTimeOut` failpoint proves MongoDB itself stops the scan (`ExecutionTimeout`) and the server returns its clean 502 without leaking the URI. On servers without failpoints (e.g. Atlas) this test skips.
- **Atlas measurement tool** (`python -m schema_guard.engine.measure`), read-only:
  - Runs the scan N times; the counts must not change.
  - Cross-checks `total`, `failing`, `preexisting` and `newly_failing` against MongoDB's own `count_documents`.
  - Confirms example ids exist and fail, and records the server version and current validator.
  - Saves `reports/engine-measure-<timestamp>.json` and refuses to save output containing the URI.
  - Exit code 0 = all checks pass, 1 = a check failed, 2 = configuration or connection problem.
  - Tests prove it catches a wrong count and non-reproducible counts.

## Test results (2026-10-03, after stretch goals)

| Suite | Result |
| --- | --- |
| Whole repo `pytest -q` | **213 passed**, 2 skipped (the live Voyage and live Atlas Vector Search checks need keys) |
| `tests/engine` unit (translator 36, JSON Schema 32, diff 14, specs 25, compat 7, suggest 20, vector search 23) | all pass |
| `tests/engine/integration` on a real `mongod` 6.0.21 (local, throwaway) | **50 passed** (34 core + 14 stretch + 2 vector), 1 live-Atlas test skipped |
| Starter `tests/test_workflow.py` | 5 passed, unchanged |
| `npm --prefix frontend run build` | passes; same bundle as before |
| CLI with JSON schema files | `7 of 12` demo result, the same as with Python models |

The real-MongoDB tests check exact hand-computed counts on a 28-document "zoo", covering:

- missing values, null, `"118"`, `"N/A"`, `[90]`, `90.0`, `true`, a 64-bit int (`NumberLong`), enum outliers
- mixed-type arrays, `imdb: {}`, `imdb: [..]`, nested missing and wrong-typed fields
- one document with several problems, a missing defaulted field, and old-schema drift

They cross-check everything against MongoDB's own `$jsonSchema` counts and `find()` results. They also prove:

- the scan is read-only and deterministic
- two-pass equals single-pass
- the demo's 12 → 7 matches real MongoDB
- Person 3's unchanged server works end to end with JSON schema files on a real database

**Recorded MongoDB behaviour (6.0.21):**

- **Enums:** an enum `[1, 2]` accepts `1`, `1.0`, `NumberLong(1)` and `Decimal128("1")`, and rejects `"1"`, `3` and `true`. Our nested `$in` check agrees with `$jsonSchema`.
- **Query `$type` vs aggregation `$type`:** query `{runtime: {$type: "string"}}` also matches `["90"]` (array traversal), while the engine correctly reports that value as an array.

## How to run

```bash
.venv/bin/python -m pytest -q                         # everything (real-MongoDB tests auto-start a local mongod)
.venv/bin/python -m pytest -q tests/engine            # only my tests
SCHEMA_GUARD_SKIP_MONGO=1 .venv/bin/python -m pytest -q   # skip the real-MongoDB tests
.venv/bin/schema-guard --demo --old examples/engine/movie_old.schema.json --new examples/engine/movie_new.schema.json
GUARD_SUGGESTIONS=lexical .venv/bin/schema-guard-server   # dashboard with offline suggestions
```

**Local environment note:** the Desktop is synced to iCloud, which kept marking `.venv` files as hidden, and Python 3.14 then skipped them, so the package "disappeared". Fixed by renaming the folder to `.venv.nosync` (iCloud ignores `*.nosync`), with a `.venv` shortcut pointing to it. Both are excluded via `.git/info/exclude` (local only). Teammates on iCloud desktops can do the same.

## Known gaps (engine)

- Distinct values are not offered for arrays nested inside arrays (`grid[][]`, `cast[].roles[]`). One level of array is supported.
- JSON Schema `additionalProperties: false` is rejected (MongoDB documents also have `_id`). Supporting it needs a new "unexpected field" reason.
- JSON Schema `format: date-time` stays `string`. Use `bsonType: "date"` in the file if dates are stored as BSON dates.
- `float` accepts BSON `decimal` (like the starter), but Pydantic cannot read `Decimal128` as a float. Revisit after seeing real data.
- `unclassified` is still computed from root reasons only, so its meaning is unchanged.
- Not yet tested against MongoDB 8.x (Atlas). The local server is 6.0.21.

## Merge check with Person 3's `fixes/backend` (2026-10-03)

- **Person 3's commit** `cee7231` ("complete reviewed backend restore contract") touches `fixes.py`, `server.py`, `tests/test_workflow.py` and `TEAM_HANDOFF.md`. None of those overlap with the engine files.
- **What it adds:**
  - `execution_contract` on plans (schema fingerprints, a 30-minute expiry)
  - `/api/demo/restore`
  - `/api/validator` (a `collMod` preview with `validationAction: "warn"`)
- **Trial merge** in a scratch copy, which was then deleted: **no conflicts; 164 passed, 1 skipped**. The engine branch itself was not changed.
- **Still open from their side:**
  - The handoff says Atlas analysis was "verified against the live sample_mflix.movies collection", but no counts are recorded anywhere.
  - None of the engine handoff items below were done yet. They hadn't seen this list.

## Person 3's `ui/integration` branch (seen 14:20, 2026-10-03)

- **Merges:** the engine branch (commits `a8a779f`, `962a02e`) plus `fixes/backend`.
- **Edits to engine files there:**
  - `suggest.py` default Voyage URL changed to `https://ai.mongodb.com/v1`, MongoDB-hosted Voyage for Atlas-issued keys (verified by Person 3); its test was updated to match
  - a compat test was extended for the new `report.py` fields
- **Carried into this branch** (the URL and matching test changes), so merging the stretch-goal commit won't conflict.
- **Also on that branch:** `report.py` passes through `warnings` and `scan`; there's AI-suggestion UI guidance in `TEAM_HANDOFF.md` and `AGENTS.md`.

## Handoff: for Person 3 (including Atlas)

Person 3 owns Atlas and their own files, so I didn't do any of this. Item 8 is new after reading their branch; item 9 came with the stretch goals.

1. **Atlas live verification (read-only).**
   - Load `sample_mflix` and use a database user with only the `read` role.
   - Set `MONGODB_URI` in `.env`.
   - Run `.venv/bin/python -m schema_guard.engine.measure --runs 2`. It runs the scan twice, cross-checks every count against MongoDB, prints PASS/FAIL, and saves a dated JSON under `reports/` (never containing the URI).
   - Exit code 0 means every check passed.
   - Paste the printed summary (with date and cluster tier) into this file or `docs/VALIDATION.md`.
2. **Run my real-MongoDB tests against Atlas's server version.** Set `SCHEMA_GUARD_TEST_URI` to a **disposable** Atlas database or cluster, then run `pytest -q tests/engine/integration`. The tests insert and drop their own collections, so **never point this at `sample_mflix` or production.**
3. **Real-data example models.** After looking at `sample_mflix`, write `examples/engine/models_mflix_{old,new}.py` (or JSON) with nested `imdb`, `awards`, `genres`, `cast` and `rated`. Then demo it via `GUARD_OLD_MODEL/GUARD_NEW_MODEL`.
4. **`report.py` (your file):** ✅ `warnings` and `scan` were added by Person 3 on `ui/integration` (commit `226e1eb`). **Still needed:** one more line for the schema-versioning output added later:

   ```python
   "versioning": impact.get("versioning"),
   ```

5. **`fixes.py` (your file):** in `make_plan`, skip reasons where `reason.get("location", "field") != "field"` when creating default operations. Nested reasons share the root `field`, so a root default would otherwise be labelled with a nested count. Consider offering mappings only for `distinct_values` with `mappable: true`.
6. **`demo.py` (optional):** call `impact.summarize_values(...)` per reason, so fixture reports also carry `distinct_values` and the UI can build mapping controls offline.
7. **Voyage AI integration.** See the separate brief, [BRIEF_PERSON3_AI.md](BRIEF_PERSON3_AI.md).
   - Includes **verifying Atlas Vector Search** on a disposable Atlas cluster: run `tests/engine/integration/test_engine_vector_real.py` with `SCHEMA_GUARD_ATLAS_VECTOR_URI` and `VOYAGE_API_KEY` set.
8. **`/api/validator` (your new endpoint), nice to have:**
   - MongoDB's schema-validation guidance suggests `validationLevel: "moderate"` with `"warn"` when adding rules to a collection that already has bad documents. Today the endpoint uses `"strict"`.
   - The engine's `load_collection_validator()` can read the collection's *current* validator and settings, so the preview could show "current vs proposed" before any `collMod`.
9. **Schema versioning migrations (stretch).** The engine now reports failing documents per `schemaVersion` and recommends a bump on breaking changes. Actually adding `schemaVersion` and migrating documents writes data, so it belongs with your backup and restore flow, on a disposable collection first.

## Handoff: for Person 1 (UI and integration)

- **Optional new fields** to add to `frontend/src/types.ts` / `docs/API.md`. They're all additive; the existing keys are unchanged.
  - **reasons:** `path`, `location`, `count_newly`, `count_preexisting`, `explanation`, `distinct_values[{value, bson_type, count, mappable, truncated?, suggestions?}]`, `distinct_value_count`, `distinct_values_limited`
  - **changes:** `parent`, `details`, `compatibility`, `compatibility_reason`, `rename_candidates?`
  - **report** (after Person 3's `report.py` lines): `warnings[]`, `scan`, `versioning{field, versioned, versions[], bump_recommended, breaking_changes[], message}`
- **UI ideas:**
  - group nested reasons under their root `field`
  - mapping controls from `distinct_values` where `mappable`
  - a "breaking / compatible" badge on model changes
  - a warnings panel
  - suggestions labelled clearly as suggestions
