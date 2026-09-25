import type { ApproachId, ApproachResponse, Rate, Status } from "./types";

export const APPROACH_LABELS: Record<ApproachId, string> = {
  search: "Search",
  basic_rag: "Basic RAG",
  guarded_rag: "Guarded RAG",
};
export const APPROACHES: ApproachId[] = ["search", "basic_rag", "guarded_rag"];

export function isApproachId(value: string | null | undefined): value is ApproachId {
  return APPROACHES.includes(value as ApproachId);
}

export const LABEL_COPY: Record<string, string> = {
  correct: "Correct",
  partially_correct: "Partially correct",
  incorrect: "Incorrect",
};

/** CSS tone for a graded row: the backend decides success; "partial" is shown as amber. */
export function outcomeTone(succeeded: boolean, outcome: string): "good" | "mid" | "bad" {
  if (succeeded) return "good";
  return outcome === "partial" ? "mid" : "bad";
}

export const CATEGORY_LABELS: Record<string, string> = {
  single_document: "Single document",
  multi_document: "Multiple documents",
  outdated_policy: "Outdated / changed policy",
  unanswerable: "Unanswerable",
  role_access: "Role-based access",
};

export const OUTCOME_LABELS: Record<string, string> = {
  correct: "Correct",
  partial: "Partially correct",
  incorrect: "Incorrect",
  unnecessary_abstention: "Abstained when it should answer",
  correct_abstention: "Correctly abstained",
  invented_answer: "Invented an answer",
  safe_decline: "Declined safely",
  answered_without_access: "Answered restricted question",
  disclosure: "Disclosed restricted content",
  error: "Error",
};

export const STATUS_COPY: Record<Status, { label: string; tone: string }> = {
  answered: { label: "Answered", tone: "ok" },
  abstained: { label: "No supported answer", tone: "neutral" },
  access_denied: { label: "Restricted", tone: "warn" },
  error: { label: "Couldn't answer", tone: "bad" },
};

/** Plain-language explanation of a non-answer, for employees rather than engineers. */
export function explainStatus(r: Pick<ApproachResponse, "status" | "error" | "guard_reason">): string | null {
  if (r.status === "abstained") {
    return "The assistant didn't find enough in the policies your role can see to answer confidently, so it didn't guess. The topic may not be covered, or it may be in a policy you don't have access to.";
  }
  if (r.status === "access_denied") {
    return "This information is in a policy your role can't view. Ask the policy owner if you need it.";
  }
  if (r.status === "error") {
    const kind = (r.error ?? "").split(":")[0];
    const map: Record<string, string> = {
      timeout: "The AI model took too long to respond. Nothing was shown so you don't get a partial answer.",
      citation_validation_failed: "An answer was generated but withheld, because a source it cited could not be verified against the policies you can see.",
      unparseable_output: "The AI model's reply was not in the expected format, so it was not shown.",
      fixture_missing: "Demo mode only has saved answers for the sample questions. Add an API key to ask anything.",
      rate_limited: "The AI provider is busy. Try again in a minute.",
      auth: "The AI provider rejected the configured API key.",
    };
    return map[kind] ?? "Something went wrong while generating this answer.";
  }
  return null;
}

export const pct = (v: number | null | undefined, digits = 0) =>
  v === null || v === undefined ? "—" : `${(v * 100).toFixed(digits)}%`;

export function rateText(r: Rate | undefined): string {
  if (!r || r.denominator === 0) return "n = 0";
  return `${pct(r.value, 1)} (${r.numerator}/${r.denominator})`;
}

export function msText(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  if (ms < 1) return "<1 ms";
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)} s` : `${Math.round(ms)} ms`;
}

export function usdText(v: number | null | undefined): string {
  if (v === null || v === undefined) return "unavailable";
  if (v === 0) return "$0";
  if (v < 0.01) return `$${v.toFixed(4)}`;
  return `$${v.toFixed(3)}`;
}

/** Latency / cost line for a single response. Never shows fixture values as measurements. */
export function measurementText(r: ApproachResponse): { latency: string; cost: string } {
  if (r.fixture) return { latency: "not measured (demo)", cost: "unavailable (demo)" };
  const latency = r.latency_ms === null ? "not measured" : msText(r.latency_ms);
  let cost = usdText(r.estimated_cost_usd);
  if (r.estimated_cost_usd === 0 && r.approach === "search") cost = "$0 (no model)";
  else if (r.estimated_cost_usd === 0) cost = "$0 (no model call)";
  return { latency, cost };
}

export type AnswerSegment = { kind: "text"; text: string } | { kind: "cite"; raw: string; ids: string[] };

/** Split an answer into text and [CITATION] segments. */
export function segmentAnswer(answer: string): AnswerSegment[] {
  const out: AnswerSegment[] = [];
  const re = /\[([^[\]]{2,200})\]/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(answer))) {
    const ids = m[1].split(/[,;]/).map((s) => s.trim()).filter((s) => /^[A-Z]{2,}(-[A-Z0-9]+)+(#\d+)?$/.test(s));
    if (!ids.length) continue;
    if (m.index > last) out.push({ kind: "text", text: answer.slice(last, m.index) });
    out.push({ kind: "cite", raw: m[0], ids });
    last = m.index + m[0].length;
  }
  if (last < answer.length) out.push({ kind: "text", text: answer.slice(last) });
  return out;
}

export const REASON_COPY: Record<string, string> = {
  unknown_document: "cites a document that does not exist",
  unknown_passage: "cites a section that does not exist",
  unauthorized: "cites a document your role can't view",
  superseded: "cites a superseded policy",
  not_in_context: "cites a passage the assistant was not given",
  unavailable: "cites a document that does not exist or that your role can't view",
};
