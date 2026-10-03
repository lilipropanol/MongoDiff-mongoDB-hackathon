import { useEffect, useRef, useState, type ReactNode } from "react";
import Icon from "@leafygreen-ui/icon";
import IconButton from "@leafygreen-ui/icon-button";
import { MongoDBLogoMark } from "@leafygreen-ui/logo";
import TextInput from "@leafygreen-ui/text-input";
import { Tabs, Tab } from "@leafygreen-ui/tabs";
import Badge from "@leafygreen-ui/badge";
import Button from "@leafygreen-ui/button";
import type { Report, Source } from "../types";
import { number } from "../api";

type Props = {
  children: ReactNode;
  database: string;
  collection: string;
  report: Report | null;
  dark: boolean;
  source: Source;
  onTheme: () => void;
};
const atlasTabs = [
  "Documents",
  "Aggregations",
  "Schema",
  "Indexes",
  "Validation",
  "Search Indexes",
];
export function AtlasShell({
  children,
  database,
  collection,
  report,
  dark,
  source,
  onTheme,
}: Props) {
  const [filter, setFilter] = useState("");
  const [expanded, setExpanded] = useState(true);
  const [explorerOpen, setExplorerOpen] = useState(false);
  const tabsRef = useRef<HTMLDivElement>(null);
  const explorerRef = useRef<HTMLElement>(null);
  const explorerToggleRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!explorerOpen) return;
    explorerRef.current?.querySelector<HTMLInputElement>("input")?.focus();
    return () => explorerToggleRef.current?.focus();
  }, [explorerOpen]);
  useEffect(() => {
    const tablist =
      tabsRef.current?.querySelector<HTMLElement>('[role="tablist"]');
    if (!tablist) return;
    const keepActiveVisible = () => {
      if (tablist.scrollWidth > tablist.clientWidth) {
        tablist.scrollLeft = tablist.scrollWidth - tablist.clientWidth;
      }
    };
    const observer = new ResizeObserver(keepActiveVisible);
    observer.observe(tablist);
    keepActiveVisible();
    return () => observer.disconnect();
  }, []);
  const demo = source === "demo";
  const matches =
    !filter ||
    `${database}.${collection}`.toLowerCase().includes(filter.toLowerCase());
  return (
    <div className="atlas-shell" data-theme={dark ? "dark" : "light"}>
      <a href="#workspace" className="skip-link">
        Skip to collection workspace
      </a>
      <header className="atlas-topbar">
        <div className="logo-cell">
          <MongoDBLogoMark
            height={40}
            color={dark ? "green-base" : "green-dark-2"}
          />
        </div>
        <div className="nav-picker">
          <span>ORGANIZATION</span>
          <div>
            mongoDiff workspace <Icon aria-hidden glyph="ChevronDown" />
          </div>
        </div>
        <Icon aria-hidden className="nav-chevron" glyph="ChevronRight" />
        <div className="nav-picker project-picker">
          <span>PROJECT</span>
          <div>
            Project 0 <Icon aria-hidden glyph="ChevronDown" />
          </div>
        </div>
        <div className="global-actions">
          <IconButton
            aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
            onClick={onTheme}
          >
            <Icon aria-hidden glyph={dark ? "Sun" : "Moon"} />
          </IconButton>
          <IconButton
            aria-label="MongoDB documentation"
            href="https://www.mongodb.com/docs/atlas/"
            target="_blank"
            rel="noreferrer"
          >
            <Icon aria-hidden glyph="QuestionMarkWithCircle" />
          </IconButton>
          <span className="context-icon" title="Atlas navigation context">
            <Icon aria-hidden glyph="CreditCard" />
          </span>
          <span className="context-icon">
            <Icon aria-hidden glyph="InviteUser" />
          </span>
          <span className="context-icon">
            <Icon aria-hidden glyph="Bell" />
          </span>
          <span className="context-icon">
            <Icon aria-hidden glyph="Apps" />
          </span>
          <span className="user-avatar" aria-label="Local prototype workspace">
            MD
          </span>
        </div>
      </header>
      <div className="atlas-body">
        <nav className="icon-rail" aria-label="Atlas navigation context">
          <span className="rail-item">
            <Icon aria-hidden glyph="Folder" />
          </span>
          <span className="rail-item rail-active" title="Data Explorer">
            <Icon aria-hidden glyph="Database" />
          </span>
          <span className="rail-item">
            <Icon aria-hidden glyph="MultiLayers" />
          </span>
          <span className="rail-item">
            <Icon aria-hidden glyph="Charts" />
          </span>
          <span className="rail-item">
            <Icon aria-hidden glyph="Lock" />
          </span>
          <span className="rail-bottom">
            <Icon aria-hidden glyph="Support" />
          </span>
        </nav>
        <aside
          id="collection-explorer"
          ref={explorerRef}
          className={`collection-explorer ${explorerOpen ? "explorer-open" : ""}`}
          aria-label="Collection explorer"
          onKeyDown={(event) => {
            if (explorerOpen && event.key === "Escape") {
              event.preventDefault();
              setExplorerOpen(false);
            }
          }}
        >
          <div className="explorer-heading">
            <h2>Data Explorer</h2>
            <IconButton
              className="mobile-close"
              aria-label="Close collection explorer"
              onClick={() => setExplorerOpen(false)}
            >
              <Icon aria-hidden glyph="X" />
            </IconButton>
          </div>
          <div className="explorer-links">
            <span>
              <Icon aria-hidden glyph="Code" />
              My Queries
            </span>
            <span>
              <Icon aria-hidden glyph="Diagram" />
              Data Modeling
            </span>
          </div>
          <div className="cluster-heading">
            <strong>CLUSTERS (1)</strong>
            <Icon aria-hidden glyph="ChevronDown" />
          </div>
          <div className="explorer-search">
            <span id="collection-filter-label" className="sr-only">
              Filter collections
            </span>
            <TextInput
              aria-labelledby="collection-filter-label"
              optional
              placeholder="Filter collections…"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
          </div>
          <div className="database-tree">
            <div className="tree-row cluster-row">
              <Icon aria-hidden glyph="ChevronDown" />
              <span className="cluster-icon">
                <Icon aria-hidden glyph="Database" />
                <i />
              </span>
              <span>{demo ? "DemoCluster" : "Cluster0"}</span>
            </div>
            <div className="tree-row tree-context">
              <Icon aria-hidden glyph="ChevronRight" />
              <Icon aria-hidden glyph="Database" />
              <span>admin</span>
            </div>
            <div className="tree-row tree-context">
              <Icon aria-hidden glyph="ChevronRight" />
              <Icon aria-hidden glyph="Database" />
              <span>local</span>
            </div>
            {matches ? (
              <>
                <button
                  className="tree-row database-row"
                  aria-expanded={expanded}
                  onClick={() => setExpanded(!expanded)}
                >
                  <Icon
                    aria-hidden
                    glyph={expanded ? "ChevronDown" : "ChevronRight"}
                  />
                  <Icon aria-hidden glyph="Database" />
                  <span>{database}</span>
                </button>
                {expanded && (
                  <a
                    className="tree-row selected-collection"
                    href="#workspace"
                    onClick={() => setExplorerOpen(false)}
                    aria-current="page"
                  >
                    <Icon aria-hidden glyph="Folder" />
                    <strong>{collection}</strong>
                    <Icon aria-hidden glyph="Ellipsis" />
                  </a>
                )}
              </>
            ) : (
              <p className="tree-empty">No matching collections.</p>
            )}
          </div>
          <div className="explorer-footnote">
            <Icon aria-hidden glyph="InfoWithCircle" />
            <span>
              {demo
                ? "Isolated demo collection"
                : "Server-configured collection"}
            </span>
          </div>
        </aside>
        <div className="collection-workspace">
          <nav className="open-collection-strip" aria-label="Open collection">
            <div>
              <Icon aria-hidden glyph="Folder" />
              {collection}
            </div>
            <span className="strip-context">
              <Icon aria-hidden glyph="Plus" />
            </span>
          </nav>
          <main id="workspace">
            <div className="collection-heading">
              <div className="collection-path">
                <IconButton
                  ref={explorerToggleRef}
                  className="explorer-toggle"
                  aria-label="Open collection explorer"
                  aria-expanded={explorerOpen}
                  aria-controls="collection-explorer"
                  onClick={() => setExplorerOpen(true)}
                >
                  <Icon aria-hidden glyph="Menu" />
                </IconButton>
                <span>{demo ? "DemoCluster" : "Cluster0"}</span>
                <Icon aria-hidden glyph="ChevronRight" />
                <span>{database}</span>
                <Icon aria-hidden glyph="ChevronRight" />
                <h1>{collection}</h1>
                {report && (
                  <span className="document-count">
                    {number(report.total_docs)} documents
                  </span>
                )}
              </div>
              <Button
                className="collection-docs"
                href="https://www.mongodb.com/docs/manual/core/schema-validation/"
                target="_blank"
                rel="noreferrer"
                leftGlyph={<Icon aria-hidden glyph="OpenNewTab" />}
              >
                Documentation
              </Button>
            </div>
            <div className="collection-tabs" ref={tabsRef}>
              <Tabs
                aria-label="Collection features"
                value={6}
                onValueChange={() => {}}
              >
                {atlasTabs.map((name) => (
                  <Tab key={name} name={name} disabled />
                ))}
                <Tab
                  name={
                    <span className="guard-tab-label">
                      <Icon aria-hidden glyph="Shield" />
                      mongoDiff<Badge variant="green">New</Badge>
                    </span>
                  }
                >
                  <div className="guard-content">{children}</div>
                </Tab>
              </Tabs>
            </div>
          </main>
        </div>
        <footer className="atlas-footer">
          <span>MongoDB Atlas mongoDiff · v1.0.0</span>
        </footer>
      </div>
    </div>
  );
}
