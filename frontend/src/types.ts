export type Status = "answered" | "abstained" | "access_denied" | "error";
export type ApproachId = "search" | "basic_rag" | "guarded_rag";

export interface Citation {
  document_id: string;
  passage_id: string | null;
  title: string | null;
  valid: boolean;
  reason: string | null;
}

export interface ApproachResponse {
  approach: ApproachId;
  answer: string;
  status: Status;
  citations: Citation[];
  retrieved_document_ids: string[];
  latency_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  estimated_cost_usd: number | null;
  error: string | null;
  approach_version?: string;
  prompt_version?: string | null;
  model?: string | null;
  retrieved_passages?: { passage_id: string; document_id: string; score: number }[];
  guard_reason?: string | null;
  warnings?: string[];
  fixture?: boolean;
  raw_output?: string | null;
}

export interface Health {
  mode: "live" | "fixture";
  live_available: boolean;
  provider: string;
  model: string;
  effort: string | null;
  judge_model: string;
  api_key_env_var: string;
}

export interface Role {
  id: string;
  label: string;
  groups: string[];
}

export interface Rate {
  value: number | null;
  numerator: number;
  denominator: number;
  ci_low: number | null;
  ci_high: number | null;
  partial?: number;
  label_sources?: Record<string, number>;
  judge_support_used?: number;
}

export interface Metrics {
  n_cases: number;
  correctness: Rate;
  correctness_deterministic: Rate;
  citation_validity: Rate;
  abstention_quality: Rate;
  access_denied_handling: Rate;
  access_safety: { disclosures: number; cases_with_disclosure: string[]; n_cases: number };
  latency: { n: number; n_unmeasured: number; coverage: number; p50_ms: number | null; p95_ms: number | null };
  cost: {
    /** True when every case has token usage. */
    complete: boolean;
    n_with_usage: number;
    n_missing: number;
    /** Share of cases with known cost (0–1). */
    coverage: number;
    total_usd: number | null;
    /** Average over the cases whose cost is known; null when none are. */
    per_question_usd: number | null;
  };
  tokens: { input_total: number | null; output_total: number | null; n_with_usage: number };
  errors: {
    count: number;
    n: number;
    case_ids: string[];
    /** Provider or runtime failures (timeouts, rate limits, bad output), counted against run validity. */
    provider?: number;
    /** Answers the guard withheld on purpose; not failures of the provider. */
    withheld?: number;
  };
  status_counts: Record<string, number>;
  fixture_rows: number;
}

export interface RunSummary {
  run_id: string;
  created_at: string;
  completed_at: string | null;
  mode: "live" | "fixture";
  status: string;
  label: string | null;
  splits: string[];
  judge_mode: string;
  corpus_version: string;
  dataset_version: string;
  prompt_versions: Record<string, { approach_version?: string; prompt_version: string | null }>;
  model_config: Record<string, string | number | null>;
  n_responses: number;
  /** A run limited to some cases or approaches (a debug run); never used as the default. */
  partial?: boolean;
  /** The live run the backend uses for the decision: the run of record, else the newest full, usable held-out run. */
  latest?: boolean;
  /** The decision run of record. Human reviews of its held-out responses are locked. */
  designated?: boolean;
}

/** Who named a run as the one the decision rests on. The newest designation is the current one. */
export interface Designation {
  designation_id: string;
  run_id: string;
  split: string;
  designated_by: string;
  note: string | null;
  designated_at: string;
}

/** How many live runs have evaluated the held-out split of one dataset version. */
export interface HeldOutUsage {
  dataset_version: string;
  split?: string;
  evaluations: number;
  run_ids: string[];
  /** Runs still marked running that already stored held-out answers (possibly killed mid-run); they count. */
  in_progress_run_ids?: string[];
}

export interface RunDetail extends RunSummary {
  metrics: Record<string, Partial<Record<ApproachId, Metrics>>>;
  config_snapshot: Record<string, unknown>;
}

export interface CaseRow {
  response_id: string;
  case_id: string;
  approach: ApproachId;
  question: string;
  role: string;
  category: string;
  split: string;
  answerability: string;
  status: Status;
  outcome: string;
  error_type: string | null;
  final_label: string | null;
  final_label_source: string;
  deterministic_label: string | null;
  judge_verdict: string | null;
  reviewed: boolean;
  /** Backend verdict: correct (answerable) or declined safely (otherwise). */
  succeeded: boolean;
  disclosures: number;
  latency_ms: number | null;
  fixture: boolean;
}

export interface Fact {
  description: string;
  match_any: string[];
}

export interface EvalCase {
  case_id: string;
  question: string;
  user_role: string;
  category: string;
  split: string;
  answerability: string;
  reference_answer: string;
  required_facts: Fact[];
  acceptable_document_ids: string[];
  forbidden_document_ids: string[];
  forbidden_facts?: string[];
  notes: string;
}

