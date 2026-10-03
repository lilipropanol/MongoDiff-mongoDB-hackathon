# Schema Guard interface direction

An Atlas-inspired feature prototype for inspecting collection schema changes.
This is an independent prototype, not an official MongoDB product or Atlas plugin.

The UI owner maintains this file and `frontend/`, then handles final app integration after contributors push. Feature status is tracked in [README.md](README.md); remaining UI tasks are in [TEAM_HANDOFF.md](TEAM_HANDOFF.md).

- Direction: a light technical workspace, fixed project navigation, a collection header,
  and tabs for impact, model changes, fix preview, validator, and run history.
- Density: comfortable, with compact tables and document/code panels.
- Primary palette: dark forest navigation (#001e2b), green actions (#00684a),
  pale green selected surfaces (#e8f5ee), neutral canvas (#f6f8f9), white panels.
- Text: #1c2d38, secondary text #526570. Error: #b42318; warning: #855600.
- Typography: local system sans fonts; local monospace for code and tabular numbers.
  No external font requests are needed for the demo.
- Motion: a short content fade and button transitions, disabled for reduced motion.
- Voice: practical and specific. Distinguish demo fixtures from MongoDB scan results;
  show counts, affected fields, exact operations, and work that needs a human decision.
- Keep colors in CSS variables. UI ownership can refine these tokens independently.
- Show live repair controls only after the backend delivers its reviewed execution contract.
  A temporary demo copy must not be presented as durable MongoDB backup/restore.
