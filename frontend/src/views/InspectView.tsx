import { useState } from "react";
import { api } from "../api";
import { AnswerCard } from "../components/AnswerCard";
import { ErrorNotice, Loading } from "../components/Notice";
import {
  APPROACHES,
  APPROACH_LABELS,
  CATEGORY_LABELS,
  LABEL_COPY,
  OUTCOME_LABELS,
  isApproachId,
  outcomeTone,
} from "../format";
import { href, navigate, type Route } from "../router";
import type { ApproachId, CaseDetail, CaseRow } from "../types";
import { useAsync } from "../useAsync";
import { defaultRunId, RunPicker, useRuns } from "./RunPicker";

const SOURCE_COPY: Record<string, string> = { human: "human review", model_judge: "model-judged", deterministic: "deterministic" };
const FILTER_KEYS = ["split", "category", "approach", "outcome", "error_type"] as const;
type Params = Record<string, string | undefined>;

function matches(row: CaseRow, filters: Params): boolean {
  return FILTER_KEYS.every((k) => !filters[k] || row[k] === filters[k]);
}

/** Filter options plus the current value, so a deep-linked filter with no matches still shows what is applied. */
function withCurrent(options: string[], current: string | undefined): string[] {
  return current && !options.includes(current) ? [...options, current] : options;
}

