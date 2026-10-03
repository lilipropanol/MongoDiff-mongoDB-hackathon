# Shared API contract

## Current behavior

Atlas scans and plan generation are read-only. **The only apply endpoint is `/api/demo/apply`, which changes in-memory fixtures.** `/api/demo/restore` restores that temporary fixture backup; it does not write to MongoDB. `/api/validator` returns a validator command preview only.

The API chooses the collection and trusted model files from server configuration. HTTP requests cannot supply a MongoDB URI, arbitrary model path, or executable Python model. The CLI is a separate entry point and its report does not automatically appear in a browser session's history.

Local development: Python on `127.0.0.1:8000`, Vite on `127.0.0.1:5173` with `/api` proxy. Built UI and API use the same origin at port 8000. No CORS configuration is needed for this setup.

`schema-guard-server --port 8001` serves the built app at port 8001. The Vite development proxy remains configured for 8000 until you edit `frontend/vite.config.ts`.

Session IDs are UUIDs stored in browser sessionStorage. They isolate fixtures and report lists; they are not access control. This prototype is local only.

| Method/path | Request | Response |
| --- | --- | --- |
| `GET /api/health` | — | `{status:"ok"}` |
| `GET /api/config` | — | Atlas configured boolean, database, collection, live apply available boolean, sanitized suggestion provider configuration |
| `POST /api/analyze` | `{session_id, source:"demo"\|"atlas", suggestions?:boolean}` | Report |
| `GET /api/runs?session_id=UUID` | — | Up to 30 saved session Reports |
| `POST /api/runs/{id}/plan` | `{session_id, defaults:{field:value}, mappings:{field:{oldString:newValue}}}` | Plan |
| `POST /api/demo/apply` | `{session_id, plan_id}` | Fresh Report after applying to isolated fixtures |
| `POST /api/demo/restore` | `{session_id}` | Fresh Report after restoring the in-memory fixture backup |
| `POST /api/demo/reset` | `{session_id}` | Fresh Report on restored fixture seed |
| `GET /api/validator?session_id=UUID&run_id=UUID` | — | `collMod` preview with `validationAction:"warn"`; does not execute it |

`session_id` and path IDs must be UUIDs. `source` defaults to `demo`; `suggestions` defaults to `false`. Suggestions work for both demo fixtures and Atlas analyses when a supported provider is configured. `/api/config` returns the provider mode, `demo_suggestion_mode`, and whether a Voyage key is configured, never the key itself. It does not test connectivity or permissions. `atlas_configured` only means a URI is set; `live_apply_available` is always `false`.

History reads local JSON files, considers the latest 200 report files across sessions, then returns up to 30 belonging to the requested session. It is not an unlimited MongoDB-backed audit log.

## Report

```typescript
type Schema = {
  bsonType?: string | string[];
  enum?: unknown[];
  required?: string[];
  properties?: Record<string, Schema>;
  items?: Schema;
};

type Report = {
  id: string; session_id: string; run_at: string;
  source: "demo" | "atlas"; database: string; collection: string;
  total_docs: number; failing: number; preexisting: number;
  newly_failing: number; unclassified: number;
  changes: {field:string; parent?:string|null; kind:string; old?:Schema; new?:Schema; required?:boolean;
            compatibility?:"breaking"|"compatible"; compatibility_reason?:string;
            rename_candidates?:{to:string; score:number; source:string}[]}[];
  reasons: {field:string; path?:string; location?:"field"|"nested"|"array_element"; reason:string; count:number;
            count_newly?:number; count_preexisting?:number; explanation?:string;
            distinct_values?:{value:unknown; bson_type:string; count:number; mappable?:boolean;
                               suggestions?:{target:string; score:number; source:string}[]}[];
            distinct_value_count?:number; distinct_values_limited?:boolean;
            example_ids:string[]; examples:Record<string,unknown>[]}[];
  warnings?: {field:string; path:string; kind:string; count:number; message:string}[];
  scan?: {duration_ms:number; max_time_ms:number; examples:number; distinct_limit:number; two_pass:boolean;
          collection_exists:boolean|null; snapshot:boolean; suggestions?:object};
  versioning?: {field:string; versioned:boolean; versions:{version:unknown; total:number; failing:number; newly_failing:number}[];
                bump_recommended:boolean; breaking_changes:string[]; message:string};
  old_schema: Schema; new_schema: Schema; new_validator: {$jsonSchema: Schema};
  model_sources?: {old:string; new:string}; notes: string[];
  demo_backup_available?: boolean;
};
```

`failing` is the unique documents failing the new stored schema. `preexisting` is all documents failing the old schema; those documents may be fixed by a relaxed new schema. `newly_failing` matches the old schema AND fails the new schema. These values must not be blindly added. Reason counts may overlap, and each reason carries its newly affected and pre-existing counts when an old schema is available. `unclassified` is failing documents unmatched by any reason check.

