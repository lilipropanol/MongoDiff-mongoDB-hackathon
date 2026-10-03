import { useEffect, useRef, useState } from "react";
import LeafyGreenProvider from "@leafygreen-ui/leafygreen-provider";
import Button from "@leafygreen-ui/button";
import Icon from "@leafygreen-ui/icon";
import IconButton from "@leafygreen-ui/icon-button";
import Badge from "@leafygreen-ui/badge";
import { Body } from "@leafygreen-ui/typography";
import { modelName, type Issue } from "./presentation";
import { api, download, number } from "./api";
import type { Config, Report, Source } from "./types";
import { AtlasShell } from "./components/AtlasShell";
import {
  ScanSummary,
  RootCauseTable,
  ReasonDetails,
} from "./components/GuardReport";
import { DetailDialog } from "./components/DetailDialog";
import { ChangesView } from "./components/ChangesView";
import { FixesView } from "./components/FixesView";
import { ValidatorView } from "./components/ValidatorView";

type Detail = "changes" | "validator" | "history" | Issue | null;
export function App() {
  const [dark, setDark] = useState(
    () => localStorage.getItem("schema-guard-theme") !== "light",
  );
  const [config, setConfig] = useState<Config | null>(null);
  const [source, setSource] = useState<Source>("demo");
  const [report, setReport] = useState<Report | null>(null);
  const [history, setHistory] = useState<Report[]>([]);
  const [detail, setDetail] = useState<Detail>(null);
  const [busy, setBusy] = useState(true);
  const [repairBusy, setRepairBusy] = useState(false);
  const [error, setError] = useState("");
  const [historyError, setHistoryError] = useState("");
  const [before, setBefore] = useState<Report | null>(null);
  const initialized = useRef(false);
  const working = busy || repairBusy;
  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    localStorage.setItem("schema-guard-theme", dark ? "dark" : "light");
  }, [dark]);
  async function refreshHistory() {
    try {
      setHistory(await api.history());
      setHistoryError("");
    } catch {
      setHistoryError("Run history could not be loaded. Retry to refresh it.");
    }
  }
  async function run(mode: Source, reset = false) {
    setBusy(true);
    setError("");
    setDetail(null);
    setBefore(null);
    try {
      const next = reset ? await api.reset() : await api.analyze(mode);
      setReport(next);
      setSource(next.source);
      await refreshHistory();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not run the analysis.",
      );
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    api
      .config()
      .then(setConfig)
      .catch(() => setConfig(null));
    void run("demo");
  }, []);
  async function applied(next: Report) {
    setBefore(report);
    setReport(next);
    await refreshHistory();
  }
  function selectSource(next: Source) {
    setSource(next);
    setReport(null);
    setError("");
    setBefore(null);
    setDetail(null);
  }
  const database =
    report?.database ||
    (source === "demo"
      ? "schema_guard_demo"
      : config?.database || "sample_mflix");
  const collection = report?.collection || config?.collection || "movies";
  const detailTitle =
    typeof detail === "object" && detail
      ? `${detail.field} · ${detail.label}`
      : detail === "changes"
        ? "Application model changes"
        : detail === "validator"
          ? "Collection validator preview"
          : "Run history";
  return (
    <LeafyGreenProvider darkMode={dark} baseFontSize={14}>
      <AtlasShell
        database={database}
        collection={collection}
        report={report}
        source={source}
        dark={dark}
        onTheme={() => setDark(!dark)}
      >
        <div className="guard-heading">
          <div>
            <div className="title-line">
              <Icon aria-hidden glyph="Shield" size={24} />
              <h2>Schema Guard</h2>
              <Badge variant="blue">
                {source === "demo" ? "Demo" : "Preview"}
              </Badge>
            </div>
            <Body className="guard-description">
              {busy ? (
                "Scanning collection…"
              ) : report ? (
                <>
                  Scan complete for collection <code>{report.collection}</code>{" "}
                  against proposed model <code>{modelName(report)}</code>.
                </>
              ) : (
                "Scan your collection against the proposed model."
              )}
            </Body>
          </div>
          <div className="heading-actions">
            <Button
              size="small"
              leftGlyph={<Icon aria-hidden glyph="Clock" />}
              onClick={() => setDetail("history")}
              disabled={working}
            >
              Run history
            </Button>
            <Button
              size="small"
              leftGlyph={<Icon aria-hidden glyph="Download" />}
              disabled={!report || working}
              onClick={() =>
                report &&
                download(
                  `schema-guard-${report.id}.json`,
                  JSON.stringify(report, null, 2),
                )
              }
            >
              Export report
            </Button>
          </div>
        </div>
        <div className="analysis-toolbar">
          <div className="source-control">
            <label htmlFor="data-source">Data source</label>
            <select
              id="data-source"
              value={source}
              disabled={working}
              onChange={(e) => selectSource(e.target.value as Source)}
            >
              <option value="demo">Demo fixtures</option>
              <option value="atlas">
                MongoDB Atlas · read-only
                {config?.atlas_configured ? "" : " · setup required"}
              </option>
            </select>
          </div>
          <div className="scan-meta">
            <Icon aria-hidden glyph="Code" />
            <span>
              Current model <Icon aria-hidden glyph="ArrowRight" /> Proposed
              model
            </span>
            {report && (
              <span className="scan-time">
                Last scan{" "}
                {new Date(report.run_at).toLocaleTimeString("en-IE", {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </span>
            )}
          </div>
          <div className="toolbar-buttons">
            {source === "demo" && (
              <IconButton
                aria-label="Reset demo data"
                onClick={() => void run("demo", true)}
                disabled={working}
              >
                <Icon aria-hidden glyph="Refresh" />
              </IconButton>
            )}
            <Button
              size="small"
              variant="primary"
              className="guard-primary"
              leftGlyph={<Icon aria-hidden glyph="Play" />}
              onClick={() => void run(source)}
              disabled={working}
            >
              {busy ? "Analyzing…" : "Run analysis"}
            </Button>
          </div>
        </div>
        {error && (
          <div className="error-banner" role="alert">
            <Icon aria-hidden glyph="Warning" />
            <p>{error}</p>
            <Button
              size="xsmall"
              disabled={working}
              onClick={() => void run(source)}
            >
              Try again
            </Button>
          </div>
        )}
        {busy ? (
          <div
            className="loading-state"
            role="status"
            aria-label="Analyzing collection"
          >
            <div className="skeleton skeleton-summary" />
            <div className="skeleton skeleton-table" />
            <p>Scanning documents against the proposed schema…</p>
          </div>
        ) : report ? (
          <div className="view-enter">
            {before && (
              <div className="verification-banner">
                <Icon aria-hidden glyph="CheckmarkWithCircle" />
                <div>
                  <strong>
                    {number(before.failing)} → {number(report.failing)} failing
                    documents
                  </strong>
                </div>
              </div>
            )}
            <ScanSummary
              report={report}
              openValidator={() => setDetail("validator")}
            />
            <RootCauseTable report={report} inspect={setDetail} />
            <section className="surface remediation-panel">
              <FixesView
                report={report}
                key={report.id}
                onApplied={(next) => void applied(next)}
                onWorking={setRepairBusy}
              />
            </section>
          </div>
        ) : (
          <div className="empty-state">
            <Icon aria-hidden glyph="Shield" size={40} />
            <h2>Preview your next model change</h2>
            <p>
              {source === "atlas"
                ? "Configure Atlas on the server, then run an analysis."
                : "Run an analysis to see document impact and suggested repairs."}
            </p>
            <Button
              variant="primary"
              className="guard-primary"
              onClick={() => void run(source)}
            >
              Run analysis
            </Button>
          </div>
        )}
        {detail && (
          <DetailDialog title={detailTitle} onClose={() => setDetail(null)}>
            {typeof detail === "object" ? (
              <ReasonDetails issue={detail} />
            ) : detail === "history" ? (
              <>
                <div className="section-heading">
                  <p>Saved reports from this browser session.</p>
                  <div className="button-group">
                    <Button
                      size="small"
                      disabled={!report}
                      onClick={() => setDetail("changes")}
                    >
                      Model changes
                    </Button>
                    <Button size="small" onClick={() => void refreshHistory()}>
                      Refresh
                    </Button>
                  </div>
                </div>
                {historyError && (
                  <p className="history-error" role="alert">
                    {historyError}
                  </p>
                )}
                {history.length ? (
                  <div className="history-list">
                    {history.map((item) => (
                      <button
                        key={item.id}
                        onClick={() => {
                          setReport(item);
                          setSource(item.source);
                          setDetail(null);
                          setBefore(null);
                        }}
                      >
                        <Icon aria-hidden glyph="Clock" />
                        <div>
                          <strong>
                            {item.database}.{item.collection}
                          </strong>
                          <span>
                            {new Date(item.run_at).toLocaleString("en-IE")} ·{" "}
                            {item.source === "demo" ? "Demo" : "Atlas"}
                          </span>
                        </div>
                        <Badge variant={item.failing ? "yellow" : "green"}>
                          {number(item.failing)} failures
                        </Badge>
                        <Icon aria-hidden glyph="ChevronRight" />
                      </button>
                    ))}
                  </div>
                ) : (
                  <p>No saved runs yet.</p>
                )}
              </>
            ) : (
              report &&
              (detail === "changes" ? (
                <ChangesView report={report} />
              ) : (
                <ValidatorView report={report} />
              ))
            )}
          </DetailDialog>
        )}
      </AtlasShell>
    </LeafyGreenProvider>
  );
}