export function InspectView({ route }: { route: Route }) {
  const runs = useRuns();
  const params: Params = Object.fromEntries(route.params.entries());
  const runId = params.run ?? defaultRunId(runs.data ?? []);
  const caseId = params.case ?? null;
  const focus = isApproachId(params.focus) ? params.focus : null;

  // Every link and control keeps all current parameters and changes only what it names.
  const link = (patch: Params) => href("inspect", { ...params, run: runId ?? undefined, ...patch });
  const set = (patch: Params) => navigate("inspect", { ...params, run: runId ?? undefined, ...patch });

  const rows = useAsync(runId, () => api.cases(runId!, {}));
  const detail = useAsync(runId && caseId ? `${runId}:${caseId}` : null, () => api.caseDetail(runId!, caseId!));
  const visible = (rows.data ?? []).filter((r) => matches(r, params));
  const uniq = (k: keyof CaseRow) => [...new Set((rows.data ?? []).map((r) => r[k]).filter(Boolean) as string[])].sort();
  const options = { outcome: uniq("outcome"), error_type: uniq("error_type") };
  const run = runs.data?.find((r) => r.run_id === runId);

  return (
    <div className="view">
      <div className="toolbar">
        <RunPicker runs={runs.data ?? []} value={runId} onChange={(id) => navigate("inspect", { run: id })} />
      </div>
      {runs.error && <ErrorNotice error={runs.error} onRetry={runs.reload} />}
      {run?.mode === "fixture" && (
        <div className="notice notice-demo">
          <strong>Fixture data.</strong> AI answers in this run are saved examples, some deliberately showing failure modes. No model judge ran.
        </div>
      )}
      <div className="filters">
        <Select label="Split" value={params.split} onChange={(v) => set({ split: v })} options={[["development", "Development"], ["held_out", "Held-out"]]} />
        <Select label="Category" value={params.category} onChange={(v) => set({ category: v })} options={Object.entries(CATEGORY_LABELS)} />
        <Select label="Approach" value={params.approach} onChange={(v) => set({ approach: v })} options={APPROACHES.map((a) => [a, APPROACH_LABELS[a]])} />
        <Select label="Outcome" value={params.outcome} onChange={(v) => set({ outcome: v })} options={withCurrent(options.outcome, params.outcome).map((o) => [o, OUTCOME_LABELS[o] ?? o])} />
        <Select label="Error type" value={params.error_type} onChange={(v) => set({ error_type: v })} options={withCurrent(options.error_type, params.error_type).map((o) => [o, o])} />
        <span className="muted small filter-count" role="status">
          {visible.length} responses
        </span>
      </div>

      <div className="inspect-layout">
        <section className="panel case-list" aria-label="Evaluated responses">
          {rows.error && <ErrorNotice error={rows.error} onRetry={rows.reload} />}
          {rows.loading && !rows.data && <Loading />}
          <table className="cases-table">
            <thead>
              <tr>
                <th scope="col">Case</th>
                <th scope="col">Approach</th>
                <th scope="col">Question</th>
                <th scope="col">Outcome</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((r) => {
                const selected = r.case_id === caseId && (!focus || focus === r.approach);
                return (
                  <tr key={r.response_id} className={selected ? "selected" : ""} onClick={() => set({ case: r.case_id, focus: r.approach })}>
                    <td className="mono">
                      <a href={link({ case: r.case_id, focus: r.approach })} aria-current={selected ? "true" : undefined}>
                        {r.case_id}
                      </a>
                    </td>
                    <td>{APPROACH_LABELS[r.approach]}</td>
                    <td className="q-cell">
                      {r.question}
                      {r.role !== "employee" && <span className="role-tag">{r.role}</span>}
                    </td>
                    <td>
                      <span className={`outcome outcome-${outcomeTone(r.succeeded, r.outcome)}`}>{OUTCOME_LABELS[r.outcome] ?? r.outcome}</span>
                      {r.reviewed && <span className="badge badge-info tiny">reviewed</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {rows.data && !visible.length && <p className="muted pad">No responses match these filters.</p>}
        </section>

        <section className="panel case-detail" aria-label="Case detail">
          {!caseId && <p className="muted pad">Select a case to see the question, reference facts, each approach's answer, grading and reviews.</p>}
          {detail.error && <ErrorNotice error={detail.error} onRetry={detail.reload} />}
          {detail.loading && !detail.data && <Loading />}
          {detail.data && (
            <CaseDetailPanel
              detail={detail.data}
              focus={focus}
              onFocus={(a) => set({ focus: a })}
              isFixture={run?.mode === "fixture"}
              onReviewed={() => {
                // Same selection, fresh data: reload keeps the current rows on screen meanwhile.
                rows.reload();
                detail.reload();
              }}
            />
          )}
        </section>
      </div>
    </div>
  );
}

function Select({ label, value, onChange, options }: { label: string; value?: string; onChange: (v?: string) => void; options: [string, string][] }) {
  return (
    <label className="inline-field">
      <span className="field-label">{label}</span>
      <select value={value ?? ""} onChange={(e) => onChange(e.target.value || undefined)}>
        <option value="">All</option>
        {options.map(([k, v]) => (
          <option key={k} value={k}>
            {v}
          </option>
        ))}
      </select>
    </label>
  );
}

function CaseDetailPanel({
  detail,
  focus,
  onFocus,
  isFixture,
  onReviewed,
}: {
  detail: CaseDetail;
  focus: ApproachId | null;
  onFocus: (a: ApproachId) => void;
  isFixture: boolean;
  onReviewed: () => void;
}) {
  const c = detail.case;
  const row = detail.responses.find((r) => r.approach === focus) ?? detail.responses[0];
  const g = row.grade;

  return (
    <div className="detail">
      <p className="eyebrow">
        {c.case_id} · {CATEGORY_LABELS[c.category]} · {c.split === "held_out" ? "held-out" : "development"} · asked as <strong>{c.user_role}</strong>
      </p>
      <h2 className="detail-q">{c.question}</h2>
      <div className="reference">
        <h3 className="h4">Expected behavior</h3>
        <p>
          <span className="badge badge-neutral">{c.answerability.replace("_", " ")}</span> {c.reference_answer}
        </p>
        {c.required_facts.length > 0 && (
          <ul className="facts">
            {c.required_facts.map((f, i) => {
              const hit = g.facts[i];
              return (
                <li key={f.description} className={hit?.found ? "fact-hit" : "fact-miss"}>
                  <span aria-hidden="true">{hit?.found ? "✓" : "✕"}</span> {f.description}
                  <span className="muted small"> {hit?.found ? `matched “${hit.matched}”` : "not found"}</span>
                </li>
              );
            })}
          </ul>
        )}
        <p className="muted small">
          Acceptable sources: <span className="mono">{c.acceptable_document_ids.join(", ") || "none"}</span>
          {c.forbidden_document_ids.length > 0 && (
            <>
              {" "}
              · must not cite: <span className="mono">{c.forbidden_document_ids.join(", ")}</span>
            </>
          )}
        </p>
        {c.notes && <p className="muted small">Note: {c.notes}</p>}
      </div>

      <div className="tabs" role="group" aria-label="Approach">
        {detail.responses.map((r) => {
          const tone = outcomeTone(r.succeeded, r.grade.outcome);
          return (
            <button key={r.approach} type="button" aria-pressed={r.approach === row.approach} className={`tab ${r.approach === row.approach ? "tab-active" : ""}`} onClick={() => onFocus(r.approach)}>
              {APPROACH_LABELS[r.approach]}
              <span className={`dot dot-${tone}`} aria-hidden="true" />
              <span className="sr-only">({OUTCOME_LABELS[r.grade.outcome] ?? r.grade.outcome})</span>
            </button>
          );
        })}
      </div>

      <AnswerCard response={row.response} role={c.user_role} />

      <div className="grade-grid">
        <div>
          <h3 className="h4">Automated grade</h3>
          <dl className="meta-grid">
            <dt>Outcome</dt>
            <dd>{OUTCOME_LABELS[g.outcome] ?? g.outcome}</dd>
            {g.deterministic_label && (
              <>
                <dt>Fact match</dt>
                <dd>
                  {LABEL_COPY[g.deterministic_label]} ({g.facts_found}/{g.facts_total} facts)
                </dd>
              </>
            )}
            {g.citation_check && (
              <>
                <dt>Citations</dt>
                <dd>
                  {g.citation_check.structurally_valid ? "valid" : "invalid"} ·{" "}
                  {g.citation_check.supports_deterministic ? "from an acceptable source" : "not from an acceptable source"}
                </dd>
              </>
            )}
            <dt>Disclosures</dt>
            <dd className={g.disclosures.length ? "bad-text" : ""}>
              {g.disclosures.length ? g.disclosures.map((d) => `${d.type}: ${d.type === "fact" ? d.value : d.document_id}`).join("; ") : "none"}
            </dd>
            {row.response.guard_reason && (
              <>
                <dt>Guard reason</dt>
                <dd className="mono small">{row.response.guard_reason}</dd>
              </>
            )}
            {row.response.error && (
              <>
                <dt>Error</dt>
                <dd className="mono small bad-text">{row.response.error}</dd>
              </>
            )}
            <dt>Final label</dt>
            <dd>{row.final_label ? `${LABEL_COPY[row.final_label]} (${SOURCE_COPY[row.final_label_source]})` : "n/a (not an answerable case)"}</dd>
          </dl>
        </div>
        <div>
          <h3 className="h4">
            Model judge <span className="badge badge-neutral tiny">model-judged</span>
          </h3>
          <JudgeSummary judge={row.judge} isFixture={isFixture} />
        </div>
      </div>

      <details className="retrieval">
        <summary>Retrieved passages ({row.response.retrieved_passages?.length ?? 0}) and raw output</summary>
        <table className="mini-table">
          <tbody>
            {row.response.retrieved_passages?.map((p) => (
              <tr key={p.passage_id}>
                <td className="mono">{p.passage_id}</td>
                <td>{row.retrieved_documents.find((x) => x.document_id === p.document_id)?.title}</td>
                <td className="num">{p.score.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {row.response.raw_output && <pre className="raw">{row.response.raw_output}</pre>}
        <p className="muted small">
          {row.response.approach_version} {row.response.prompt_version ? `· prompt ${row.response.prompt_version}` : ""}{" "}
          {row.response.model ? `· ${row.response.model}` : ""}
          {row.response.input_tokens !== null && ` · ${row.response.input_tokens} in / ${row.response.output_tokens} out tokens`}
        </p>
      </details>

      <ReviewBox key={row.response_id} responseId={row.response_id} reviews={row.reviews} canReview={c.answerability === "answerable"} onReviewed={onReviewed} />
      <p className="small">
        <a href={href("ask", { q: c.question, role: c.user_role })}>Try this question in Ask →</a>
      </p>
    </div>
  );
}

function JudgeSummary({ judge, isFixture }: { judge: CaseDetail["responses"][0]["judge"]; isFixture: boolean }) {
  if (!judge) {
    return <p className="muted small">{isFixture ? "No model judge in fixture mode." : "Not judged (only answered, answerable cases are sent to the judge)."}</p>;
  }
  if (!judge.verdict) return <p className="bad-text small">Judge failed: {judge.error}</p>;
  const support = judge.citations_support === null || judge.citations_support === undefined ? "n/a" : judge.citations_support ? "yes" : "no";
  return (
    <>
      <p>
        <strong>{LABEL_COPY[judge.verdict]}</strong> · citations support the answer: {support}
      </p>
      <p className="muted small">{judge.rationale}</p>
      <p className="muted small mono">{judge.model}</p>
    </>
  );
}

function ReviewBox({
  responseId,
  reviews,
  canReview,
  onReviewed,
}: {
  responseId: string;
  reviews: CaseDetail["responses"][0]["reviews"];
  canReview: boolean;
  onReviewed: () => void;
}) {
  // No default verdict: a review overrides the automated label, so it has to be a deliberate choice.
  const [verdict, setVerdict] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.review(responseId, verdict!, note, reviewer.trim());
      setNote("");
      setVerdict(null);
      onReviewed();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };
  return (
    <div className="review-box">
      <h3 className="h4">Human review</h3>
      {reviews.length > 0 && (
        <ul className="reviews">
          {reviews.map((r) => (
            <li key={r.review_id}>
              <strong>{LABEL_COPY[r.verdict]}</strong>{" "}
              <span className="muted small">
                {r.reviewer ?? "anonymous"} · {r.created_at}
              </span>
              {r.note && <p className="small">{r.note}</p>}
            </li>
          ))}
        </ul>
      )}
      <p className="muted small">
        A review sets the final label for metrics. The automated grade and any model-judge verdict above are kept unchanged.
        {!canReview &&
          " This case isn't scored on correctness, so the verdict you choose is recorded with your note but doesn't change any metric."}
      </p>
      <div className="review-form">
        <div className="radio-row" role="radiogroup" aria-label="Verdict">
          {Object.entries(LABEL_COPY).map(([k, v]) => (
            <label key={k} className="check">
              <input type="radio" name={`verdict-${responseId}`} checked={verdict === k} onChange={() => setVerdict(k)} /> {v}
            </label>
          ))}
        </div>
        <textarea aria-label="Review note" placeholder="Note (what is right or wrong, and why)" value={note} onChange={(e) => setNote(e.target.value)} rows={2} />
        <div className="review-actions">
          <input aria-label="Reviewer name" placeholder="Your name (required)" required value={reviewer} onChange={(e) => setReviewer(e.target.value)} />
          <button className="btn" onClick={save} disabled={saving || !verdict || !reviewer.trim()}>
            {saving ? "Saving…" : "Save review"}
          </button>
        </div>
        {error && <ErrorNotice error={error} />}
      </div>
    </div>
  );
}
