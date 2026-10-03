import Button from "@leafygreen-ui/button";
import Icon from "@leafygreen-ui/icon";
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
      <Button size="small" onClick={openValidator}>
        View validator
      </Button>
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
    <section
      className="surface root-cause-panel"
      aria-labelledby="root-cause-title"
    >
      <div className="surface-heading">
        <div>
          <h2 id="root-cause-title">Document issues</h2>
        </div>
      </div>
      <Table
        className="cause-table"
        aria-labelledby="root-cause-title"
        baseFontSize={13}
        verticalAlignment="middle"
      >
        <TableHead>
          <HeaderRow>
            <HeaderCell>Field</HeaderCell>
            <HeaderCell>Issue</HeaderCell>
            <HeaderCell className="count-column" align="right">
              Documents
            </HeaderCell>
            <HeaderCell>
              <span className="sr-only">Details</span>
            </HeaderCell>
          </HeaderRow>
        </TableHead>
        <TableBody>
          {issues.map((issue) => (
            <Row key={`${issue.field}-${issue.reason}`}>
              <Cell>
                <code className="field-name">{issue.field}</code>
              </Cell>
              <Cell>{issue.label}</Cell>
              <Cell className="count-column" align="right">
                <strong>{number(issue.count)}</strong>
              </Cell>
              <Cell align="right">
                <Button
                  size="xsmall"
                  onClick={() => inspect(issue)}
                  aria-label={`Details for ${issue.field}: ${issue.label}`}
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
      {report.unclassified > 0 && (
        <div className="table-empty">
          {number(report.unclassified)} documents need further review.
        </div>
      )}
    </section>
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
  return (
    <div className="reason-details">
      <p>
        {issue.label} · {number(issue.count)} documents
      </p>
      {issue.parts.map((part) => (
        <section key={part.reason}>
          <h3>
            {reasonLabels[part.reason] || part.reason} · {number(part.count)}
          </h3>
          {part.examples.map((example, i) => (
            <div className="document-example" key={`${part.reason}-${i}`}>
              <div className="example-heading">
                <Icon aria-hidden glyph="Folder" />
                Example {i + 1}
              </div>
              {Object.entries(example).map(([key, value]) => (
                <div
                  className={key === issue.field ? "affected-field" : ""}
                  key={key}
                >
                  <code>{key}</code>
                  <pre>{JSON.stringify(value, null, 2)}</pre>
                </div>
              ))}
              {!(issue.field in example) && (
                <div className="affected-field">
                  <code>{issue.field}</code>
                  <em>Missing from document</em>
                </div>
              )}
            </div>
          ))}
          {!part.examples.length && <p>No examples available.</p>}
        </section>
      ))}
    </div>
  );
}
