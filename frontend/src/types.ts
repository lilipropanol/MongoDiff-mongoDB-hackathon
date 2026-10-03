export type Source = 'demo' | 'atlas';
export type Tab = 'impact' | 'changes' | 'fixes' | 'validator' | 'history';
export interface Rule { bsonType?: string | string[]; enum?: unknown[]; required?: string[]; properties?: Record<string, Rule>; items?: Rule; }
export interface Change { field: string; kind: string; old?: Rule; new?: Rule; required?: boolean; }
export interface Reason { field: string; reason: string; count: number; example_ids: string[]; examples: Record<string, unknown>[]; }
export interface Report {
  id: string; run_at: string; source: Source; database: string; collection: string;
  total_docs: number; failing: number; preexisting: number; newly_failing: number; unclassified: number;
  changes: Change[]; reasons: Reason[]; old_schema: Rule; new_schema: Rule;
  new_validator: { $jsonSchema: Rule }; model_sources?: { old: string; new: string }; notes: string[];
}
export interface Operation { field: string; kind: string; description: string; count: number | null; filter: unknown; update: unknown; }
export interface Plan {
  id: string; run_id: string; operations: Operation[];
  unresolved: { field: string; reason: string; count: number; message: string }[];
  script: string; notes: string[]; live_execution_available: boolean;
}
export interface Config { atlas_configured: boolean; database: string; collection: string; live_apply_available: boolean; }
