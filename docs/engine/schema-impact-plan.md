# Person 2 — Schema & impact: implementation plan

Status: **implemented** (2026-10-03). See [PROGRESS.md](PROGRESS.md) for what was built, test results, and the handoff list. Code now lives in `schema_guard/engine/`, tests in `tests/engine/`. Atlas work was left to Person 3. This plan is kept for reference.

Branch: `engine/atlas-analysis` (already created locally, no commits yet).

---

## 1. Goal and acceptance (from TEAM_HANDOFF.md)

Produce a **verified live impact report** on the real Atlas `sample_mflix.movies` collection:

- The unique failing count is independent of the overlapping per-reason counts.
- Old-schema drift (`preexisting`) is kept separate from new violations (`newly_failing`), and the difference is easy to understand.
- Nested models give useful paths (`imdb.rating`, `cast[]`) instead of only the root field.
- Optional/defaulted fields that are missing in storage produce **warnings**, not failures.
- Reasons carry **bounded distinct bad values**, so the UI can build mapping controls without full documents.
- Unsupported Pydantic behaviour fails with a clear error instead of producing a wrong schema.
- Scan size, timeout and example limits are defensible, and empty or missing collections are reported correctly.
- Tests cover missing fields, nulls, string integers, an unconvertible value, enum outliers, mixed-type arrays, aliases and nested required fields, **against a real MongoDB server**.
- Observed counts are reproducible.

## 2. Ground rules for this branch

- **Files I own and will edit:** `schema_guard/translator.py`, `diff.py`, `impact.py`, `models.py`.
- **New files only (no conflicts possible):**
  - `tests/test_engine_*.py`
  - `tests/integration/*`
  - `examples/models_mflix_*.py`
  - `tools/measure_atlas.py`
  - `docs/ENGINE_NOTES.md`
  - this plan
- **Not edited by me:** `server.py`, `cli.py`, `report.py`, `fixes.py`, `demo.py` (Person 3), `frontend/`, `docs/API.md`, `docs/VALIDATION.md` (Person 1), `pyproject.toml`, `tests/test_workflow.py`. Section 7 has the 3 small, optional requests for other owners.
- **No new dependencies.** pymongo, pydantic and pytest are enough. No `mongomock`: it does not implement `$jsonSchema`/`$facet` faithfully, and verifying real semantics is the whole point.
- **Every change is additive to the report.** Existing keys and meanings stay the same, and `analyze_collection(...)` keeps its current signature (new parameters are keyword-only with defaults), so `server.py` and `cli.py` work unchanged.
- **Atlas stays read-only.** Integration tests write only to a throwaway local `mongod`, never to Atlas.

## 3. What I found in the current code (verified, 2026-10-03)

I ran probes against the starter code to check these.

| # | Finding | Impact | Fix in this plan |
| --- | --- | --- | --- |
| F1 | `fixes.make_plan` does `props[reason["field"]]`. A reason with `field: "imdb.rating"` raises **`KeyError` → HTTP 500 on `/plan`**. | Nested reasons cannot simply put the dotted path in `field`. | Keep `field` = root field, add a new `path` key (§4.3). |
| F2 | `demo.analyze_demo` calls `impact.reason_specs()` and looks up `new_schema["properties"][field]`. | If `reason_specs` starts returning nested specs, the demo breaks or miscounts. | Leave `reason_specs()` output **byte-for-byte unchanged**; nested specs come from a new function. |
| F3 | `Field(exclude=True)` is translated as a required stored field, but Pydantic never writes it. | Wrong schema, silently. | Raise `TypeError`. |
| F4 | `@field_serializer` / `@model_serializer` are ignored. | Stored shape may differ from the annotation, silently. | Raise `TypeError`. |
| F5 | `validation_alias="a", serialization_alias="b"` → schema uses `b` silently; documents written as `b` would be read back from `a`. | Ambiguous stored key. | Raise when they differ. |
| F6 | A recursive model gives a bare `RecursionError` (the server turns it into a cryptic 422). | Unclear error. | Detect cycles: `TypeError("Recursive model Node is not supported")`. |
| F7 | `reason_specs` only explains root fields; nested problems all show up as `nested_or_array_constraint` on the root. | Not actionable. | Deep reasons (§4.3). |
| F8 | No distinct-value summaries, no missing-default warnings, no per-reason split between new and pre-existing. | Handoff items. | §4.4–4.6. |
| F9 | Empty and nonexistent collections both report `total: 0`. A typo in `MONGODB_COLLECTION` looks like "all fine". | Misleading. | `scan.collection_exists` (§4.7). |
| F10 | Every reason facet runs over **all** documents, with up to 3 facets per reason. | Slow on big collections or Atlas M0. | Two-pass scan (§4.7). |
| F11 | `models.py` names modules `schema_guard_model_<stem>`, so two files called `models.py` in different folders collide in `sys.modules`. | Forward references can resolve against the wrong module. | Add a path hash to the module name. |

Things that are **already right** and need tests to lock in:

