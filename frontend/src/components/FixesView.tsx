import { useRef, useState } from 'react';
import { ArrowRight, Check, Play, ShieldCheck, X } from 'lucide-react';
import { api, number } from '../api';
import type { Plan, Report } from '../types';
import { CodeBlock } from './CodeBlock';

export function FixesView({ report, onApplied }: { report: Report; onApplied: (report: Report) => void }) {
  const [defaults, setDefaults] = useState('{}');
  const [mappings, setMappings] = useState('{}');
  const [plan, setPlan] = useState<Plan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const dialog = useRef<HTMLDialogElement>(null);
  function edit(kind: 'defaults' | 'mappings', value: string) {
    (kind === 'defaults' ? setDefaults : setMappings)(value); setPlan(null); setError('');
  }
  async function preview() {
    setBusy(true); setError('');
    try {
      const d = JSON.parse(defaults), m = JSON.parse(mappings);
      if (!d || !m || Array.isArray(d) || Array.isArray(m) || typeof d !== 'object' || typeof m !== 'object') throw new Error('Defaults and mappings must be JSON objects.');
      setPlan(await api.plan(report.id, d, m));
    } catch (err) { setError(err instanceof SyntaxError ? 'Check the JSON syntax. Use double quotes for field names and strings.' : err instanceof Error ? err.message : 'Could not generate a plan.'); }
    finally { setBusy(false); }
  }
  async function apply() {
    if (!plan) return;
    setBusy(true); setError(''); dialog.current?.close();
    try { onApplied(await api.applyDemo(plan.id)); }
    catch (err) { setError(err instanceof Error ? err.message : 'Could not apply the demo plan.'); }
    finally { setBusy(false); }
  }
  function demoInputs() {
    setDefaults(JSON.stringify({ rated: 'PG', runtime: 90 }, null, 2));
    setMappings(JSON.stringify({ rated: { PG13: 'PG-13', NR: 'PG' }, runtime: { 'N/A': 90 } }, null, 2));
    setPlan(null); setError('');
  }
  return <div className="view-enter">
    <div className="section-heading"><div><h2>Review a repair plan</h2><p>You choose the defaults and mappings. The tool generates deterministic operations.</p></div>{report.source === 'demo' && <button className="button secondary" onClick={demoInputs} disabled={busy}>Use demo decisions</button>}</div>
    <div className="decision-grid">
      <div className="editor-field"><label htmlFor="defaults">Defaults for missing or null fields</label><p>Example: <code>{'{"rated": "PG", "runtime": 90}'}</code></p><textarea id="defaults" spellCheck={false} value={defaults} onChange={e => edit('defaults', e.target.value)} disabled={busy} /></div>
      <div className="editor-field"><label htmlFor="mappings">Explicit value mappings</label><p>Example: <code>{'{"rated": {"PG13": "PG-13"}}'}</code></p><textarea id="mappings" spellCheck={false} value={mappings} onChange={e => edit('mappings', e.target.value)} disabled={busy} /></div>
    </div>
    <div className="plan-actions"><button className="button primary" onClick={preview} disabled={busy}>{busy ? 'Working…' : 'Preview fix plan'}<ArrowRight size={16} /></button><span><ShieldCheck size={16} />Preview does not change data</span></div>
    {error && <div className="error-banner" role="alert"><p>{error}</p><button className="text-button" onClick={preview} disabled={busy}>Try again</button></div>}
    {plan && <section className="plan-result">
      <div className="section-heading"><div><h2>{number(plan.operations.length)} proposed operations</h2><p>Review the exact filters and updates before applying anything.</p></div>{report.source === 'demo' && <button className="button primary" disabled={busy || !plan.operations.length} onClick={() => dialog.current?.showModal()}><Play size={16} />Apply to demo data</button>}</div>
      <div className="operation-list">{plan.operations.map((op, i) => <div key={i}><span className="operation-index">{i + 1}</span><span>{op.description}</span><span className="badge neutral">{op.kind}</span></div>)}{!plan.operations.length && <p>No operations yet. Provide decisions for the listed issues.</p>}</div>
      <CodeBlock label="Generated MongoDB operations · review only" filename="schema_guard_fix.js" code={plan.script} />
      {plan.unresolved.length > 0 && <div className="review-note"><h3>Verify the result after applying</h3>{plan.unresolved.map((r, i) => <p key={i}><code>{r.field}</code> — {r.message}</p>)}</div>}
      {report.source === 'atlas' && <div className="info-note"><ShieldCheck size={18} /><p>Live execution is not available in this starter. Export the plan for review. Backup, rollback, and validator rollout are assigned in the team handoff.</p></div>}
    </section>}
    <dialog ref={dialog} className="confirm-dialog" aria-labelledby="confirm-title"><div className="dialog-heading"><ShieldCheck size={24} /><button className="icon-button" aria-label="Close confirmation" onClick={() => dialog.current?.close()}><X size={20} /></button></div><h2 id="confirm-title">Apply this plan to the demo?</h2><p>{number(plan?.operations.length)} reviewed operations will update only this session’s fixture documents. The server keeps a demo copy and immediately scans the result.</p><div className="dialog-actions"><button className="button secondary" onClick={() => dialog.current?.close()}>Keep reviewing</button><button className="button primary" onClick={apply}><Check size={16} />Apply demo plan</button></div></dialog>
  </div>;
}
