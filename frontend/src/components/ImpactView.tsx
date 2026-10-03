import { useState } from 'react';
import { ArrowRight, CircleCheck, FileSearch, TriangleAlert } from 'lucide-react';
import type { Reason, Report } from '../types';
import { number, percent } from '../api';

export const reasonLabel: Record<string, string> = {
  missing: 'Missing required field', null_not_allowed: 'Null is no longer allowed',
  wrong_type: 'Unexpected BSON type', value_not_allowed: 'Value outside allowed options',
  nested_or_array_constraint: 'Nested field or array item is invalid',
};

function needs(reason: Reason) {
  if (reason.reason === 'wrong_type') return 'Conversion candidate';
  if (reason.reason === 'value_not_allowed') return 'Needs review';
  return 'Needs a default';
}

export function ImpactView({ report, openFixes }: { report: Report; openFixes: () => void }) {
  const [selectedKey, setSelectedKey] = useState('');
  const keyFor = (r: Reason) => `${r.field}:${r.reason}`;
  const selected = report.reasons.find(r => keyFor(r) === selectedKey) || report.reasons[0];
  const safe = report.total_docs - report.failing;
  return <div className="view-enter">
    <div className={`impact-summary ${report.failing === 0 ? 'success' : ''}`}>
      <div className="summary-heading">{report.failing ? <TriangleAlert size={20} /> : <CircleCheck size={20} />}<span>{report.failing ? 'Schema change needs attention' : 'The collection matches the proposed schema'}</span><span className="badge neutral">Full scan</span></div>
      <div className="summary-number"><strong>{number(report.failing)}</strong><span>of <b>{number(report.total_docs)}</b> documents fail</span></div>
      <p>{report.failing ? 'Review affected fields before deploying the new model.' : 'No failing documents remain. Review the validator before enabling enforcement.'}</p>
      <div className="impact-meter" role="img" aria-label={`${percent(report.failing, report.total_docs)} of documents fail`}><span style={{ width: `${report.total_docs ? report.failing / report.total_docs * 100 : 0}%` }} /></div>
      <div className="meter-legend"><span><i className="dot danger" />{percent(report.failing, report.total_docs)} fail the new schema</span><span><i className="dot healthy" />{number(safe)} match</span></div>
    </div>
    <div className="metric-strip">
      <div><span>Newly affected by this change</span><strong>{number(report.newly_failing)}</strong></div>
      <div><span>Already fail the old schema</span><strong>{number(report.preexisting)}</strong></div>
      <div><span>Unclassified failures</span><strong>{number(report.unclassified)}</strong></div>
    </div>
    <div className="section-heading"><div><h2>What breaks, and why</h2><p>Counts are issues per field. A document can appear in more than one row.</p></div><button className="text-button" onClick={openFixes}>Review fixes <ArrowRight size={16} /></button></div>
    {report.reasons.length === 0 ? <div className="empty-state"><CircleCheck size={32} /><h3>No schema violations</h3><p>Open model changes or export the proposed validator.</p></div> : <div className="issue-layout">
      <div className="issue-list" aria-label="Schema issues">
        {report.reasons.map(reason => <button key={keyFor(reason)} className={`issue-row ${selected === reason ? 'selected' : ''}`} onClick={() => setSelectedKey(keyFor(reason))} aria-pressed={selected === reason}>
          <span className="issue-icon"><FileSearch size={18} /></span><span className="issue-content"><code>{reason.field}</code><span>{reasonLabel[reason.reason] || reason.reason}</span><small>{needs(reason)}</small></span><strong>{number(reason.count)}</strong><ArrowRight size={16} />
        </button>)}
      </div>
      {selected && <section className="document-panel"><div className="panel-heading"><h3>Example documents</h3><span className="badge neutral">{selected.examples.length} samples</span></div><p>Only the identifier and affected field are shown.</p>
        {selected.examples.map((doc, i) => <div className="document" key={String(doc._id) + i}><div className="document-id">_id: <code>{String(doc._id)}</code></div><div className="document-value"><code>{selected.field}</code><code>{selected.field in doc ? JSON.stringify(doc[selected.field]) : '<missing>'}</code></div></div>)}
        {!selected.examples.length && <p>No examples were retained for this run.</p>}
      </section>}
    </div>}
    <div className="info-note"><FileSearch size={17} /><p>Stored BSON types are checked strictly. Pydantic may coerce some values when reading, so a schema violation does not always mean the application would crash.</p></div>
  </div>;
}
