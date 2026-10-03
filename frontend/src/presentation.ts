import type { Operation, Plan, Reason, Report, Rule } from "./types";

export function modelName(report: Report) {
  if (report.source === "demo") return "Movie";
  const classes = [
    ...(report.model_sources?.new || "").matchAll(/^class\s+(\w+)\s*\(/gm),
  ];
  return classes.length === 1 ? classes[0][1] : "Configured model";
}

export function ruleLabel(rule?: Rule) {
  if (!rule) return "Schema rule";
  if (rule.enum)
    return `Literal[${rule.enum.map((value) => JSON.stringify(value)).join(", ")}]`;
  const types = Array.isArray(rule.bsonType) ? rule.bsonType : [rule.bsonType];
  if (types.includes("int") && types.includes("long")) return "int";
  return types.filter(Boolean).join(" | ") || "object";
}

export interface Issue extends Reason {
  label: string;
  action: string;
  variant: "yellow" | "blue" | "red";
  parts: Reason[];
}

function combine(
  parts: Reason[],
  label: string,
  action: string,
  variant: Issue["variant"],
): Issue {
  const examples = new Map(
    parts.flatMap((part) =>
      part.examples.map((example) => [String(example._id), example] as const),
    ),
  );
  return {
    field: parts[0].field,
    reason: parts.map((part) => part.reason).join(" / "),
    count: parts.reduce((total, part) => total + part.count, 0),
    example_ids: [...new Set(parts.flatMap((part) => part.example_ids))],
    examples: [...examples.values()],
    label,
    action,
    variant,
    parts,
  };
}

/** Only combine mutually exclusive reasons for the same field. */
export function summarizeIssues(report: Report): Issue[] {
  const fields = [...new Set(report.reasons.map((reason) => reason.field))];
  const issues: Issue[] = [];
  for (const field of fields) {
    const rule = report.new_schema.properties?.[field];
    const reasons = report.reasons.filter((reason) => reason.field === field);
    const absent = reasons.filter((reason) =>
      ["missing", "null_not_allowed"].includes(reason.reason),
    );
    const values = reasons.filter(
      (reason) => reason.reason === "value_not_allowed",
    );
    if (rule?.enum && values.length) {
      // Enum failures explicitly exclude missing/null, so these counts are disjoint.
      issues.push(
        combine(
          [...absent, ...values],
          absent.length ? "Missing or invalid value" : "Value not allowed",
          report.source === "demo" && field === "rated"
            ? 'Set "PG" & map ratings'
            : "Review allowed values",
          "yellow",
        ),
      );
    } else if (absent.length) {
      const label =
        absent.length === 2
          ? "Missing or empty value"
          : absent[0].reason === "missing"
            ? "Missing required field"
            : "Null is not allowed";
      const demoDefault =
        report.source === "demo"
          ? field === "runtime"
            ? "90"
            : field === "rated"
              ? '"PG"'
              : null
          : null;
      issues.push(
        combine(
          absent,
          label,
          demoDefault ? `Set default: ${demoDefault}` : "Choose a default",
          "yellow",
        ),
      );
    }
    for (const reason of reasons.filter(
      (reason) =>
        !["missing", "null_not_allowed", "value_not_allowed"].includes(
          reason.reason,
        ),
    )) {
      const numeric =
        Array.isArray(rule?.bsonType) &&
        rule.bsonType.includes("int") &&
        rule.bsonType.includes("long");
      const allStrings =
        reason.count === reason.examples.length &&
        reason.examples.every((example) => typeof example[field] === "string");
      const label =
        reason.reason === "wrong_type"
          ? allStrings
            ? "Stored as text"
            : "Stored type does not match"
          : "Nested rule mismatch";
      issues.push(
        combine(
          [reason],
          label,
          numeric && reason.reason === "wrong_type"
            ? "Convert via $convert"
            : "Review values",
          numeric ? "blue" : "red",
        ),
      );
    }
    // Preserve enum-like reasons from future schemas even when no enum metadata is returned.
    if (!rule?.enum && values.length)
      issues.push(combine(values, "Value not allowed", "Review values", "red"));
  }
  return issues.sort((a, b) => {
    const rank = (issue: Issue) =>
      report.new_schema.properties?.[issue.field]?.enum
        ? 0
        : issue.parts[0].reason === "wrong_type"
          ? 1
          : 2;
    return rank(a) - rank(b) || a.field.localeCompare(b.field);
  });
}

/** These explicit example choices are visible in the script before confirmation. */
export function demoDecisions(report: Report): {
  defaults: Record<string, unknown>;
  mappings: Record<string, Record<string, unknown>>;
} {
  if (report.source !== "demo" || report.failing === 0)
    return { defaults: {}, mappings: {} };
  return {
    defaults: { rated: "PG", runtime: 90 },
    mappings: { rated: { PG13: "PG-13", NR: "PG" }, runtime: { "N/A": 90 } },
  };
}

function literal(value: unknown, depth = 0): string {
  const key = (name: string) =>
    name === "__proto__"
      ? `[${JSON.stringify(name)}]`
      : /^[A-Za-z_$][\w$]*$/.test(name)
        ? name
        : JSON.stringify(name);
  if (value === null || typeof value !== "object")
    return JSON.stringify(value) ?? "null";
  const array = Array.isArray(value);
  const entries = array
    ? value.map((item) => literal(item, depth + 1))
    : Object.entries(value).map(
        ([name, item]) => `${key(name)}: ${literal(item, depth + 1)}`,
      );
  const open = array ? "[" : "{",
    close = array ? "]" : "}";
  if (!entries.length) return open + close;
  const inline = `${open} ${entries.join(", ")} ${close}`;
  if (!inline.includes("\n") && inline.length + depth * 2 <= 100) return inline;
  return `${open}\n${entries.map((entry) => `${"  ".repeat(depth + 1)}${entry}`).join(",\n")}\n${"  ".repeat(depth)}${close}`;
}

/** Render the reviewed operations verbatim, with readable JavaScript formatting. */
export function repairScript(report: Report, plan: Plan) {
  if (!plan.operations.length) return "// No repairs needed.";
  const lines = [
    "// Generated MongoDB Update Pipeline",
    `const targetDb = db.getSiblingDB(${JSON.stringify(report.database)});`,
    `const movies = targetDb.getCollection(${JSON.stringify(report.collection)});`,
    "",
  ];
  const titles: Record<Operation["kind"], string> = {
    default: "Set required defaults",
    convert: "Convert string runtimes; preserve failed conversions",
    mapping: "Map remaining values",
  };
  const seen = new Set<string>();
  for (const op of plan.operations) {
    if (!seen.has(op.kind)) {
      lines.push(`// ${titles[op.kind] || op.description}`);
      seen.add(op.kind);
    }
    const filter = literal(op.filter, 1),
      update = literal(op.update, 1);
    const inline = `movies.updateMany(${filter}, ${update});`;
    lines.push(
      !inline.includes("\n") && inline.length <= 110
        ? inline
        : `movies.updateMany(\n  ${filter},\n  ${update}\n);`,
    );
  }
  return lines.join("\n");
}
