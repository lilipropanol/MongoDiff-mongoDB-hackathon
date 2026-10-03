# Shared API contract

## Current behavior

This file describes endpoints that exist in the starter. Atlas scans and plan generation are read-only. **The only apply endpoint is `/api/demo/apply`, which changes in-memory fixtures.** There are no live apply, backup/restore, or validator execution endpoints yet.

The API chooses the collection and trusted model files from server configuration. HTTP requests cannot supply a MongoDB URI, arbitrary model path, or executable Python model. The CLI is a separate entry point and its report does not automatically appear in a browser session's history.

Local development: Python on `127.0.0.1:8000`, Vite on `127.0.0.1:5173` with `/api` proxy. Built UI and API use the same origin at port 8000. No CORS configuration is needed for this setup.

`schema-guard-server --port 8001` serves the built app at port 8001. The Vite development proxy remains configured for 8000 until you edit `frontend/vite.config.ts`.

Session IDs are UUIDs stored in browser sessionStorage. They isolate fixtures and report lists; they are not access control. This prototype is local only.

| Method/path | Request | Response |
| --- | --- | --- |
| `GET /api/health` | — | `{status:"ok"}` |
| `GET /api/config` | — | Atlas configured boolean, database, collection, live apply available boolean |
| `POST /api/analyze` | `{session_id, source:"demo"\|"atlas"}` | Report |
| `GET /api/runs?session_id=UUID` | — | Up to 30 saved session Reports |
| `POST /api/runs/{id}/plan` | `{session_id, defaults:{field:value}, mappings:{field:{oldString:newValue}}}` | Plan |
| `POST /api/demo/apply` | `{session_id, plan_id}` | Fresh Report after applying to isolated fixtures |
| `POST /api/demo/reset` | `{session_id}` | Fresh Report on restored fixture seed |

`session_id` and path IDs must be UUIDs. `source` defaults to `demo`. Defaults and mappings default to empty objects. `/api/config` returns `atlas_configured: true` when a URI is set; it does not test connectivity or permissions. Its `live_apply_available` is currently always `false`.

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
  changes: {field:string; kind:string; old?:Schema; new?:Schema; required?:boolean}[];
  reasons: {field:string; reason:string; count:number; example_ids:string[]; examples:Record<string,unknown>[]}[];
  old_schema: Schema; new_schema: Schema; new_validator: {$jsonSchema: Schema};
  model_sources?: {old:string; new:string}; notes: string[];
  demo_backup_available?: boolean;
};
```

`failing` is the unique documents failing the new stored schema. `preexisting` is all documents failing the old schema; those documents may be fixed by a relaxed new schema. `newly_failing` matches old schema AND fails new schema. These values must not be blindly added. Reason counts may overlap. `unclassified` is failing documents unmatched by any reason check.

The fixture seed has `total_docs: 12`, `failing: 7`, `preexisting: 2`, and `newly_failing: 5`. Those are fixture results, not predicted Atlas counts. Strict stored BSON validation can differ from coercive Pydantic reads.

Reasons: `missing`, `null_not_allowed`, `wrong_type`, `value_not_allowed`, `nested_or_array_constraint`. Examples project only `_id` and the root affected field; nested object examples may therefore contain that object's contents. BSON-specific values are serialized to strings in local reports.

Diff kinds: `added`, `removed`, `became_required`, `type_or_constraint_changed`. A nested change is currently grouped under the root field. Removal alone does not imply a stored-data violation.

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

Demo apply keeps one pre-apply copy in memory and returns a fresh scan. `demo_backup_available` means that temporary copy exists; there is no restore endpoint for it. Demo reset loads the original fixture seed. Neither is durable MongoDB backup/restore.

## Errors

Responses use `{detail:string}` for application errors. Request schema validation may return FastAPI's structured 422 list; the UI displays a generic actionable error for that case. Missing Atlas configuration returns 409; bad decisions/models return 422; stale demo plans return 409; a MongoDB scan failure returns a sanitized 502 without echoing the URI.

## Contract extension process

The UI owner coordinates the shared contract. Engine and fixes/backend contributors propose fields/endpoints and agree on them with the UI owner before implementing their own side on their branches. Update this file and `frontend/src/types.ts` to reflect the agreed shape. After contributors push, the UI owner merges their branches, connects both sides, and verifies the combined app. Prefer additive report changes; keep existing keys stable. A live execution contract must define backup/rollback states, partial operation results, and explicit confirmation before the UI offers live apply.
