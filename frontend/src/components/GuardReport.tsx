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
