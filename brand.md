# Atlas Schema Guard interface

The UI owner maintains `frontend/` and this file, and integrates contributors' pushed branches. This is an independent feature prototype, not an installed or endorsed Atlas extension.

## Visual source of truth

- Supplied Atlas screenshot: organization/project header, icon rail, database tree, open collection strip, breadcrumbs and collection tabs.
- [MongoDB design system](https://www.mongodb.design/) and [LeafyGreen React kit](https://github.com/mongodb/leafygreen-ui). Use published `@leafygreen-ui/*` components for buttons, logo, icons, badges, tabs, tables, typography, inputs and code.
- One implemented collection tab: Schema Guard. Surrounding Atlas tabs are disabled context; model/validator/history views open supporting dialogs.
- Typography: Euclid Circular A, matching LeafyGreen's tokens. Fonts use the CDN referenced in LeafyGreen's Storybook configuration; Helvetica/Arial fallback keeps the app usable offline. Code uses system monospace.
- Dense technical workspace: 64px header, 64px icon rail, 284px explorer, 14px body, 12px metadata, crisp 1px boundaries. No decorative gradients.

## Dark theme (default)

Canvas `#001E2B`, panels `#0C2340`, inner boxes `#00141E`, borders `#21313C`, top navigation `#021621`, action green `#00ED64`, hover `#00C351`, primary text `#FFFFFF`, muted text `#889397`, alert red `#CF3B3B`, amber `#FFC010`. Use LeafyGreen's accessible badges and lighter red for small alert text. Avoid oversized error metrics.

## Light theme

Match the screenshot: white workspace/header, pale gray explorer/rail, dark navy text, dark green actions/tabs and mint selected navigation. Preserve hierarchy; the theme switch persists locally.

## Content and interaction

- Preserve the approved Atlas shell, palette and typography. Main view: one scan subtitle, a plain scan-result sentence, a LeafyGreen table with Field / Issue / Documents / Details, generated script and one Apply action. Do not reintroduce metric cards, uppercase status labels, model-rule columns or triage badges. No JSON forms, repeated disclaimers, asterisks or run IDs on the main page.
- Real report counts only; combine only mutually exclusive reasons within a field. Keep raw reasons/counts in exported reports and inspection. Identify fixtures with the Demo badge/data-source selector; omit unavailable Git/PR metadata. A validator update means a generated candidate is available, not that the installed validator was compared.
- Strict BSON failures do not necessarily crash coercive Pydantic reads. Preserve missing versus null in inspection. Render the actual plan operations and actual database/collection; never substitute illustrative scripts or conversion success counts.
- Atlas scans stay read-only; fixture Apply requires review and confirmation. Backup/restore controls await the backend contract.
- Visible focus, accessible dialogs, bounded table/code scrolling, responsive explorer and reduced-motion support. Small fades only; no invented progress percentages.

See [docs/FRONTEND_PLAN.md](docs/FRONTEND_PLAN.md) and [TEAM_HANDOFF.md](TEAM_HANDOFF.md).
