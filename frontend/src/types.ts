export type Source = "demo" | "atlas";
export interface Rule {
  bsonType?: string | string[];
  enum?: unknown[];
  required?: string[];
  properties?: Record<string, Rule>;
  items?: Rule;
}
export interface Suggestion {
  target: string;
  score: number;
  source: string;
}
export interface RenameSuggestion {
  to: string;
  score: number;
  source: string;
}
export interface DistinctValue {
  value: unknown;
  bson_type: string;
  count: number;
  mappable?: boolean;
  truncated?: boolean;
  suggestions?: Suggestion[];
}
export interface Reason {
  field: string;
  path?: string;
  location?: "field" | "nested" | "array_element";
  reason: string;
  count: number;
  count_newly?: number;
  count_preexisting?: number;
  explanation?: string;
  distinct_values?: DistinctValue[];
  distinct_value_count?: number;
  distinct_values_limited?: boolean;
  example_ids: string[];
  examples: Record<string, unknown>[];
}
export interface Change {
  field: string;
  parent?: string | null;
  kind: string;
  old?: Rule;
  new?: Rule;
  required?: boolean;
  details?: Record<string, unknown>;
  compatibility?: "breaking" | "compatible";
  compatibility_reason?: string;
  rename_candidates?: RenameSuggestion[];
}
export interface ScanSuggestions {
  provider?: string;
  model?: string | null;
  method?: string;
  status: "ok" | "fallback" | "disabled";
  fallback_reason?: string | null;
  semantic_jobs?: { scored: number; total: number };
}
export interface Warning {
  field: string;
  path: string;
  kind: string;
  count: number;
  message: string;
}
export interface VersionRow {
  version: unknown;
  total: number;
  failing: number;
  newly_failing: number;
}
export interface Versioning {
  field: string;
  versioned: boolean;
  versions: VersionRow[];
  bump_recommended: boolean;
  breaking_changes: string[];
  message: string;
}
export interface Report {
  id: string;
  run_at: string;
  source: Source;
  database: string;
  collection: string;
  total_docs: number;
  failing: number;
  preexisting: number;
  newly_failing: number;
  unclassified: number;
  changes: Change[];
  reasons: Reason[];
  warnings?: Warning[];
  scan?: {
    duration_ms?: number;
    max_time_ms?: number;
    examples?: number;
    distinct_limit?: number;
    two_pass?: boolean;
    collection_exists?: boolean | null;
    snapshot?: boolean;
    suggestions?: ScanSuggestions;
  };
  versioning?: Versioning;
  old_schema: Rule;
  new_schema: Rule;
  new_validator: { $jsonSchema: Rule };
  model_sources?: { old: string; new: string };
  notes: string[];
}
export interface Operation {
  field: string;
  kind: string;
  description: string;
  count: number | null;
  filter: unknown;
  update: unknown;
}
export interface Plan {
  id: string;
  run_id: string;
  operations: Operation[];
  unresolved: { field: string; reason: string; count: number; message: string }[];
  script: string;
  notes: string[];
  live_execution_available: boolean;
}
export interface Config {
  atlas_configured: boolean;
  database: string;
  collection: string;
  live_apply_available: boolean;
  suggestions_configured?: boolean;
  suggestion_mode?: string | null;
  suggestion_key_configured?: boolean;
}
