# Atlas mongoDiff interface

The UI owner maintains `frontend/` and this file, and integrates contributors' pushed branches. This is an independent feature prototype, not an installed or endorsed Atlas extension.

Public feature name: **mongoDiff**. Use that casing in the tab, workspace title, browser title, exports and documentation. Existing Python/CLI identifiers and database/session IDs use the starter names for compatibility.

## Visual source of truth

- Supplied Atlas screenshot: organization/project header, icon rail, database tree, open collection strip, breadcrumbs and collection tabs.
- [MongoDB design system](https://www.mongodb.design/) and [LeafyGreen React kit](https://github.com/mongodb/leafygreen-ui). Use published `@leafygreen-ui/*` components for buttons, logo, icons, badges, tabs, tables, typography, inputs and code.
- One implemented collection tab: mongoDiff. Surrounding Atlas tabs are disabled context; model/validator/history views open supporting dialogs.
- Typography: Euclid Circular A, matching LeafyGreen's tokens. Fonts use the CDN referenced in LeafyGreen's Storybook configuration; Helvetica/Arial fallback keeps the app usable offline. Code uses system monospace.
- Dense technical workspace: 64px header, 68px icon rail, responsive 284–432px explorer, 16px LeafyGreen base typography, 14px table body and 12px metadata, crisp 1px boundaries. No decorative gradients.

## Dark theme (optional)

Canvas `#001E2B`, panels `#0C2340`, inner boxes `#00141E`, borders `#21313C`, top navigation `#021621`, action green `#00ED64`, hover `#00C351`, primary text `#FFFFFF`, muted text `#889397`, alert red `#CF3B3B`, amber `#FFC010`. Use LeafyGreen's accessible badges and lighter red for small alert text. Avoid oversized error metrics.

## Light theme (default)

Follow the supplied Documents, Aggregations and Indexes screenshots. Canvas/header/panels `#FFFFFF`; explorer and inner surfaces `#F8FAF9`; crisp boundaries `#E7EDED`; navy text `#001E2B`; secondary text `#5C6C75`; action green `#00684A`, hover `#00553D`; selected collection `#E8EDEB`, selected rail `#E3FCF3`.

Use LeafyGreen's light provider for buttons, Select, TextInput, Tabs, Table, Banner, badges, icons and syntax-highlighted Code. Keep document tables flat, headings in sentence case, and a single collection-tab title. Match the screenshots' desktop button sizing, readable inactive tabs and footer spanning the explorer/workspace. Keep generated code in a bounded scrolling panel. Navigation and the footer stay in place while the collection workspace scrolls.

Light is the initial appearance, including browsers that saved the earlier dark default. `schema-guard-theme-v2` stores subsequent explicit choices. The document applies that preference before paint; the old preference key is no longer read.

## Content and interaction

- Preserve the approved Atlas shell, palette and typography. Main view: one scan subtitle and controls inside a LeafyGreen Card, a plain scan-result sentence, a separate LeafyGreen Card containing the Field / Issue / Documents / Details table, generated script and one Apply action. Do not reintroduce metric cards, uppercase status labels, model-rule columns or triage badges. No JSON forms, repeated disclaimers, asterisks or run IDs on the main page.
- Real report counts only; combine only mutually exclusive reasons within a field. Keep raw reasons/counts in exported reports and inspection. Identify fixtures with the Demo badge/data-source selector; omit unavailable Git/PR metadata. A validator update means a generated candidate is available, not that the installed validator was compared.
- Strict BSON failures do not necessarily crash coercive Pydantic reads. Preserve missing versus null in inspection. Use LeafyGreen Modal and Card for document inspection: one field title, one affected count, and flat Atlas-style key/value previews. No repeated example headings or nested count sections. Render the actual plan operations and actual database/collection; never substitute illustrative scripts or conversion success counts.
- Atlas scans stay read-only; fixture Apply requires review and confirmation. Backup/restore controls await the backend contract.
- AI uses an explicit **AI suggestions** action. Candidates retain their actual source and similarity score. **Use suggestion** changes only the reviewed repair preview. Keep the main screen concise; collapse document examples while candidates are visible. Label successful cached provider responses for recording retakes.
- Visible focus, accessible dialogs, bounded table/code scrolling, responsive explorer and reduced-motion support. Small fades only; no invented progress percentages.

See [docs/FRONTEND_PLAN.md](docs/FRONTEND_PLAN.md) and [TEAM_HANDOFF.md](TEAM_HANDOFF.md).