export interface Review {
  review_id: string;
  verdict: string;
  note: string | null;
  reviewer: string | null;
  created_at: string;
}

export interface Grade {
  answerability: string;
  status: Status;
  facts: { description: string; found: boolean; matched: string | null }[];
  facts_found: number;
  facts_total: number;
  forbidden_documents_cited: string[];
  deterministic_label: string | null;
  citation_check: Record<string, boolean> | null;
  abstained_correctly: boolean | null;
  disclosures: { type: string; document_id: string; value: string }[];
  outcome: string;
  error_type: string | null;
}

export interface Judge {
  verdict: string | null;
  citations_support?: boolean | null;
  rationale?: string;
  model?: string;
  error?: string | null;
  label?: string;
}

export interface CaseResponseRow {
  response_id: string;
  approach: ApproachId;
  response: ApproachResponse;
  grade: Grade;
  judge: Judge | null;
  reviews: Review[];
  final_label: string | null;
  final_label_source: string;
  succeeded: boolean;
  retrieved_documents: { document_id: string; title: string | null; status: string | null }[];
}

export interface CaseDetail {
  case: EvalCase;
  responses: CaseResponseRow[];
}

export interface Criterion {
  id: string;
  label: string;
  comparator: string;
  threshold: number;
  unit: "count" | "rate" | "ms" | "usd";
  value: number | null;
  n: number | null;
  numerator?: number;
  ci_low?: number | null;
  ci_high?: number | null;
  state: "pass" | "fail" | "insufficient";
  reason: string | null;
  confidence: "low" | "ok" | null;
  /** "interval": the whole 95% interval must meet the threshold. Absent on older runs, which means "point". */
  evidence?: "point" | "interval";
  /** Minimum evaluated cases for this criterion (per-criterion override of min_sample_size). */
  min_n?: number;
  example_case_ids: string[];
}

export interface Decision {
  run_id: string;
  run_mode: "live" | "fixture";
  run_created_at: string;
  model_config: Record<string, string | number | null>;
  evaluated_split: string;
  n_cases: number;
  criteria_version: string;
  criteria_hash: string;
  criteria_changed_since_run: boolean;
  criteria_registered_on: string;
  correctness_source: string | null;
  target_approach: ApproachId;
  recommendation: { verdict: string; headline: string; summary: string };
  approaches: Partial<
    Record<
      ApproachId,
      {
        label: string;
        criteria: Criterion[];
        passes: number;
        total: number;
        /** Where the correctness labels came from; human labels override the automated grade. */
        label_sources?: { human: number; model_judge: number; deterministic: number } | null;
        /** Human reviews of correctness labels; `changed` counts those that differ from the automated label. */
        human_reviews?: { reviewed: number; changed: number } | null;
      }
    >
  >;
  comparison: {
    target: ApproachId;
    baseline: ApproachId;
    correctness_lift_pp: number | null;
    target_correct: string;
    baseline_correct: string;
    target_p95_ms: number | null;
    baseline_p95_ms: number | null;
    target_cost_per_question: number | null;
    baseline_cost_per_question: number | null;
  } | null;
  next_experiments: { criterion: string; text: string }[];
  rollout_tests: string[];
  limitations: string[];
  /** Set when this run is the current decision run of record; null otherwise. */
  designation?: Designation | null;
  /** Why this run cannot be designated (fixture, partial, no held-out split, error-dominated); null when it can. */
  designation_blocker?: string | null;
  held_out_usage?: HeldOutUsage | null;
  /** Every designation for the decision split, newest first (the audit trail). */
  designation_history?: Designation[];
  /** Set when the designated run fails the designation rules and the newest usable run is used instead. */
  run_of_record_warning?: string | null;
}

export interface DecisionResponse {
  live_available: boolean;
  message?: string;
  decision: Decision | null;
}

export interface DocumentDetail {
  document_id: string;
  title: string;
  owner: string;
  effective_date: string;
  status: string;
  superseded_by: string | null;
  supersedes: string | null;
  access_groups: string[];
  country: string[];
  passages: { passage_id: string; heading: string; text: string }[];
}

export interface CriterionConfig {
  id: string;
  label: string;
  metric: string;
  comparator: "<=" | ">=";
  threshold: number;
  unit: Criterion["unit"];
  evidence?: "point" | "interval";
  min_n?: number;
}

export interface LaunchCriteria {
  version: string;
  registered_on: string;
  evaluated_split: string;
  target_approach: ApproachId;
  baseline_approach: ApproachId;
  min_sample_size: number;
  min_measurement_coverage: number;
  correctness_source: string;
  criteria: CriterionConfig[];
  hash: string;
}

export interface AppConfig {
  settings: Health;
  roles: Role[];
  approaches: { id: ApproachId; label: string }[];
  launch_criteria: LaunchCriteria;
  corpus_version: string;
  dataset_version: string;
}
