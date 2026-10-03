# Brief: Voyage AI suggestions (for Person 3)

From Person 2 (schema & impact). Code: branch `engine/atlas-analysis`, file `schema_guard/engine/suggest.py`.

## What exists already

The engine can suggest fixes for bad values and renamed fields:

- `"PG13"` → `"PG-13"` for the `rated` field
- `runtime` → `duration_minutes` as a possible rename

There are three Voyage AI modes, including MongoDB Atlas Vector Search, plus offline text matching as a fallback. **They only suggest.** Suggestions never become plan decisions and never change counts; tests prove both.

| Mode (`GUARD_SUGGESTIONS=`) | How it works | Requests |
| --- | --- | --- |
| *(unset)* | Off (default) | none |
| `lexical` | Offline text similarity | none |
| `voyage` | Embeddings (`voyage-4-lite`), cosine similarity | **1 per scan** (batched) |
| `voyage-rerank` | Reranker (`rerank-2.5`); usually more accurate for "which allowed value did they mean?" | 1 per bad value, capped at 20 per scan |
| `atlas-vector` | **MongoDB Atlas Vector Search.** Voyage embeddings stored in a vocabulary collection, matched with `$vectorSearch` | 1 Voyage call per scan, plus one `$vectorSearch` per bad value |

## Setup (`.env`, which is git-ignored, so never commit keys)

```dotenv
GUARD_SUGGESTIONS=atlas-vector      # or voyage / voyage-rerank / lexical
VOYAGE_API_KEY=...
# Optional tuning, no code changes needed:
VOYAGE_MIN_SCORE=0.6                # threshold for the active Voyage mode (defaults: embed 0.6, rerank 0.5)
VOYAGE_EMBED_MODEL=voyage-4-lite
GUARD_VECTOR_COLLECTION=schema_guard.suggestion_vectors   # atlas-vector only: where vectors may be written (never the scanned collection)
GUARD_VECTOR_INDEX_WAIT=60          # seconds to wait for the vector index to become queryable
VOYAGE_RERANK_MODEL=rerank-2.5
VOYAGE_API_URL=https://ai.mongodb.com/v1     # default (Atlas-issued keys, verified by Person 3); use https://api.voyageai.com/v1 for voyageai.com keys
```

## Where the output appears

- `reasons[].distinct_values[].suggestions`: `[{target, score, source}]`, up to 3 per bad value
- `changes[].rename_candidates`: `[{to, score, source}]`
- `scan.suggestions`: `{provider, model, method, status, fallback_reason, semantic_jobs?}`. It's saved in reports on `ui/integration`, where `report.py` copies `scan`.

## Your tasks

1. **Get a Voyage key** (Atlas console or voyageai.com) and run the live check:

   ```bash
   VOYAGE_API_KEY=... SCHEMA_GUARD_LIVE_VOYAGE=1 .venv/bin/python -m pytest -q tests/engine/test_engine_suggest.py
   ```

   If it fails with an Atlas-issued key, set `VOYAGE_API_URL` to the endpoint MongoDB's docs give for those keys.
2. **`report.py`:** ✅ `warnings` and `scan` are already done on `ui/integration`. Add one more line for schema versioning:

   ```python
   "versioning": impact.get("versioning"),
   ```

3. **Tune on real data.**
   - Run an Atlas analysis of `sample_mflix.movies` with each Voyage mode.
   - Compare the suggestions for real `rated` outliers (e.g. `"NOT RATED"`, `"TV-14"`, `"PASSED"`).
   - Adjust `VOYAGE_MIN_SCORE` until the suggestions are sensible.
   - Record the chosen mode, threshold and a few examples in `docs/engine/PROGRESS.md`.
4. **Verify Atlas Vector Search on a disposable Atlas cluster** (the headline MongoDB feature):

   ```bash
   SCHEMA_GUARD_ATLAS_VECTOR_URI='mongodb+srv://<disposable-cluster>' VOYAGE_API_KEY=... \
     .venv/bin/python -m pytest -q tests/engine/integration/test_engine_vector_real.py -k live
   ```

   - It creates a throwaway database, a vocabulary collection and a `vectorSearch` index. It runs `$vectorSearch`, then drops the database.
   - For the demo, set `GUARD_SUGGESTIONS=atlas-vector` and `GUARD_VECTOR_COLLECTION=schema_guard.suggestion_vectors`, and use a database user that can write to that one namespace (the scan itself stays read-only).
   - The status should show `method: "atlas-vector-search"`.
5. **`fixes.py` (optional):** only offer mappings for values with `mappable: true`. Suggestions stay advisory: the human still picks or types the mapping.

## Rules (please keep)

- **Off by default.** It must stay opt-in, because it sends data values to an outside service.
- **Only these are sent:** bad values (cut to 80 characters), allowed enum values and field names. Never document ids, documents, examples or the database URI. There are tests for this; keep them passing.
- **Rate limits:** the free tier can be about 3 requests a minute. Prefer `voyage` (one batched call). `voyage-rerank` is capped at 20 calls per scan; values beyond the cap still get offline suggestions.
- **Failures:** if Voyage fails or times out (10 s), the scan still succeeds, with offline suggestions and `status: "fallback"`.
- **Atlas Vector Search writes only to `GUARD_VECTOR_COLLECTION`.** That's the vocabulary of allowed values and its index. It refuses the scanned collection, and the scan itself stays read-only.

## Done when

- The live test passes with a real key.
- `scan.suggestions.status` is `"ok"` in a saved Atlas report.
- The chosen mode, threshold and example suggestions are recorded in `docs/engine/PROGRESS.md`.
- `pytest -q` is still green.
