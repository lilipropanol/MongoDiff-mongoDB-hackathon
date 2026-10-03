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

## Test results (2026-10-03)

| Suite | Result |
| --- | --- |
| Whole repo `pytest -q` | **163 passed**, 1 skipped (the live Voyage check needs a key) |
| `tests/engine` unit (translator 36, JSON Schema 32, diff 14, specs 21, compat 7, suggest 14) | all pass |
| `tests/engine/integration` on a real `mongod` 6.0.21 (local, throwaway) | **34 passed** |
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

- Distinct values are not offered for array elements (`genres[]`). That would need an `$unwind` facet.
- JSON Schema `additionalProperties: false` is rejected (MongoDB documents also have `_id`). Supporting it needs a new "unexpected field" reason.
- JSON Schema `format: date-time` stays `string`. Use `bsonType: "date"` in the file if dates are stored as BSON dates.
- `float` accepts BSON `decimal` (like the starter), but Pydantic cannot read `Decimal128` as a float. Revisit after seeing real data.
- `unclassified` is still computed from root reasons only, so its meaning is unchanged.
- Not yet tested against MongoDB 8.x (Atlas). The local server is 6.0.21.

## Handoff: for Person 3 (including Atlas)

Person 3 owns Atlas and their own files, so I didn't do any of this.

1. **Atlas live verification (read-only).**
   - Load `sample_mflix` and use a database user with only the `read` role.
   - Set `MONGODB_URI` in `.env`.
   - Run `schema-guard --database sample_mflix --collection movies` twice. The counts must match.
   - Record the numbers (with date and cluster tier) in this file or `docs/VALIDATION.md`.
   - Check that the URI never appears in `reports/`.
2. **Run my real-MongoDB tests against Atlas's server version.** Set `SCHEMA_GUARD_TEST_URI` to a **disposable** Atlas database or cluster, then run `pytest -q tests/engine/integration`. The tests insert and drop their own collections, so **never point this at `sample_mflix` or production.**
3. **Real-data example models.** After looking at `sample_mflix`, write `examples/engine/models_mflix_{old,new}.py` (or JSON) with nested `imdb`, `awards`, `genres`, `cast` and `rated`. Then demo it via `GUARD_OLD_MODEL/GUARD_NEW_MODEL`.
4. **`report.py` (your file):** two lines so warnings and scan info reach saved reports. Today they're computed but dropped by `build_report`:

   ```python
   "warnings": impact.get("warnings", []),
   "scan": impact.get("scan"),
   ```

5. **`fixes.py` (your file):** in `make_plan`, skip reasons where `reason.get("location", "field") != "field"` when creating default operations. Nested reasons share the root `field`, so a root default would otherwise be labelled with a nested count. Consider offering mappings only for `distinct_values` with `mappable: true`.
6. **`demo.py` (optional):** call `impact.summarize_values(...)` per reason, so fixture reports also carry `distinct_values` and the UI can build mapping controls offline.
7. **Voyage live check.** Set `VOYAGE_API_KEY` and `SCHEMA_GUARD_LIVE_VOYAGE=1` and run `pytest -q tests/engine/test_engine_suggest.py`.
   - Keys created in the Atlas console may need a different `VOYAGE_API_URL`; check the current docs.
   - Tune `VOYAGE_MIN` in `suggest.py` if suggestions are too eager or too shy on real `rated` values.

## Handoff: for Person 1 (UI and integration)

- **Optional new fields** to add to `frontend/src/types.ts` / `docs/API.md`. They're all additive; the existing keys are unchanged.
  - **reasons:** `path`, `location`, `count_newly`, `count_preexisting`, `explanation`, `distinct_values[{value, bson_type, count, mappable, truncated?, suggestions?}]`, `distinct_value_count`, `distinct_values_limited`
  - **changes:** `parent`, `details`, `compatibility`, `compatibility_reason`, `rename_candidates?`
  - **report** (after Person 3's `report.py` lines): `warnings[]`, `scan`
- **UI ideas:**
  - group nested reasons under their root `field`
  - mapping controls from `distinct_values` where `mappable`
  - a "breaking / compatible" badge on model changes
  - a warnings panel
  - suggestions labelled clearly as suggestions
