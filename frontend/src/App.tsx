import { useEffect, useRef, useState } from 'react';
import { Activity, ArrowDownToLine, ArrowUpRight, BookOpen, Check, ChevronDown, ChevronRight, Database, FileCode2, FlaskConical, History, Layers, Leaf, LoaderCircle, Play, RotateCcw, ShieldCheck, Wrench } from 'lucide-react';
import { api, download, number } from './api';
import type { Config, Report, Source, Tab } from './types';
import { ImpactView } from './components/ImpactView';
import { ChangesView } from './components/ChangesView';
import { FixesView } from './components/FixesView';
import { ValidatorView } from './components/ValidatorView';

const tabs: { id: Tab; title: string; icon: typeof Activity }[] = [
  { id: 'impact', title: 'Impact report', icon: Activity }, { id: 'changes', title: 'Model changes', icon: FileCode2 },
  { id: 'fixes', title: 'Fix preview', icon: Wrench }, { id: 'validator', title: 'Validator', icon: ShieldCheck }, { id: 'history', title: 'Run history', icon: History },
];

export function App() {
  const [config, setConfig] = useState<Config | null>(null);
  const [source, setSource] = useState<Source>('demo');
  const [report, setReport] = useState<Report | null>(null);
  const [history, setHistory] = useState<Report[]>([]);
  const [tab, setTab] = useState<Tab>('impact');
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [historyError, setHistoryError] = useState('');
  const initialized = useRef(false);

  async function refreshHistory() {
    try { setHistory(await api.history()); setHistoryError(''); }
    catch { setHistoryError('Run history could not be loaded. Retry to refresh it.'); }
  }
  async function run(mode: Source, reset = false) {
    setBusy(true); setError(''); setNotice('');
    try {
      const next = reset ? await api.reset() : await api.analyze(mode);
      setReport(next); setSource(next.source); setTab('impact');
      setNotice(reset ? 'Demo fixtures restored. A fresh scan is ready.' : 'Analysis complete. No data was changed.');
      await refreshHistory();
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not run the analysis.'); }
    finally { setBusy(false); }
  }
  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    api.config().then(setConfig).catch(() => setConfig(null));
    void run('demo');
  }, []);

  async function applied(next: Report) {
    setReport(next); setTab('impact'); setNotice(`Demo plan applied. ${number(next.failing)} failing documents remain.`);
    await refreshHistory();
  }
  function selectSource(next: Source) {
    setSource(next); setReport(null); setError(''); setNotice(''); setTab('impact');
  }
  const displayedDatabase = report?.database || (source === 'demo' ? 'schema_guard_demo' : config?.database || 'sample_mflix');
  const displayedCollection = report?.collection || config?.collection || 'movies';
  const modelLabel = source === 'demo' ? 'Movie' : 'Configured model pair';
  const changeLabel = report ? `${report.changes.length} schema changes detected` : 'Current model → proposed model';
  return <div className="app-shell">
    <a href="#workspace" className="skip-link">Skip to collection workspace</a>
    <aside className="sidebar" aria-label="Project navigation">
      <div className="brand-lockup"><Leaf size={26} strokeWidth={1.6} /><span>MongoDB<span>ATLAS INSPIRED</span></span></div>
      <div className="project-selector"><span className="project-avatar">SG</span><div><small>Project</small><strong>Schema Guard</strong></div><ChevronDown size={16} /></div>
      <div className="nav-label">DATABASE</div>
      <div className="side-section"><Database size={18} /><span>Database deployments</span></div>
      <a className="side-link active" href="#workspace" aria-label="Collections"><Layers size={18} /><span>Collections</span><ChevronRight size={15} /></a>
      <div className="collection-tree"><span><span className="tree-dot" />{source === 'demo' ? 'DemoCluster' : 'AtlasCluster'}</span><span>{displayedDatabase}</span><strong>{displayedCollection}</strong></div>
      <div className="sidebar-bottom"><ShieldCheck size={22} /><strong>Guard your next change</strong><p>Know what breaks before your application model ships.</p><a href="https://www.mongodb.com/docs/manual/core/schema-validation/" target="_blank" rel="noreferrer">Schema validation docs <ArrowUpRight size={14} /></a><small>Independent feature prototype</small></div>
    </aside>
    <div className="workspace-shell">
      <header className="topbar"><div className="breadcrumb"><span>Schema Guard</span><ChevronRight size={14} /><span>Collections</span></div><div className="topbar-right"><span className="prototype-label">Feature prototype</span><a className="icon-button" href="/docs" target="_blank" rel="noreferrer" aria-label="Open API documentation"><BookOpen size={18} /></a><span className="user-avatar" aria-label="Local workspace">SG</span></div></header>
      <main id="workspace" className="main-content">
        <div className="collection-breadcrumb"><Database size={14} /><span>{displayedDatabase}</span><ChevronRight size={14} /><strong>{displayedCollection}</strong></div>
        <div className="page-heading"><div><div className="title-line"><h1>Schema Guard</h1><span className="badge preview">Preview</span></div><p>See how a model change affects the data already in your collection.</p></div><button className="button secondary" disabled={!report || busy} onClick={() => report && download(`schema-guard-${report.id}.json`, JSON.stringify(report, null, 2))}><ArrowDownToLine size={16} />Export report</button></div>
        <div className="analysis-toolbar"><div className="source-control"><label htmlFor="data-source">Data source</label><select id="data-source" value={source} disabled={busy} onChange={e => selectSource(e.target.value as Source)}><option value="demo">Demo fixtures</option><option value="atlas">MongoDB Atlas{config?.atlas_configured ? '' : ' · setup required'}</option></select></div><div className="model-pair"><span className="model-label">MODEL CHANGE</span><code>{modelLabel}</code><ChevronRight size={14} /><span>{changeLabel}</span></div><div className="toolbar-buttons">{source === 'demo' && <button className="icon-button" onClick={() => void run('demo', true)} disabled={busy} aria-label="Reset demo data" title="Reset demo data"><RotateCcw size={17} /></button>}<button className="button primary" onClick={() => void run(source)} disabled={busy}>{busy ? <LoaderCircle className="spin" size={16} /> : <Play size={16} />}{busy ? 'Analyzing…' : 'Run analysis'}</button></div></div>
        {source === 'demo' ? <div className="demo-banner"><FlaskConical size={17} /><span><strong>Demo workspace.</strong> Twelve synthetic movie documents. Repair decisions apply only to your demo session.</span></div> : <div className="demo-banner atlas-banner"><Database size={17} /><span>{config?.atlas_configured ? 'Connected through the server’s configured MongoDB URI. Analysis reads collection data.' : 'Set MONGODB_URI in the server .env and restart the API to scan an Atlas collection.'}</span></div>}
        {error && <div className="error-banner" role="alert"><p>{error}</p><button className="text-button" onClick={() => void run(source)} disabled={busy}>Try again</button></div>}
        {notice && !busy && <div className="notice" role="status"><Check size={16} /><span>{notice}</span></div>}
        <section className="workspace-panel" aria-label="Schema analysis">
          <div className="tabs" role="tablist" aria-label="Analysis views">{tabs.map(({ id, title, icon: Icon }) => <button key={id} id={`tab-${id}`} className={tab === id ? 'active' : ''} role="tab" aria-selected={tab === id} aria-controls="analysis-content" disabled={busy} tabIndex={tab === id ? 0 : -1} onClick={() => setTab(id)} onKeyDown={event => {
            if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
            event.preventDefault(); const index = tabs.findIndex(t => t.id === tab);
            const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
            setTab(tabs[next].id); document.getElementById(`tab-${tabs[next].id}`)?.focus();
          }}><Icon size={16} />{title}{id === 'changes' && report && <span className="tab-count">{report.changes.length}</span>}</button>)}</div>
          <div id="analysis-content" className="panel-content" role="tabpanel" aria-labelledby={`tab-${tab}`} aria-busy={busy}>
            {busy ? <div className="loading-state" role="status"><div className="skeleton skeleton-heading" /><div className="skeleton skeleton-card" /><div className="skeleton skeleton-row" /><div className="skeleton skeleton-row" /><span>Scanning documents against the proposed schema…</span></div> : tab === 'history' ? <div className="view-enter"><div className="section-heading"><div><h2>Run history</h2><p>Saved reports from this browser session.</p></div><button className="button secondary" onClick={() => void refreshHistory()}>Refresh</button></div>{historyError && <p role="alert" className="history-error">{historyError}</p>}{history.length ? <div className="history-list">{history.map((item, i) => <button key={item.id} onClick={() => { setReport(item); setSource(item.source); setTab('impact'); setNotice('Viewing a saved run. Run analysis to refresh it before applying a plan.'); }}><span className="history-icon"><History size={18} /></span><div><strong>{item.database}.{item.collection}</strong><span>{new Date(item.run_at).toLocaleTimeString('en-IE', { hour: '2-digit', minute: '2-digit', second: '2-digit' })} · {item.source === 'demo' ? 'Demo fixtures' : 'MongoDB scan'}{i === 0 ? ' · latest' : ''}</span></div><span className={`badge ${item.failing ? 'warning' : 'healthy'}`}>{number(item.failing)} failures</span><ChevronRight size={16} /></button>)}</div> : <div className="empty-state"><History size={32} /><h3>No saved runs</h3><p>Run an analysis to start a history of collection checks.</p></div>}</div> : !report ? <div className="empty-state"><ShieldCheck size={36} /><h2>Preview your next model change</h2><p>{source === 'atlas' ? 'Configure Atlas on the server, then run an analysis.' : 'Run an analysis to see document impact and suggested repairs.'}</p><button className="button primary" onClick={() => void run(source)}>Run analysis</button></div> : tab === 'impact' ? <ImpactView report={report} key={report.id} openFixes={() => setTab('fixes')} /> : tab === 'changes' ? <ChangesView report={report} /> : tab === 'fixes' ? <FixesView report={report} key={report.id} onApplied={next => void applied(next)} /> : <ValidatorView report={report} />}
          </div>
        </section>
        <footer className="workspace-footer"><span><ShieldCheck size={14} />Deterministic schema comparison · Human-reviewed repairs</span><span>{report ? `${number(report.total_docs)} documents · ${report.source === 'demo' ? 'fixture adapter' : 'MongoDB $facet scan'}` : 'Ready to analyze'}</span></footer>
      </main>
    </div>
  </div>;
}