- Field-level type checks use aggregation `$type` inside `$expr`. That returns `"array"` for an array instead of matching elements the way query `{f: {$type: "string"}}` does.
- Missing and null are distinguished.
- `alias_generator` works.
- An `Enum` subclass raises a clear "Unsupported field type".

## 4. Design

### 4.1 Translator audit (`translator.py`)

Keep `translate(model) -> dict` output identical for every model that works today. Add checks that raise `TypeError` with an actionable message:

| Case | Behaviour |
| --- | --- |
| `Field(exclude=True)` | Raise: "`secret` is excluded from serialization, so it is never stored; remove it from the model or mark it unsupported". |
| `field_serializers` / `model_serializers` present | Raise: "Custom serializer on X changes the stored shape; not supported". |
| String `validation_alias` ≠ serialization key | Raise with both names. |
| Recursive / self-referencing models | Track a `_stack` of model classes during translation; raise on re-entry. |
| `extra="forbid"`, validators, constraints, `AliasPath`/`AliasChoices`, `$`/`.` names | Already raise. Add tests. |
| Unsupported annotation (`dict`, `Any`, `UUID`, `Decimal`, `date`, `set`, `tuple`, bare `list`) | Already raise "Unsupported field type". Add tests and include the **field path** in the message (today the message doesn't say which field). |

Optional small wins (see Decisions D5 and D2):

- `Enum` subclasses → `{"enum": [member.value, ...]}`.
- `float` currently allows BSON `decimal`, but PyMongo returns `Decimal128`, which Pydantic `float` rejects on read. Either drop `"decimal"` or keep it and explain it.

Error messages include the dotted path (`imdb.rating`) by threading a `path` argument through `translate`/`field_schema`. That is an internal signature, called only from inside the translator.

### 4.2 Diff with nested paths (`diff.py`)

- Recurse into `properties` when both old and new are objects. Recurse into `items` with the suffix `[]` (`cast[]`, `cast[].name`).
- **Keep the existing root entries unchanged** (UI and compatibility). Nested entries are added with `field` = full path, plus `parent` = root field. Nothing downstream looks up `changes[].field` in the schema; I checked `fixes.py`, `impact.py` and `demo.py`.
- Add a `details` object to `type_or_constraint_changed` entries (additive):

  ```json
  {"types_added": ["string"], "types_removed": ["null"],
   "enum_added": ["PG-13"], "enum_removed": [],
   "nullable": {"old": true, "new": false}}
  ```

- New kind `became_optional` (required → not required), alongside the existing `became_required`.

### 4.3 Deep reasons with exact locations (`impact.py`)

New function `deep_reason_specs(schema) -> list[spec]`. Each spec has:

```text
field:     root field (unchanged meaning; keeps fixes.make_plan working)
path:      exact location, e.g. "imdb.rating", "genres[]", "cast[].name"
location:  "nested" | "array_element"
reason:    missing | null_not_allowed | wrong_type | value_not_allowed
expr:      an aggregation boolean expression (used inside {$expr: ...})
value:     aggregation expression for the offending value (for distinct values), or None
```

**Every nested check is written as an aggregation expression, never as a query-language path.** This avoids MongoDB's implicit array traversal: `{"imdb.rating": {$exists: false}}` behaves differently when `imdb` is an array.

- **Nested object field** (parent must really be an object):

  ```json
  {"$and": [{"$eq": [{"$type": "$imdb"}, "object"]},
            {"$eq": [{"$type": "$imdb.rating"}, "missing"]}]}
  ```

- **Array elements**: does any element violate the rule? Non-arrays count as an empty list, so they don't double-count with the root `wrong_type`.

  ```json
  {"$anyElementTrue": [{"$map": {
     "input": {"$cond": [{"$isArray": "$genres"}, "$genres", []]},
     "as": "e0",
     "in": {"$not": [{"$in": [{"$type": "$$e0"}, ["string"]]}]}}}]}
  ```

  Nested arrays use `e1`, `e2`, … Objects inside arrays use `$$e0.name`.

- **Enums in nested positions** use `$in` against the enum list, guarded by present and non-null. Integration tests check this agrees with `$jsonSchema`'s own enum semantics, for example `1` vs `1.0` vs `NumberLong(1)`.

How this goes into the report:

- Root reasons from the existing `reason_specs()` are emitted exactly as today, with `path = field` and `location = "field"` added.
- Deep reasons are appended, sharing `field` with their root. The root `nested_or_array_constraint` reason stays as the **group header**: the unique count of documents with *something* wrong inside that root field. Person 1's "root-field nested issue presentation" task can group children under it by `field`.
- `unclassified` is unchanged (it is still computed from root reasons), so its meaning doesn't shift.

### 4.4 Distinct bad values for mapping controls (`impact.py`)

For `wrong_type` and `value_not_allowed` on root and nested-object scalar paths (array elements are a stretch goal), add a facet after the reason match:

```text
[{$match: reason}, {$group: {_id: {v: <value>, t: {$type: <value>}}, n: {$sum: 1}}},
 {$sort: {n: -1, "_id.t": 1}}, {$limit: K}]
```

Plus a `$count` of distinct groups.

- The group key includes the **BSON type**. `$group` treats `1`, `1.0` and `NumberLong(1)` as equal, and the UI needs to know `"118"` (string) is different from `118`.
- Only scalar values are returned. For objects and arrays, `v` is replaced by `null` and only the type is reported, so no documents leak.
- Strings are truncated to 80 code points **in Python after the query** (grouping stays exact), with `truncated: true`.
- Output per reason (additive):

  ```json
  "distinct_values": [{"value": "PG13", "bson_type": "string", "count": 412, "mappable": true}],
  "distinct_value_count": 37, "distinct_values_limited": true
  ```

- `mappable` is true only when `bson_type == "string"` and `location == "field"`, which matches what `fixes.make_plan` supports today (string keys, root fields). That stops the UI offering mappings the backend can't execute.

### 4.5 Missing-default warnings (`impact.py`)

- A property **not** in `required` has a default: the translator only marks fields required when Pydantic says `is_required()`. For each optional field (root, and nested when the parent is an object), count documents where it is missing.
- Output: `warnings: [{field, path, kind: "missing_defaulted_field", count, message}]`, where the message says: "Missing in N stored documents. Pydantic fills the default when reading, but MongoDB queries, indexes and validators see the field as absent."
- Warnings never affect `failing`.
- `report.py` (Person 3) copies only known keys, so top-level `warnings` and `scan` won't reach the saved report until the integrator adds a passthrough at merge time. **We don't edit that file.** Warnings are still in `analyze_collection`'s return value and fully tested. Everything placed *inside* `reasons` (paths, distinct values, explanations, new/pre-existing split) reaches the report with no change anywhere else. See §7.

### 4.6 Making drift understandable (`impact.py`)

Per reason, add `count_newly` (documents matching this reason **and** valid under the old schema) and `count_preexisting = count - count_newly`. For example: "runtime missing: 1,200 newly affected, 0 already violating".

Per reason, also add a plain-language `explanation` built from the reason, schema and distinct values. For example, for wrong_type `"118"` on an int field: "Stored as a string. MongoDB checks BSON types strictly, so "118" fails `int` even though Pydantic's default (lax) mode would accept it on read." This puts the strict-BSON vs coercive-Pydantic difference into words for the UI.

### 4.7 Limits, empty collections, performance (`impact.py`)

- **Two-pass scan:**
  1. One aggregate computes `total`, `failing`, `preexisting`, `newly_failing` and warning counts over all documents.
  2. A second aggregate starts with `$match: invalid` and runs every reason facet only over failing documents.

  Results are identical, with much less work when most documents pass.
- **Limits** are keyword-only parameters with validated defaults (`ValueError` outside range):

  | Limit | Default | Range | Why |
  | --- | --- | --- | --- |
  | `examples` | 3 | 0–5 | Existing; keeps `$facet` output small |
  | `distinct_limit` | 10 | 0–50 | Enough for a mapping form |
  | `max_time_ms` | 30000 per aggregate | 1000–60000 | Existing behaviour; server socket timeout is 35s |
  | Example arrays | sliced to 5 elements | — | A `cast` list can be long |
  | Example strings | truncated to 200 chars | — | `fullplot` can be large |

  The `$facet` result must stay under 16 MB. These bounds keep it in the KB range.
- **Empty vs missing collection:** `collection.database.list_collection_names(filter={"name": ...})` (works with the Atlas `read` role) sets `scan.collection_exists`. The report says so instead of a silent 0.
- **`scan` metadata** (needs the same `report.py` passthrough):

  ```json
  {"duration_ms": 812, "max_time_ms": 30000, "examples": 3, "distinct_limit": 10,
   "collection_exists": true, "two_pass": true, "snapshot": false}
  ```

  `snapshot: false` makes it explicit that concurrent writes can shift counts.

### 4.8 Richer real-data example models (new files)

`examples/models_mflix_old.py` and `examples/models_mflix_new.py`: Movie models using the real nested shape of `sample_mflix.movies`, e.g. `imdb: Imdb` (`rating`, `votes`, `id`), `awards: Awards`, `genres: list[str]`, `cast: list[str]`, `rated: Literal[...]`. The live demo exercises nested paths, arrays and enum outliers.

- Selected via the existing `GUARD_OLD_MODEL` / `GUARD_NEW_MODEL` in `.env`. No server change.
- The default `examples/models_old.py` / `models_new.py` stay untouched, because the fixture tests depend on them.
- **No counts are promised.** Fields are chosen after a baseline look at the real data (phase 0), e.g. whether `imdb.rating` contains empty strings and which `rated` values exist.

## 5. Phases (mapped to the handoff's timeline)

**Cut line if time runs short:** phases 0–1 plus distinct values (§4.4), because the UI owner is waiting on them. Then warnings and nested reasons.

### Phase 0 — setup and baseline (~20 min)

1. Atlas: create or confirm a cluster and load the **sample dataset**. Create a **read-only** database user (`read` on `sample_mflix`) and allow your IP.
2. `.env`: set `MONGODB_URI` (the read-only user). It is already git-ignored.
3. Baseline with the unchanged starter: `.venv/bin/schema-guard --database sample_mflix --collection movies --output reports/baseline-starter.json`. Save the numbers into `docs/ENGINE_NOTES.md` as "starter baseline, unverified".
4. Local integration server: confirm `mongod` (v6.0.21 is on this machine) starts with a temp `--dbpath`. Write `tests/integration/conftest.py` (§6.2).

### Phase 1 — verify the existing engine on real MongoDB, then harden (~90 min)

1. Integration tests T-I1…T-I12 (§6.2) against the **current** `impact.py`. Fix any semantic bugs they reveal first.
2. Translator audit (§4.1) plus unit tests (§6.1 U-T).
3. Diff nested paths (§4.2) plus U-D tests.
4. Deep reasons (§4.3) plus U-R and T-N tests.

### Phase 2 — UI-facing data (~60 min)

1. Distinct values (§4.4) plus T-V tests. **Tell Person 1 the shape as soon as it's stable.**
2. Per-reason new/pre-existing split and explanations (§4.6).
3. Missing-default warnings (§4.5) plus T-W tests.
4. Limits, two-pass scan and the empty/missing collection flag (§4.7) plus T-L tests.

### Phase 3 — live verification and handoff (~40 min)

1. `tools/measure_atlas.py` on real `sample_mflix` (§6.3). Run it twice; the counts must match.
2. Write `docs/ENGINE_NOTES.md`: verified semantics, measured counts (labelled with date, dataset and models), limits, and known differences from Pydantic.
3. Write the integration notes (§7) into the handoff. No edits to other people's files.
4. Full checks: `pytest -q` (unit plus integration), `npm --prefix frontend run build` (it shouldn't change, but confirms nothing broke).
5. Commit, then **you review before push**. Post the handoff (§8).

## 6. Test plan

All new test files are mine. `tests/test_workflow.py` stays untouched and **must keep passing**; it is the guard that the demo and UI flow are unaffected.

### 6.1 Unit tests (no MongoDB, run everywhere)

**`tests/test_engine_translator.py`**

| ID | Case | Expect |
| --- | --- | --- |
| U-T1 | Each supported scalar: `str,int,float,bool,datetime` | Exact `bsonType`, e.g. int → `["int","long"]` |
| U-T2 | `Optional[int]` without default | Required **and** nullable |
| U-T3 | `Optional[int] = None` | Not required, nullable |
| U-T4 | `Literal["G","PG"]` and `Optional[Literal[...]]` | `enum`, with `None` appended for Optional |
| U-T5 | `list[str]`, `list[Model]`, `list[list[int]]` | Nested `items` |
| U-T6 | Nested model, and nested Optional model | Nested `properties`/`required`; `["object","null"]` |
| U-T7 | `Field(alias="_id")`, `serialization_alias`, `alias_generator=to_camel` | Stored keys use the alias |
| U-T8 | `Field(exclude=True)` | `TypeError` mentioning "excluded" |
| U-T9 | `@field_serializer`, `@model_serializer` | `TypeError` mentioning "serializer" |
| U-T10 | `validation_alias` ≠ `serialization_alias` | `TypeError` naming both |
| U-T11 | Self-recursive and mutually recursive models | `TypeError("Recursive model ...")`, not `RecursionError` |
| U-T12 | `Field(gt=0)`, `Annotated[str, Field(max_length=3)]`, `Field(strict=True)` | `TypeError` "Unsupported constraints" |
| U-T13 | `extra="forbid"` (root and nested) | `TypeError` |
| U-T14 | `dict`, `Any`, `UUID`, `Decimal`, `date`, `set[str]`, `tuple`, bare `list`, `int \| str` | `TypeError` whose message contains the **field path** |
| U-T15 | `$`-prefixed / dotted alias | `TypeError` |
| U-T16 | Regression: translate `examples/models_old.py` and `models_new.py` | **Identical** to the starter output (snapshot) |
| U-T17 | (if D5) `str` Enum and `int` Enum | `enum` of member values |

**`tests/test_engine_diff.py`**

| ID | Case | Expect |
| --- | --- | --- |
| U-D1 | Starter example models | Same root entries as today (snapshot) |
| U-D2 | Nested field added, removed, type changed (`imdb.rating` float → str) | Entries with `field: "imdb.rating"`, `parent: "imdb"` |
| U-D3 | Nested field became required / optional | `became_required` / `became_optional` at the nested path |
| U-D4 | `list[str]` → `list[int]` | Change at `genres[]` |
| U-D5 | `list[Model]` inner field change | Change at `cast[].name` |
| U-D6 | Enum widened/narrowed | `details.enum_added` / `enum_removed` exact |
| U-D7 | `Optional[int]` → `int` | `details.nullable == {"old": true, "new": false}` |
| U-D8 | Object → scalar at the same key | Root `type_or_constraint_changed`, no recursion crash |
| U-D9 | Identical schemas | `[]` |

**`tests/test_engine_specs.py`**

| ID | Case | Expect |
| --- | --- | --- |
| U-R1 | `reason_specs(new example schema)` | **Unchanged** from the starter (snapshot), which protects `demo.py` (F2) |
| U-R2 | `deep_reason_specs` on a nested model | Expected `(field, path, location, reason)` tuples; `field` is always a root property |
| U-R3 | Every generated `expr` | Uses only `$expr` operators; no query-language dotted paths (walk the dict) |
| U-R4 | Arrays of arrays | Distinct variable names `e0`, `e1` |
| U-R5 | Limits validation | `examples=6`, `distinct_limit=-1`, `max_time_ms=0` → `ValueError` |

**`tests/test_engine_compat.py`** (guards other people's code; I only call it, never change it)

| ID | Case | Expect |
| --- | --- | --- |
| U-C1 | `fixes.make_plan` on a report containing deep reasons, distinct values and warnings | No exception; operations only for root fields |
| U-C2 | `report.build_report(impact, ...)` with the new impact output | Works; the existing keys have the same values |
| U-C3 | `json.dumps(report, default=str)` with `ObjectId`, `Decimal128`, `datetime`, `Int64` in examples and distinct values | Serializes (mirrors `server.save_report`) |
| U-C4 | `demo.analyze_demo(SEED, old, new)` | Still `(12, 7, 2, 5)` and the same reasons |

### 6.2 Integration tests against a real `mongod` (`tests/integration/`)

**Harness (`tests/integration/conftest.py`), session-scoped fixture:**

1. If `SCHEMA_GUARD_TEST_URI` is set, use it. This must be a **disposable** server/database and never Atlas production.
2. Otherwise, if `mongod` is on PATH, start one with `--dbpath <tmp> --port <free> --bind_ip 127.0.0.1`, wait for `ping`, and terminate it at the end.
3. Otherwise `pytest.skip("no MongoDB available")`. Teammates without mongod still get a green `pytest`.
4. Each test gets a fresh collection `t_<uuid>` in database `schema_guard_it` and drops it afterwards.
5. The marker is registered in this conftest via `pytest_configure`, so `pyproject.toml` is not touched.

**The document "zoo".** One corpus, parametrized, built with real BSON types (`Int64`, `Decimal128`, `datetime`, `ObjectId`). Test models are defined in the test file:

```python
class Imdb(BaseModel):  rating: float; votes: int
class Cast(BaseModel):  name: str
class Old(BaseModel):   id: str = Field(alias="_id"); title: str; runtime: Optional[int] = None
class New(BaseModel):   id: str = Field(alias="_id"); title: str; runtime: int
                        rated: Literal["G","PG","PG-13","R"]; genres: list[str]
                        imdb: Imdb; cast: list[Cast]; awards_text: Optional[str] = None
```

| Doc | Content | Expected classification |
| --- | --- | --- |
| z01 | Fully valid | passes |
| z02 | `runtime` missing | `runtime/missing`, newly failing |
| z03 | `runtime: null` | `runtime/null_not_allowed` |
| z04 | `runtime: "118"` | `runtime/wrong_type`; distinct value `"118"` string |
| z05 | `runtime: "N/A"` | `runtime/wrong_type`; distinct value `"N/A"` |
| z06 | `runtime: [90]` and `runtime: ["90"]` | `wrong_type` with type **array**; not reported as a string value |
| z07 | `runtime: 90.0` (double) | `wrong_type` (strict BSON); explanation mentions Pydantic lax |
| z08 | `runtime: true` | `wrong_type` (bool ≠ int) |
| z09 | `runtime: Int64(90)` | passes (long allowed) |
| z10 | `rated: "PG13"`, `"NR"`, `"pg"` | `rated/value_not_allowed`, 3 distinct values |
| z11 | `rated` missing | `rated/missing` |
| z12 | `genres: ["Drama", 1]` | `genres[]/wrong_type` (array_element) |
| z13 | `genres: []` | passes |
| z14 | `genres: "Drama"` | `genres/wrong_type` at root only, **not** also `genres[]` |
| z15 | `imdb: {}` | `imdb.rating/missing` and `imdb.votes/missing`, plus root `nested_or_array_constraint` |
| z16 | `imdb: {rating: "", votes: 5}` | `imdb.rating/wrong_type`, distinct value `""` |
| z17 | `imdb: null` | `imdb/null_not_allowed`; **no** nested reasons |
| z18 | `imdb: [{rating: 1, votes: 1}]` | `imdb/wrong_type` (array); **no** `imdb.rating` reasons (array traversal guard) |
| z19 | `cast: [{name: "A"}, {}]` | `cast[].name/missing` |
| z20 | `cast: [{name: 5}]` | `cast[].name/wrong_type` |
| z21 | Multi-issue: `rated` missing + `runtime: "118"` + `imdb.rating: ""` | Counted **once** in `failing`, in 3 reasons |
| z22 | `awards_text` missing (otherwise valid) | **warning** only; passes |
| z23 | `awards_text: null` | passes; no warning |
| z24 | `imdb.rating: Decimal128("7.1")` | Passes `$jsonSchema` (decimal allowed); note for D2 |
| z25 | Fails the old schema too (`title` missing) | Counted in `preexisting`, not `newly_failing` |

**Tests:**

| ID | Test |
| --- | --- |
| T-I1 | Zoo → exact expected `total`, `failing`, `preexisting`, `newly_failing`, and per-reason counts from the table (hand-computed constants in the test). |
| T-I2 | **Oracle: failing.** `failing == count_documents({"$nor": [{"$jsonSchema": new}]})`. |
| T-I3 | **Oracle: drift.** `preexisting == count({"$nor":[{"$jsonSchema": old}]})`; `newly_failing == count({"$and":[{"$jsonSchema": old}, {"$nor":[{"$jsonSchema": new}]}]})`. |
| T-I4 | **Overlap.** `sum(reason counts) > failing` for the zoo, and every reason count ≤ `failing`. |
| T-I5 | **Examples.** Every `example_ids` entry is in the failing id set (fetched independently with `find`); example keys ⊆ `{_id, field}`; arrays ≤ 5, strings ≤ 200. |
| T-I6 | **Unclassified.** Equals the failing documents matched by no root reason (computed in Python from per-reason `find` id sets). |
| T-I7 | **Array pitfall documented.** Query `{runtime: {$type: "string"}}` *does* match z06 `["90"]`, while our `wrong_type` reports it as an array. This shows why `$expr` is used. |
| T-I8 | **Read-only.** A sorted dump of the collection before and after `analyze_collection` is identical, and the collection's indexes are unchanged. |
| T-I9 | **Deterministic.** Two runs give identical results (ignoring `scan.duration_ms`). |
| T-I10 | **Python cross-check.** Compare MongoDB's failing set with `demo.matches_schema` on the fetched documents. Agreement is expected except for listed known gaps (e.g. Decimal128). Any *other* mismatch fails the test, which catches drift between the demo adapter and the real server. |
| T-I11 | **Enum equality.** With `Literal[1, 2]`, store `1`, `1.0`, `Int64(1)`, `"1"`. Our `value_not_allowed` count equals what `$jsonSchema` itself says (whatever the server decides), and the result is recorded in ENGINE_NOTES. |
| T-I12 | **Starter models.** The demo SEED inserted into real Mongo, analysed with `examples/models_*.py`, gives `(12, 7, 2, 5)` and the same reason counts as the fixture adapter. This proves the demo numbers match real MongoDB. |
| T-N1 | Deep reasons: each `(path, reason)` count matches the zoo table exactly; `field` is always the root. |
| T-N2 | z17/z18: no nested reasons when the parent is null or an array. |
| T-N3 | z14: root `wrong_type` only, no `genres[]` element reason. |
| T-V1 | Distinct values: `runtime/wrong_type` lists `"118"`, `"N/A"` (string) and an array-typed entry with `value: null`; counts are correct and sorted descending. |
| T-V2 | Type-aware grouping: `"1"` and `1` stay separate entries. |
| T-V3 | `distinct_limit=2` → 2 entries, `distinct_values_limited: true`, `distinct_value_count` is the true total. |
| T-V4 | `mappable` is true only for string values on root fields. |
| T-V5 | No full documents: each entry has exactly `{value, bson_type, count, mappable[, truncated]}`. |
| T-V6 | A 500-character bad string → truncated to 80, `truncated: true`, grouped exactly. |
| T-W1 | z22 gives a `missing_defaulted_field` warning with the correct count; it does not increase `failing`. |
| T-W2 | A nested optional field missing → warning at the nested path, only where the parent is an object. |
| T-L1 | Empty existing collection → `total 0`, `collection_exists: true`, no reasons. |
| T-L2 | Nonexistent collection → `collection_exists: false`. |
| T-L3 | Two-pass and single-pass give identical outputs on the zoo (equivalence check of the optimization). |
| T-L4 | `max_time_ms` too small on a large generated collection (e.g. 50k documents) → `ExecutionTimeout` propagates as a `PyMongoError`, so the server's existing 502 handling applies. |
| T-L5 | Per-reason `count_newly + count_preexisting == count` for every reason. |

### 6.3 Live Atlas checks (manual, read-only): `tools/measure_atlas.py`

Run with `.venv/bin/python tools/measure_atlas.py [--old ... --new ...]`. It reads `.env`, and the URI is never printed.

1. Runs `analyze_collection` on `sample_mflix.movies` with both model pairs (starter and mflix).
2. Runs live oracle checks: T-I2 and T-I3 style `count_documents` comparisons, and sampled example ids exist and fail.
3. Prints a summary and writes `reports/atlas-baseline-<timestamp>.json` (`reports/` is git-ignored).
4. Run twice: the counts must be identical (reproducibility acceptance).
5. Safety check: `grep -r "mongodb+srv" reports/ docs/` returns nothing.

The verified numbers go into `docs/ENGINE_NOTES.md`, labelled with the date, cluster tier, dataset and models. They are not put into the pitch until measured.

### 6.4 Commands

```bash
.venv/bin/python -m pytest -q                               # unit + integration (integration skips if no mongod)
.venv/bin/python -m pytest -q tests/integration -v          # real-server semantics only
.venv/bin/python -m pytest -q tests/test_workflow.py        # starter flow must stay green
.venv/bin/python tools/measure_atlas.py                     # live, read-only
npm --prefix frontend run build                             # sanity: nothing broke for the UI
```

## 7. Integration notes for the handoff (we do NOT edit these files)

Rule for this branch: **no edits to Person 1's or Person 3's files.** These notes go into the handoff text, so the UI owner can choose to wire things up during final integration. The engine works without any of them.

1. **`report.py` (Person 3's file):** to surface top-level warnings and scan info, the integrator can add two lines inside `build_report`'s dict:

   ```python
   "warnings": impact.get("warnings", []),
   "scan": impact.get("scan"),
   ```

2. **`frontend/src/types.ts` and `docs/API.md` (Person 1's files):** the optional fields the UI can use:

   ```ts
   export interface DistinctValue { value: unknown; bson_type: string; count: number; mappable: boolean; truncated?: boolean; }
   export interface Reason { /* existing */ path?: string; location?: 'field' | 'nested' | 'array_element';
     count_newly?: number; count_preexisting?: number; explanation?: string;
     distinct_values?: DistinctValue[]; distinct_value_count?: number; distinct_values_limited?: boolean; }
   export interface Warning { field: string; path: string; kind: 'missing_defaulted_field'; count: number; message: string; }
   export interface Report { /* existing */ warnings?: Warning[]; scan?: { duration_ms: number; max_time_ms: number;
     examples: number; distinct_limit: number; collection_exists: boolean; two_pass: boolean; snapshot: false } | null; }
   export interface Change { /* existing */ parent?: string; details?: { types_added?: string[]; types_removed?: string[];
     enum_added?: unknown[]; enum_removed?: unknown[]; nullable?: { old: boolean; new: boolean } }; }
   ```

3. **`demo.py` (Person 3's file):** `impact.summarize_values(values)` is available if anyone later wants demo reasons to carry `distinct_values`. Until then, distinct values appear only in Atlas scans.

## 8. Handoff template (posted with the branch)

```text
Branch: engine/atlas-analysis
Completed behavior: ...
Changed files: schema_guard/{translator,diff,impact,models}.py; new tests/test_engine_*.py, tests/integration/*, tools/measure_atlas.py, examples/models_mflix_*.py, docs/ENGINE_NOTES.md
API/report changes: additive only — §7 (reasons.path/location/distinct_values/…, warnings, scan, changes.parent/details)
Checks run and results: pytest (N unit, M integration on mongod 6.0.21), measure_atlas x2 (identical), frontend build
Remaining gaps: ...
How the UI owner can try it: set GUARD_OLD_MODEL/GUARD_NEW_MODEL to examples/models_mflix_*.py, run Atlas analysis
```

## 9. Decisions for you

| ID | Question | My recommendation |
| --- | --- | --- |
| D1 | Nested reasons: keep `field` = root and add `path` (works with `fixes.py` today), or put the full path in `field` (needs Person 3 to change `make_plan`)? | **Keep root + `path`.** |
| D2 | `float` allows BSON `decimal`, but Pydantic can't read `Decimal128` as float. Drop `"decimal"` or keep it with an explanation? | Keep it for now; document it; revisit after the real-data baseline. |
| D3 | Warnings and scan metadata can't reach the saved report without a `report.py` change, which we won't make. Leave them for the integrator (noted in the handoff), or stuff warnings into `reasons` (pollutes counts and unresolved items)? | **Leave for the integrator.** |
| D4 | Integration tests: auto-start local `mongod` during plain `pytest`, or opt-in via env var only? | Auto-start when on PATH, skip otherwise. |
| D5 | Add `Enum` support (small), or keep it unsupported with a clear error? | Add it if phase 1 finishes on time. |
| D6 | Which real fields go in the mflix models? | Decide after the phase 0 baseline; start with `imdb`, `rated`, `genres`, `cast`, `runtime`. |
| D7 | Limits: distinct K=10, string cut 80, example array 5 / string 200, 30s per aggregate. | As listed. |
| D8 | Distinct values for array elements (`genres[]`) need an `$unwind` facet. Include, or leave as a stretch goal? | Stretch goal. |
| D9 | Voyage AI: opt-in (off unless `VOYAGE_API_KEY` and `GUARD_SUGGESTIONS=voyage` are set), or on whenever a key exists? | **Opt-in.** It sends bounded data values to an external API. |
| D10 | Voyage calls via stdlib `urllib` (no dependency change), or the `voyageai` SDK (needs a `pyproject.toml` edit)? | **stdlib `urllib`.** |

## 10. Technologies

| Area | Technology |
| --- | --- |
| Language / models | Python 3.14 (venv), Pydantic v2 (2.13.x) for model introspection |
| Database driver | PyMongo 4.18 (`aggregate`, `count_documents`, `list_collection_names`, BSON types) |
| MongoDB features | `$jsonSchema` validation queries; aggregation `$facet`, `$match`, `$expr`, `$type`, `$map`, `$anyElementTrue`, `$isArray`, `$group`, `$sort`, `$limit`, `$count`; `maxTimeMS` |
| Live data | MongoDB Atlas, `sample_mflix.movies`, read-only database user |
| Real-server tests | Local `mongod` 6.0.21 (Homebrew) started by a pytest fixture. If possible, also run once against a disposable Atlas database, since Atlas likely runs a newer server (8.x) |
| Tests | pytest (parametrized tables; no new plugins), FastAPI `TestClient` only through the existing tests |
| AI suggestions | Voyage AI (MongoDB) embeddings and reranker over HTTPS, via stdlib `urllib`; `difflib` lexical fallback |
| Not used | `mongomock` (does not emulate `$jsonSchema`/`$facet`), Atlas Vector Search (the vectors are tiny and per-scan, so in-memory cosine is enough) |

## 11. Voyage AI mapping and rename suggestions (phase 4, after the core)

The handoff lists AI suggestions as stretch work, and the human must stay the decision-maker. So Voyage **suggests**; it never fills in decisions or changes counts.

**New file: `schema_guard/suggest.py`.** It's engine-owned, so nobody else's file is touched.

1. **Value-mapping suggestions.** For each reason with `distinct_values`, plus the field's allowed `enum` values: rank candidate targets for each bad value (e.g. `"PG13"` → `"PG-13"`, `"NOT RATED"` → no confident match).
   - First, a cheap lexical normalization: case, spaces and punctuation, via `difflib`.
   - Then Voyage **rerank** (`rerank-2.5`-class model). The query is `"<field> value '<bad>'"`; the documents are the enum values.
   - Alternatively Voyage **embeddings** (`voyage-3.5-lite`-class model) with cosine similarity.
   - Output, additive: `distinct_values[].suggestions: [{target, score, source: "voyage-rerank" | "voyage-embed" | "lexical"}]`, at most 3 per value. Below a score threshold, nothing is suggested.
2. **Rename candidates in the diff.** When a field is `removed` and another is `added` with compatible types, embed `field name + type` and suggest "possible rename" (e.g. `runtime` → `duration_minutes`).
   - Output: `changes[].rename_candidates: [{to, score, source}]`.
   - The handoff says inferred renames need design, so these are labelled hints only.
3. **Wiring.** `analyze_collection` calls `suggest.enrich(result, new_schema)` at the end, only when `GUARD_SUGGESTIONS=voyage` and `VOYAGE_API_KEY` are set. No server change is needed.
4. **Safety.**
   - Only distinct values (already truncated to 80 chars), enum values and field names are sent. Never `_id`, documents, examples or the URI.
   - Requests are batched into one rerank/embedding call per field.
   - 10-second timeout. On error or timeout it falls back to lexical, and `scan.suggestions` records `{provider, model, status, fallback_reason}`.
   - The model names are environment-configurable (`VOYAGE_EMBED_MODEL`, `VOYAGE_RERANK_MODEL`), because Voyage's lineup changes. Check the current model names when implementing.

**Tests (`tests/test_engine_suggest.py`, fake HTTP transport, no network):**

| ID | Case | Expect |
| --- | --- | --- |
| U-S1 | No key, or `GUARD_SUGGESTIONS` unset | No HTTP call; lexical suggestions only, or none |
| U-S2 | Payload capture | Contains only bad values, enum targets and field names; no `_id`, examples or URI |
| U-S3 | Fake rerank scores | Suggestions sorted by score, ≤3, threshold respected |
| U-S4 | Transport timeout / HTTP 429 / malformed JSON | Lexical fallback; `scan.suggestions.status == "fallback"`; scan still succeeds |
| U-S5 | `fixes.make_plan` on an enriched report | Identical operations to the unenriched report (suggestions never become decisions) |
| U-S6 | Counts unchanged | `failing`, reasons and counts are identical with and without enrichment |
| U-S7 | Lexical baseline | `"PG13"` → `"PG-13"`, `"pg"` → `"PG"` with no network |
| U-S8 | Rename candidates | `removed runtime:int` + `added duration_minutes:int` → candidate; incompatible types → none |
| L-S1 | Live, opt-in (`VOYAGE_API_KEY` set) | Real `sample_mflix` `rated` outliers get sensible top suggestions; recorded in ENGINE_NOTES, not asserted as exact scores |