The fixture seed has `total_docs: 12`, `failing: 7`, `preexisting: 2`, and `newly_failing: 5`. Those are fixture results, not predicted Atlas counts. Strict stored BSON validation can differ from coercive Pydantic reads.

Reasons include `missing`, `null_not_allowed`, `wrong_type`, `value_not_allowed`, and nested rule mismatches. `field` identifies the root field; `path` pinpoints nested/list locations (for example `imdb.rating` or `cast[].name`). Bad-value summaries are bounded, omit document IDs, and count documents per value. Example documents are separately bounded and project only `_id` and the root affected field. BSON-specific values are serialized safely in local reports. Optional/defaulted missing fields are reported under `warnings` and do not count as failures. `scan` describes query limits and whether the scan used two passes; it is not a snapshot transaction.

Diff kinds include `added`, `removed`, `became_required`, `became_optional`, and `type_or_constraint_changed`; nested changes include their path and parent. Each change may be labelled breaking or compatible, with a reason. Rename candidates remain advisory. Versioning analysis groups counts by the configured `GUARD_VERSION_FIELD` (default `schemaVersion`) and may recommend a version bump; it never edits stored versions.

### Optional suggestions

Suggestions are off for each scan unless `suggestions:true` is sent from the UI. The server must also have `GUARD_SUGGESTIONS` set to `lexical`, `voyage`, `voyage-rerank`, or `atlas-vector`. Lexical matching is offline. Voyage modes send only bounded distinct bad values, allowed values, and field names; they never send examples, IDs, whole documents, credentials, or the MongoDB URI. Atlas Vector Search stores allowed-value vectors only in the explicitly configured `GUARD_VECTOR_COLLECTION`, and refuses the scanned namespace. Suggestions and provider/fallback status are recorded under `scan.suggestions`; they never alter counts or repair plans automatically. The UI labels candidates as suggestions for human review.

The **AI suggestions** button is explicit opt-in for a scan. Demo analysis uses the same real suggestion provider on bounded synthetic values, without constructing a MongoDB client. Demo `atlas-vector` configuration uses Voyage embeddings instead and reports that actual method. Successful demo responses are cached in memory (up to eight signatures); `scan.suggestions.cache_hit` labels reuse. Failure/fallback results are not cached, so retry can contact the provider again. Fixture reasons include real per-reason old/new attribution, explanations and distinct-value summaries.

**Use suggestion** adds a chosen root-field string mapping to the explicit plan request, followed by a regenerated preview. It does not write documents. Truncated or nested/non-mappable values cannot be selected. The backend validates the selected target against the new schema; application still requires review and confirmation. Similarity scores are not probabilities.

## Plan

```typescript
type Plan = {
  id: string; session_id: string; run_id: string;
  operations: {field:string; kind:"default"|"convert"|"mapping"; description:string;
               filter:unknown; update:unknown; count:number|null}[];
  unresolved: {field:string; reason:string; count:number; message:string}[];
  script: string; live_execution_available: false; notes: string[];
};
```

Defaults and mapping targets are validated against the supported stored schema. Conversion counts are deliberately `null` until conversion feasibility is measured on actual MongoDB data. A proposed operation is not a claim that every wrong-typed value is repairable. Mapping keys are strings in this version; mappings are explicitly reviewed and may also change currently valid values matching the exact source value.

`unresolved` contains advisory review items with counts from the source report. It is not an exact prediction of documents remaining after repair. Use the fresh report's `failing` count after applying to determine leftovers.

Plans are retained in server memory. Apply accepts only a plan from the same session and the latest analyzed demo revision. After a restart, generate a new plan. Plan generation does not write to MongoDB. Live execution does not exist yet.

Demo apply keeps one pre-apply copy in memory and returns a fresh scan. `demo_backup_available` means that temporary copy exists. Demo restore returns to that copy; demo reset loads the original fixture seed. Neither is durable MongoDB backup/restore.

## Errors

Responses use `{detail:string}` for application errors. Request schema validation may return FastAPI's structured 422 list; the UI displays a generic actionable error for that case. Missing Atlas configuration returns 409; bad decisions/models return 422; stale demo plans return 409; a MongoDB scan failure returns a sanitized 502 without echoing the URI.

## Contract extension process

The UI owner coordinates the shared contract. Engine and fixes/backend contributors propose fields/endpoints and agree on them with the UI owner before implementing their own side on their branches. Update this file and `frontend/src/types.ts` to reflect the agreed shape. After contributors push, the UI owner merges their branches, connects both sides, and verifies the combined app. Prefer additive report changes; keep existing keys stable. A live execution contract must define backup/rollback states, partial operation results, and explicit confirmation before the UI offers live apply.
