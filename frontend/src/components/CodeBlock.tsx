import { useState } from 'react';
import { Check, Copy, Download } from 'lucide-react';
import { download } from '../api';

export function CodeBlock({ code, filename, label }: { code: string; filename: string; label: string }) {
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState('');
  async function copy() {
    try { await navigator.clipboard.writeText(code); setCopied(true); setError(''); }
    catch { setError('Copy is unavailable. Download the file instead.'); }
  }
  return <div className="code-panel">
    <div className="code-toolbar"><span>{label}</span><div className="button-group">
      <button className="icon-button" onClick={copy} aria-label={copied ? 'Copied code' : 'Copy code'}>{copied ? <Check size={16} /> : <Copy size={16} />}</button>
      <button className="icon-button" onClick={() => download(filename, code, filename.endsWith('.js') ? 'text/javascript' : 'text/plain')} aria-label={`Download ${filename}`}><Download size={16} /></button>
    </div></div>
    <pre tabIndex={0} aria-label={label}><code>{code}</code></pre>
    {error && <p role="status" className="code-message">{error}</p>}
  </div>;
}
