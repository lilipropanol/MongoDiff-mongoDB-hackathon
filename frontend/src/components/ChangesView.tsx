import { ArrowRight } from 'lucide-react';
import type { Report, Rule } from '../types';
import { CodeBlock } from './CodeBlock';

function describe(rule?: Rule) {
  if (!rule) return '—';
  if (rule.enum) return rule.enum.map(value => JSON.stringify(value)).join(' | ');
  const types = rule.bsonType;
  return Array.isArray(types) ? types.join(' | ') : types || 'object';
}
const labels: Record<string, string> = { added: 'Field added', removed: 'Field removed', became_required: 'Now required', type_or_constraint_changed: 'Type or constraint changed' };
export function ChangesView({ report }: { report: Report }) {
  return <div className="view-enter"><div className="section-heading"><div><h2>Model changes</h2><p>Derived from the translated schemas using deterministic comparison.</p></div><span className="badge neutral">Pydantic v2</span></div>
    <div className="change-table"><div className="change-table-head"><span>Field</span><span>Change</span><span>Stored shape</span></div>
      {report.changes.map((change, i) => <div className="change-table-row" key={change.field + i}><code>{change.field}</code><span className="badge neutral">{labels[change.kind] || change.kind}{change.required ? ' · required' : ''}</span><div><code>{describe(change.old)}</code><ArrowRight size={14} /><code>{describe(change.new)}</code></div></div>)}
      {!report.changes.length && <p className="table-empty">No model changes found.</p>}
    </div>
    <div className="code-grid"><CodeBlock label="Current model" filename="model_old.py" code={report.model_sources?.old || JSON.stringify(report.old_schema, null, 2)} /><CodeBlock label="Proposed model" filename="model_new.py" code={report.model_sources?.new || JSON.stringify(report.new_schema, null, 2)} /></div>
    <div className="info-note"><p>Extra stored fields are allowed. Removing a field from the model does not automatically delete it from the collection.</p></div>
  </div>;
}
