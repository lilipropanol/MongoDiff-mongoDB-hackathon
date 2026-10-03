import Icon from "@leafygreen-ui/icon";
import type { Report, Rule } from "../types";
import { CodeBlock } from "./CodeBlock";

function describe(rule?: Rule) {
  if (!rule) return "—";
  if (rule.enum)
    return rule.enum.map((value) => JSON.stringify(value)).join(" | ");
  const types = rule.bsonType;
  return Array.isArray(types) ? types.join(" | ") : types || "object";
}
const labels: Record<string, string> = {
  added: "Field added",
  removed: "Field removed",
  became_required: "Now required",
  became_optional: "No longer required",
  type_or_constraint_changed: "Type or constraint changed",
};
export function ChangesView({ report }: { report: Report }) {
  return (
    <div className="view-enter">
      <div className="section-heading">
        <div>
          <h2>Model changes</h2>
          <p>
            Derived from the translated schemas using deterministic comparison.
          </p>
        </div>
        <span className="badge neutral">JSON Schema comparison</span>
      </div>
      <div
        className="change-table"
        tabIndex={0}
        aria-label="Model change comparison"
      >
        <div className="change-table-head">
          <span>Field</span>
          <span>Change</span>
          <span>Compatibility</span>
          <span>Stored shape</span>
        </div>
        {report.changes.map((change, i) => (
          <div className="change-table-row" key={change.field + i}>
            <code>{change.field}</code>
            <span className="badge neutral">
              {labels[change.kind] || change.kind}
              {change.required ? " · required" : ""}
            </span>
            {change.compatibility && (
              <span className={`badge ${change.compatibility === "breaking" ? "warning" : "success"}`}>
                <span title={change.compatibility_reason}>{change.compatibility}</span>
              </span>
            )}
            <div>
              <code>{describe(change.old)}</code>
              <Icon aria-hidden glyph="ArrowRight" size={14} />
              <code>{describe(change.new)}</code>
            </div>
            {change.rename_candidates?.length ? (
              <div className="rename-suggestions">
                Possible rename: {change.rename_candidates.map((candidate) => (
                  <span key={candidate.to}><code>{candidate.to}</code> · {Math.round(candidate.score * 100)}% suggestion</span>
                ))}
              </div>
            ) : null}
          </div>
        ))}
        {!report.changes.length && (
          <p className="table-empty">No model changes found.</p>
        )}
      </div>
      <div className="code-grid">
        <CodeBlock
          label="Current model"
          filename={report.model_sources?.old.trimStart().startsWith("{") ? "model_old.schema.json" : "model_old.py"}
          code={
            report.model_sources?.old ||
            JSON.stringify(report.old_schema, null, 2)
          }
        />
        <CodeBlock
          label="Proposed model"
          filename={report.model_sources?.new.trimStart().startsWith("{") ? "model_new.schema.json" : "model_new.py"}
          code={
            report.model_sources?.new ||
            JSON.stringify(report.new_schema, null, 2)
          }
        />
      </div>
      <div className="info-note">
        <p>
          Extra stored fields are allowed. Removing a field from the model does
          not automatically delete it from the collection.
        </p>
      </div>
    </div>
  );
}
