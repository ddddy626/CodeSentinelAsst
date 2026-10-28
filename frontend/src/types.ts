export type Evidence = {
  origin: "tool" | "llm" | "source";
  source: string;
  detail: string;
};

export type Finding = {
  id: string;
  rule_id: string;
  title: string;
  explanation: string;
  line: number;
  filename?: string | null;
  severity: "S0" | "S1" | "S2" | "S3";
  evidence_level: "strong" | "medium" | "weak";
  disposition: "must_fix" | "suggested" | "uncertain";
  evidence: Evidence[];
  suggestion: string;
  trigger_path?: string | null;
  verification?: {
    status: "tool_reported" | "located" | "corroborated";
    reason: string;
  } | null;
};

export type ReviewReport = {
  id: string;
  filename: string;
  language: string;
  created_at: string;
  decision: "request_changes" | "comment" | "pass";
  findings: Finding[];
  knowledge_refs?: { id: string; title: string; provenance: "github" | "authored"; source_url: string | null }[];
  coverage: { completed: string[]; gaps: string[] };
  rule_version: string;
  source_hash?: string | null;
  model_version?: string | null;
  build_version?: string;
  context_ranges?: [number, number][];
  omitted_ranges?: [number, number][];
  context_chars?: number | null;
};

export type Project = { id: string; owner_id: string; name: string };
export type ProjectFile = { path: string; source: string; language: string };
export type FindingFeedback = { finding_id: string; status: "confirmed" | "false_positive" | "accepted_risk"; note: string; updated_at: string };
export type ReviewJob = {
  id: string;
  project_id: string;
  filename: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  created_at: string;
  updated_at: string;
  review_round: number;
  error: string | null;
  source_hash: string;
  report: ReviewReport | null;
  score: { value: number; deduction: number; counted_findings: number; pending_findings: number; version: string } | null;
};
export type ProgressEvent = { seq: number; kind: string; detail: string; created_at: string };
