# Recording MongoDiff (about 2 minutes)

Open **http://127.0.0.1:8002**. Use light mode, a desktop window around 1440px wide and browser zoom at 100%. Record the application window. The API key is in the ignored local `.env`; keep terminals, settings files and developer tools out of the recording.

This recording uses **12 synthetic movies and real Voyage AI embeddings** from MongoDB's `ai.mongodb.com` endpoint. The fixture repair is real within your isolated session. This setup does not use an Atlas connection or run `$vectorSearch`, so describe the AI as “Voyage embeddings,” not a live Atlas Vector Search demonstration.

## Clicks and narration

| Time | Click / record | What to say |
| --- | --- | --- |
| 0–15s | Select **Demo fixtures** if needed. Click the circular **Reset demo data** icon beside the action buttons. Hold on **7 of 12** and the issue table. | “MongoDiff previews what a model change would break in existing MongoDB documents. This is our repeatable synthetic movie demo.” |
| 15–35s | Click **Run history**, then **Model changes**. Show the new required fields and breaking/compatible labels. Close the modal. | “The comparison is deterministic. Runtime becomes required and the model adds a constrained rating.” |
| 35–50s | Click **Details** on runtime **Stored as text**. Show the actual values and explanation. Close. | “It identifies the stored value and explains why it fails. Counts distinguish new problems from existing drift, and each document counts once in the headline.” |
| 50–75s | Click **Voyage AI suggestions**. Wait for the **Voyage AI suggestions** status. In the `rated` row click **Review suggestions**. | “AI is optional. MongoDB's Voyage embeddings suggest possible mappings from bounded bad values. We show the actual source and score for each candidate.” |
| 75–90s | Scroll to the `"PG13" → "PG-13"` candidate and click its **Use suggestion** button. | “An exact spelling match is labelled as text matching. Ambiguous values also have Voyage candidates. A person chooses the mapping; selecting one changes only the repair preview.” |
| 90–110s | Scroll the workspace to **Repair plan**. Pause on the operations. Click **Apply Fix & Rescan**, then **Apply & Rescan**. | “I review the defaults, conversions and mappings, then explicitly confirm the repair in this isolated demo.” |
| 110–125s | Show **7 → 0** and **0 of 12**. Click **View validator**, show the preview, then close it. | “A fresh scan verifies the result. The generated validator protects future writes; it is available for review.” |

## Before a retake

Click **Reset demo data** to return to 7 failures. Repeat **Voyage AI suggestions** to restore the candidates. Successful provider responses are cached in server memory and labelled **Saved provider response**, so retakes can reuse the real result. Cache is cleared by restarting the server; failed provider requests are not cached and can be retried.

`NR` is ambiguous. Do not interpret its similarity score as a probability or assume the first candidate is correct. The demo repair explicitly uses `PG` as its synthetic fixture default; a real application needs a reviewed business rule for unrated movies. Every candidate retains its true source: **Text matching**, **Voyage embeddings**, or **Atlas Vector Search**.

## Start it again

From the repository root, after dependencies are installed:

```bash
npm --prefix frontend run build
.venv/bin/schema-guard-server --port 8002
```

The local `.env` configures `GUARD_SUGGESTIONS=voyage`, `VOYAGE_API_URL=https://ai.mongodb.com/v1` and `VOYAGE_EMBED_MODEL=voyage-4-lite`. Credentials stay local. API documentation is at http://127.0.0.1:8002/docs.

Optional end-to-end recording check, with that server running:

```bash
GUARD_SMOKE_AI=1 node frontend/scripts/smoke.mjs http://127.0.0.1:8002
```

This check requires successful Voyage results (or their in-memory cached response). It verifies explicit selection updates the plan without modifying counts, then confirms the fixture repair and reset.
