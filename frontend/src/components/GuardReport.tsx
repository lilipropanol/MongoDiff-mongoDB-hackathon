import Button from "@leafygreen-ui/button";
import Icon from "@leafygreen-ui/icon";
import Card from "@leafygreen-ui/card";
import { Body } from "@leafygreen-ui/typography";
import {
  Cell,
  HeaderCell,
  HeaderRow,
  Row,
  Table,
  TableBody,
  TableHead,
} from "@leafygreen-ui/table";
import { number } from "../api";
import { summarizeIssues, type Issue } from "../presentation";
import type { Report } from "../types";

export function ScanSummary({
  report,
  openValidator,
}: {
  report: Report;
  openValidator: () => void;
}) {
  return (
    <section className="scan-summary" aria-label="Scan result">
      <Body className="scan-result">
        <strong data-testid="failure-count">
          {number(report.failing)} of {number(report.total_docs)}
        </strong>{" "}
        documents need attention.
      </Body>
      <Button onClick={openValidator}>View validator</Button>
    </section>
  );
}

export function RootCauseTable({
  report,
  inspect,
}: {
  report: Report;
  inspect: (issue: Issue) => void;
}) {
  const issues = summarizeIssues(report);
  return (
    <Card
      as="section"
      className="issues-panel"
      aria-labelledby="root-cause-title"
    >
      <div className="issues-heading">
        <h2 id="root-cause-title">Document issues</h2>
      </div>
      <Table
        className="cause-table"
        aria-labelledby="root-cause-title"
        baseFontSize={16}
        verticalAlignment="middle"
      >
        <TableHead>
          <HeaderRow>
            <HeaderCell>Path</HeaderCell>
            <HeaderCell>Issue</HeaderCell>
            <HeaderCell className="count-column" align="right">
              Documents
            </HeaderCell>
            <HeaderCell className="change-counts">New / existing</HeaderCell>
            <HeaderCell>
              <span className="sr-only">Details</span>
            </HeaderCell>
          </HeaderRow>
        </TableHead>
        <TableBody>
          {issues.map((issue) => (
            <Row key={`${issue.path}-${issue.reason}`}>
              <Cell>
                <code className="field-name">{issue.path}</code>
              </Cell>
              <Cell>{issue.label}</Cell>
              <Cell className="count-column" align="right">
                <strong>{number(issue.count)}</strong>
              </Cell>
              <Cell className="change-counts">
                {issue.count_newly === undefined
                  ? "—"
                  : `${number(issue.count_newly)} / ${number(issue.count_preexisting)}`}
              </Cell>
              <Cell align="right">
                <Button
                  size="xsmall"
                  onClick={() => inspect(issue)}
                  aria-label={`Details for ${issue.path}: ${issue.label}`}
                >
                  Details
                </Button>
              </Cell>
            </Row>
          ))}
        </TableBody>
      </Table>
      {!issues.length && (
        <div className="table-empty">
          <Icon aria-hidden glyph="CheckmarkWithCircle" />
          {report.failing
            ? "No field details available."
            : "No failing documents."}
        </div>
      )}
      {issues.length > 0 && <p className="issues-footnote">Issue counts may overlap; the scan total counts each document once.</p>}
      {report.unclassified > 0 && (
        <div className="table-empty">
          {number(report.unclassified)} documents need further review.
        </div>
      )}
    </Card>
  );
}

const reasonLabels: Record<string, string> = {
  missing: "Missing field",
  null_not_allowed: "Null value",
  wrong_type: "Wrong type",
  value_not_allowed: "Invalid value",
  nested_or_array_constraint: "Nested rule mismatch",
};
export function ReasonDetails({ issue }: { issue: Issue }) {
  const examples = issue.parts.flatMap((part) =>
    part.examples.map((document) => ({ document, reason: part.reason })),
  );
  return (
    <div className="reason-details">
      <Body className="inspection-summary">
        {number(issue.count)} documents need attention.
      </Body>
      {(issue.count_newly !== undefined || issue.count_preexisting !== undefined) && (
        <div className="drift-breakdown" aria-label="New versus pre-existing issues">
          <span><strong>{number(issue.count_newly)}</strong> newly affected</span>
          <span><strong>{number(issue.count_preexisting)}</strong> already failing</span>
        </div>
      )}
      {issue.explanations.map((explanation) => (
        <Body className="issue-explanation" key={explanation}>{explanation}</Body>
      ))}
      {issue.distinctValues.length > 0 && (
        <div className="bad-values" aria-label="Observed values">
          <h3>Observed values</h3>
          {issue.distinctValues.map((item, index) => (
            <div className="bad-value-row" key={`${item.bson_type}-${JSON.stringify(item.value)}-${index}`}>
              <code>{JSON.stringify(item.value)}</code>
              <span>{number(item.count)} docs</span>
              {item.suggestions?.map((suggestion) => (
                <span className="suggestion-chip" key={`${suggestion.target}-${suggestion.source}`}>
                  Suggested: <code>{suggestion.target}</code>
                  <span>{Math.round(suggestion.score * 100)}% · {suggestion.source}</span>
                </span>
              ))}
            </div>
          ))}
          {issue.parts.some((part) => part.distinct_values_limited) && (
            <Body className="inspection-note">Additional values are omitted by the scan limit.</Body>
          )}
        </div>
      )}
      {examples.length > 0 && examples.length < issue.count && (
        <Body className="inspection-note">
          Showing {number(examples.length)} examples.
        </Body>
      )}
      <div className="document-list">
        {examples.map(({ document, reason }, index) => (
          <Card
            as="article"
            className="document-card"
            key={`${reason}-${index}`}
          >
            <div className="document-status">
              {reasonLabels[reason] || "Schema mismatch"}
            </div>
            <dl className="document-fields">
              {Object.entries(document).map(([key, value]) => (
                <div
                  className={
                    key === issue.field
                      ? "document-field affected"
                      : "document-field"
                  }
                  key={key}
                >
                  <dt>{key}:</dt>
                  <dd
                    className={
                      typeof value === "string"
                        ? "document-string"
                        : "document-value"
                    }
                  >
                    {JSON.stringify(value, null, 2)}
                  </dd>
                </div>
              ))}
              {!(issue.field in document) && (
                <div className="document-field affected">
                  <dt>{issue.field}:</dt>
                  <dd className="document-missing">Missing from document</dd>
                </div>
              )}
            </dl>
          </Card>
        ))}
      </div>
      {!examples.length && <Body>No examples available.</Body>}
    </div>
  );
}
