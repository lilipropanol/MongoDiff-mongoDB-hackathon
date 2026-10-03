import { ShieldCheck } from 'lucide-react';
import type { Report } from '../types';
import { CodeBlock } from './CodeBlock';

export function ValidatorView({ report }: { report: Report }) {
  const command = { collMod: report.collection, validator: report.new_validator, validationLevel: 'strict', validationAction: 'warn' };
  return <div className="view-enter"><div className="section-heading"><div><h2>Proposed collection validator</h2><p>Review the generated rule before attaching it to the collection.</p></div><span className="badge warning">Review only</span></div>
    <div className="validator-explanation"><ShieldCheck size={22} /><div><h3>Start with warnings</h3><p>This command allows writes and logs validation violations. A validator does not repair existing documents. After validating application behavior and cleaning existing data, review a separate change to <code>validationAction: "error"</code>.</p></div></div>
    <CodeBlock label="collMod command · not executed" filename="validator.json" code={JSON.stringify(command, null, 2)} />
  </div>;
}
