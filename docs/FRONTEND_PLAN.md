# Atlas collection tab implementation plan

## Direction agreed before implementation

Recreate the supplied Atlas Data Explorer layout with a single implemented collection feature: **Schema Guard**. The familiar Documents, Aggregations, Schema, Indexes, Validation and Search Indexes tabs remain visible as disabled context. Model changes, validator preview and history become supporting dialogs inside Schema Guard.

Use the actual React components published from [mongodb/leafygreen-ui](https://github.com/mongodb/leafygreen-ui), inspected from a local clone, and [MongoDB's design system](https://www.mongodb.design/). Use its logo, icons, buttons, badges, tabs, typography and syntax-highlighted code. Use Euclid Circular A, the font specified by LeafyGreen's tokens, with a system fallback.

The screenshot supplies layout; the supplied dark tokens supply the initial theme. Provide a light theme switch for comparison with the screenshot. Keep styling centralized in `frontend/src/styles.css` and `brand.md`.

## Implementation sequence

1. Install individual published LeafyGreen packages; keep the existing React/Vite application.
2. Build an Atlas shell: organization/project header, global icon rail, searchable database tree, open collection strip, breadcrumb and collection tabs.
3. Build the Schema Guard surface: source/scan toolbar, compact scan result, a LeafyGreen issues table with document details, and an embedded reviewed repair workflow.
4. Preserve model diff, validator export, session history, report export, reset and fixture confirmation through supporting dialogs/actions.
5. Check the production build, the full fixture repair loop, light/dark appearance, keyboard/dialog behavior, accessibility and narrow layouts. Update the smoke script for the new navigation.

## Data and behavior boundaries

- Show actual unique failure counts. Keep newly failing/pre-existing drift in exported reports, and raw reasons in document details. Reason counts can overlap.
- Show demo results explicitly; never substitute the prompt's illustrative 403/21,349 counts.
- The API has no PR linkage or installed-validator comparison. Display configured model sources and the generated validator candidate without inventing installed-validator or PR metadata.
- Stored BSON validation is stricter than some coercive Pydantic reads. Do not claim every reported failure crashes a read.
- Wrong-type counts are not measured conversion success counts. Label conversions as proposed and requiring verification.
- Atlas analysis and exported plans stay read-only. Apply remains restricted to isolated fixtures. No backend endpoint or report shape changes are required.
- The tree represents the current configured collection. Context collections must not imply working navigation or discovery that the API does not support.

## Content simplification

The approved Atlas shell, colors and typography are preserved. The status cards are replaced with a plain scan-result sentence and **View validator**. The actual LeafyGreen Table shows only **Field / Issue / Documents / Details**, with three consolidated demo issue rows. Model rules and triage badges are removed from the main view. The script-only remediation panel retains **Apply Fix & Rescan**. JSON forms, repeated disclaimers, asterisks, raw run IDs and extra plan explanations are removed.

The rated row includes missing and invalid values (4 real demo documents). The runtime rows cover wrong types (2) and missing/null (2). Do not hardcode the illustrative row counts or hide enum failures. The displayed/downloaded script is formatted from the exact API plan operations, including the null default and explicit mappings needed for 7 → 0. The database remains the actual report target, not a hardcoded `sample_mflix`.

`frontend/src/presentation.ts` owns this presentation-only consolidation and demo presets. There are no backend or API-shape changes. CSS changes are limited to the compact scan summary, table and corresponding loading state. Custom decisions are API-only until an optional advanced dialog is needed.

## Delivered

All five implementation steps above are complete. The build and Chrome smoke check pass, including fixture repair 7 → 0, reset, both themes, supporting dialogs, collection filtering, grouped inspection, error recovery, Axe checks and 375/768/1280px layouts. See `docs/VALIDATION.md` for the exact coverage and limitations.

### Frontend file map

- `src/App.tsx`: scan/source/report state and supporting views.
- `src/components/AtlasShell.tsx`: navigation, database tree, breadcrumb and collection tabs.
- `src/components/GuardReport.tsx`: compact scan result, LeafyGreen issues table and document inspection.
- `src/components/FixesView.tsx`: reviewed preset pipeline and fixture confirmation.
- `src/presentation.ts`: accurate issue grouping, example decisions and exact-operation script formatting.
- `src/components/DetailDialog.tsx`: supporting dialog lifecycle.
- `src/components/CodeBlock.tsx`: LeafyGreen syntax highlighting, copy and download.
- `src/styles.css`: theme tokens, Atlas shell, component layouts and responsive behavior.
- `src/emotion-server-browser.ts` plus `vite.config.ts`: client-only compatibility for LeafyGreen's Emotion dependency. CSS remains handled by LeafyGreen; server rendering helpers are unavailable in this browser app.
- `scripts/smoke.mjs`: repeatable browser check. Paths above are relative to `frontend/`.

The frontend uses React 18 because the published LeafyGreen polymorphic component types do not compile with the previous React 19 types. API requests and report/plan shapes are unchanged.

## Team continuation

The UI owner maintains this shell and integrates the other contributors' pushed branches. The engine contributor delivers richer nested reasons/distinct bad values. The fixes/backend contributor delivers reviewed live execution, backup/restore, validator status and MongoDB history. See `TEAM_HANDOFF.md` for their completion criteria.
