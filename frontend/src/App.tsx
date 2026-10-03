import { useEffect, useRef, useState } from "react";
import LeafyGreenProvider from "@leafygreen-ui/leafygreen-provider";
import Button from "@leafygreen-ui/button";
import Icon from "@leafygreen-ui/icon";
import IconButton from "@leafygreen-ui/icon-button";
import Badge from "@leafygreen-ui/badge";
import Banner from "@leafygreen-ui/banner";
import Card from "@leafygreen-ui/card";
import { Select, Option } from "@leafygreen-ui/select";
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
    () => localStorage.getItem("schema-guard-theme-v2") === "dark",
  );
  const [config, setConfig] = useState<Config | null>(null);
  const [source, setSource] = useState<Source>("demo");
  const [suggestionsOptIn, setSuggestionsOptIn] = useState(false);
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
    localStorage.setItem("schema-guard-theme-v2", dark ? "dark" : "light");
    document
      .querySelector('meta[name="theme-color"]')
      ?.setAttribute("content", dark ? "#001e2b" : "#ffffff");
  }, [dark]);
  async function refreshHistory() {
    try {
      setHistory(await api.history());
      setHistoryError("");
    } catch {
      setHistoryError("Run history could not be loaded. Retry to refresh it.");
    }
  }
  async function run(mode: Source, reset = false, includeSuggestions = suggestionsOptIn) {
    setBusy(true);
    setError("");
    setDetail(null);
    setBefore(null);
    try {
      const next = reset
        ? await api.reset()
        : await api.analyze(mode, mode === "atlas" && includeSuggestions);
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
      ? detail.path
      : detail === "changes"
        ? "Application model changes"
        : detail === "validator"
          ? "Collection validator preview"
          : "Run history";
  return (
    <LeafyGreenProvider darkMode={dark} baseFontSize={16}>
      <AtlasShell
        database={database}
        collection={collection}
        report={report}
        source={source}
        dark={dark}
        onTheme={() => setDark(!dark)}
      >
        <Card
          as="section"
          className="analysis-panel"
          aria-label="Collection analysis"
        >
          <div className="guard-heading">
            <div className="scan-caption">
              <Badge variant="lightgray">
                {source === "demo" ? "Demo" : "Preview"}
              </Badge>
              <Body className="guard-description">
                {busy ? (
                  "Scanning collection…"
                ) : report ? (
                  <>
                    Scan complete for collection{" "}
                    <code>{report.collection}</code> against proposed model{" "}
                    <code>{modelName(report)}</code>.
                  </>
                ) : (
                  "Scan your collection against the proposed model."
                )}
              </Body>
            </div>
            <div className="heading-actions">
              <Button
                leftGlyph={<Icon aria-hidden glyph="Clock" />}
                onClick={() => setDetail("history")}
                disabled={working}
              >
                Run history
              </Button>
              <Button
                leftGlyph={<Icon aria-hidden glyph="Download" />}
                disabled={!report || working}
                onClick={() =>
                  report &&
                  download(
                    `mongodiff-${report.id}.json`,
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
              <span id="data-source-label">Data source</span>
              <Select
                className="source-select"
                id="data-source"
                aria-labelledby="data-source-label"
                value={source}
                disabled={working}
                allowDeselect={false}
                onChange={(value) => {
                  if (value === "demo" || value === "atlas")
                    selectSource(value);
                }}
              >
                <Option value="demo">Demo fixtures</Option>
                <Option
                  value="atlas"
                  description={
                    config?.atlas_configured
                      ? "Read-only analysis"
                      : "Setup required · read-only"
                  }
                >
                  MongoDB Atlas
                </Option>
              </Select>
            </div>
            <div className="scan-meta">
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
            {source === "atlas" && config?.suggestions_configured && (
              <label className="suggestion-opt-in">
                <input
                  type="checkbox"
                  checked={suggestionsOptIn}
                  disabled={working}
                  onChange={(event) => setSuggestionsOptIn(event.target.checked)}
                />
                <span>
                  Include suggestions
                  <small>{config.suggestion_mode === "lexical" ? "Offline matching" : "Optional · " + (config.suggestion_mode === "atlas-vector" ? "Atlas Vector Search" : "Voyage AI")}</small>
                </span>
              </label>
            )}
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
          {source === "atlas" && suggestionsOptIn && config?.suggestions_configured && config.suggestion_mode !== "lexical" && (
            <p className="suggestion-disclosure">
              Suggestions share bounded distinct values, allowed values, and field names with the configured provider. Document examples, IDs, and connection details are excluded.
              {config.suggestion_mode === "atlas-vector" && " Atlas Vector Search stores allowed-value vectors in the separately configured vocabulary collection; it does not write to the scanned collection."}
            </p>
          )}
        </Card>
        {error && (
          <Banner variant="danger" className="scan-error" role="alert">
            <div className="scan-error-content">
              <span>{error}</span>
              <Button
                size="xsmall"
                disabled={working}
                onClick={() => void run(source)}
              >
                Try again
              </Button>
            </div>
          </Banner>
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
              <Banner variant="success" className="scan-verification">
                <strong>
                  {number(before.failing)} → {number(report.failing)} failing
                  documents
                </strong>
              </Banner>
            )}
            <ScanSummary
              report={report}
              openValidator={() => setDetail("validator")}
            />
            {report.scan?.suggestions && (
              <div className="suggestion-status" role="status">
                <Icon aria-hidden glyph={report.scan.suggestions.status === "fallback" ? "Warning" : "Sparkle"} />
                <span>
                  {report.scan.suggestions.provider === "lexical" ? "Offline value suggestions" :
                    report.scan.suggestions.method === "atlas-vector-search" ? "Atlas Vector Search suggestions" :
                      report.scan.suggestions.provider === "voyage" ? "Voyage AI suggestions" : "Suggestions"}
                  {report.scan.suggestions.status === "fallback" && report.scan.suggestions.fallback_reason
                    ? ` · Fallback: ${report.scan.suggestions.fallback_reason}`
                    : " · Review candidates before using them."}
                </span>
              </div>
            )}
            <RootCauseTable report={report} inspect={setDetail} />
            {!!report.warnings?.length && (
              <Card as="section" className="analysis-note-panel" aria-label="Model defaults">
                <h2>Fields using model defaults</h2>
                {report.warnings.map((warning) => (
                  <p key={warning.path}><code>{warning.path}</code> · {warning.count.toLocaleString("en-IE")} documents · missing from storage</p>
                ))}
              </Card>
            )}
            {report.versioning && (
              <Card as="section" className="analysis-note-panel" aria-label="Schema version analysis">
                <div className="version-heading">
                  <h2>Schema version</h2>
                  {report.versioning.bump_recommended && <Badge variant="yellow">Version bump recommended</Badge>}
                </div>
                <p>{report.versioning.message}</p>
                {report.versioning.versions.length > 0 && (
                  <div className="version-list">
                    {report.versioning.versions.map((item, index) => (
                      <span key={`${String(item.version)}-${index}`}><strong>v{String(item.version ?? "unset")}</strong> · {number(item.failing)} failing</span>
                    ))}
                  </div>
                )}
              </Card>
            )}
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
          <DetailDialog
            title={detailTitle}
            compact={typeof detail === "object"}
            onClose={() => setDetail(null)}
          >
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
