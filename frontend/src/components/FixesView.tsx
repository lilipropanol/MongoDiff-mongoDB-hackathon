import { useEffect, useRef, useState } from "react";
import Button from "@leafygreen-ui/button";
import Icon from "@leafygreen-ui/icon";
import Modal from "@leafygreen-ui/modal";
import { api } from "../api";
import { demoDecisions, repairScript } from "../presentation";
import type { Plan, Report } from "../types";
import { CodeBlock } from "./CodeBlock";

export function FixesView({
  report,
  onApplied,
  onWorking,
  mappingOverrides,
}: {
  report: Report;
  onApplied: (report: Report) => void;
  onWorking?: (busy: boolean) => void;
  mappingOverrides?: Record<string, Record<string, unknown>>;
}) {
  const [plan, setPlan] = useState<Plan | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const activeRequest = useRef(0);
  async function loadPlan() {
    const revision = ++activeRequest.current;
    setLoading(true);
    setError("");
    const decisions = demoDecisions(report);
    for (const [field, values] of Object.entries(mappingOverrides || {})) {
      decisions.mappings[field] = { ...decisions.mappings[field], ...values };
    }
    try {
      const next = await api.plan(
        report.id,
        decisions.defaults,
        decisions.mappings,
      );
      if (revision === activeRequest.current) setPlan(next);
    } catch (err) {
      if (revision === activeRequest.current)
        setError(
          err instanceof Error ? err.message : "Could not prepare the fix.",
        );
    } finally {
      if (revision === activeRequest.current) setLoading(false);
    }
  }
  useEffect(() => {
    void loadPlan();
    return () => {
      activeRequest.current++;
    };
  }, [report.id, mappingOverrides]);
  async function apply() {
    if (!plan || report.source !== "demo") return;
    setBusy(true);
    onWorking?.(true);
    setError("");
    setConfirmOpen(false);
    try {
      onApplied(await api.applyDemo(plan.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not apply the fix.");
    } finally {
      setBusy(false);
      onWorking?.(false);
    }
  }
  return (
    <div>
      <div className="surface-heading">
        <div>
          <h2>
            <Icon aria-hidden glyph="Code" />
            Repair plan
          </h2>
        </div>
      </div>
      <div className="remediation-body">
        {!!Object.keys(mappingOverrides || {}).length && (
          <p className="mapping-review-note" role="status">Your selected mappings are included below. Review the operations before applying.</p>
        )}
        {loading ? (
          <div className="pipeline-placeholder" role="status">
            Preparing fix…
          </div>
        ) : plan ? (
          <CodeBlock
            label="Generated MongoDB operations"
            filename="mongodiff_fix.js"
            code={repairScript(report, plan)}
          />
        ) : (
          <div className="pipeline-placeholder">Fix unavailable.</div>
        )}
        {error && (
          <div className="error-banner" role="alert">
            <Icon aria-hidden glyph="Warning" />
            <p>{error}</p>
            <Button size="xsmall" onClick={loadPlan} disabled={busy || loading}>
              Retry
            </Button>
          </div>
        )}
        <div className="plan-actions">
          <div>
            <Button
              variant="primary"
              className="guard-primary"
              leftGlyph={<Icon aria-hidden glyph="LightningBolt" />}
              disabled={
                busy ||
                loading ||
                !plan?.operations.length ||
                report.source !== "demo"
              }
              onClick={() => setConfirmOpen(true)}
              title={
                report.source === "atlas"
                  ? "Live repairs are not available"
                  : undefined
              }
            >
              {busy ? "Applying & rescanning…" : "Apply Fix & Rescan"}
            </Button>
          </div>
        </div>
      </div>
      <Modal
        open={confirmOpen}
        setOpen={setConfirmOpen}
        size="small"
        className="repair-confirmation"
        aria-labelledby="confirm-title"
      >
        <h2 id="confirm-title">Apply this fix?</h2>
        <p>
          Update this demo session using the displayed operations, then rescan.
        </p>
        <div className="dialog-actions">
          <Button onClick={() => setConfirmOpen(false)}>Cancel</Button>
          <Button variant="primary" className="guard-primary" onClick={apply}>
            Apply & Rescan
          </Button>
        </div>
      </Modal>
    </div>
  );
}
