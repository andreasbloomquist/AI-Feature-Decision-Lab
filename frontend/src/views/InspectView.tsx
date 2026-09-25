import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { AnswerCard } from "../components/AnswerCard";
import { APPROACHES, APPROACH_LABELS, CATEGORY_LABELS, OUTCOME_LABELS } from "../format";
import { href, navigate, type Route } from "../router";
import type { ApproachId, CaseDetail, CaseRow, RunSummary } from "../types";
import { RunPicker } from "./RunPicker";

const LABEL_COPY: Record<string, string> = { correct: "Correct", partially_correct: "Partially correct", incorrect: "Incorrect" };
const SOURCE_COPY: Record<string, string> = { human: "human review", model_judge: "model-judged", deterministic: "deterministic", "n/a": "" };
const GOOD = new Set(["correct", "correct_abstention", "safe_decline"]);

export function InspectView({ route }: { route: Route }) {
  const p = route.params;
  const filters = {
    split: p.get("split") ?? undefined,
    category: p.get("category") ?? undefined,
    approach: p.get("approach") ?? undefined,
    outcome: p.get("outcome") ?? undefined,
    error_type: p.get("error_type") ?? undefined,
  };
  const runId = p.get("run");
  const caseId = p.get("case");
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [rows, setRows] = useState<CaseRow[]>([]);
  const [allRows, setAllRows] = useState<CaseRow[]>([]);
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [refresh, setRefresh] = useState(0);

  const set = (patch: Record<string, string | undefined>) => {
    const next: Record<string, string | undefined> = { run: runId ?? undefined, ...filters, case: caseId ?? undefined, ...patch };
    navigate("inspect", next);
  };

  useEffect(() => {
    api.runs().then((rs) => {
      setRuns(rs);
      if (!runId && rs.length) set({ run: (rs.find((r) => r.mode === "live") ?? rs[0]).run_id });
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const filterKey = JSON.stringify(filters);
  useEffect(() => {
    if (!runId) return;
    api.cases(runId, filters).then(setRows);
    api.cases(runId, {}).then(setAllRows);
  }, [runId, filterKey, refresh]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (runId && caseId) api.caseDetail(runId, caseId).then(setDetail).catch(() => setDetail(null));
    else setDetail(null);
  }, [runId, caseId, refresh]);

  const options = useMemo(() => {
    const uniq = (k: keyof CaseRow) => [...new Set(allRows.map((r) => r[k]).filter(Boolean) as string[])].sort();
    return { outcome: uniq("outcome"), error_type: uniq("error_type") };
  }, [allRows]);
  const run = runs.find((r) => r.run_id === runId);

  return (
    <div className="view">
      <div className="toolbar">
        <RunPicker runs={runs} value={runId} onChange={(id) => set({ run: id, case: undefined })} />
      </div>
      {run?.mode === "fixture" && (
        <div className="notice notice-demo">
          <strong>Fixture data.</strong> AI answers in this run are saved examples, some deliberately showing failure modes. No model judge ran.
        </div>
      )}
      <div className="filters">
        <Select label="Split" value={filters.split} onChange={(v) => set({ split: v })} options={[["development", "Development"], ["held_out", "Held-out"]]} />
        <Select label="Category" value={filters.category} onChange={(v) => set({ category: v })} options={Object.entries(CATEGORY_LABELS)} />
        <Select label="Approach" value={filters.approach} onChange={(v) => set({ approach: v })} options={APPROACHES.map((a) => [a, APPROACH_LABELS[a]])} />
        <Select label="Outcome" value={filters.outcome} onChange={(v) => set({ outcome: v })} options={options.outcome.map((o) => [o, OUTCOME_LABELS[o] ?? o])} />
        <Select label="Error type" value={filters.error_type} onChange={(v) => set({ error_type: v })} options={options.error_type.map((o) => [o, o])} />
        <span className="muted small filter-count">{rows.length} responses</span>
      </div>

      <div className="inspect-layout">
        <section className="panel case-list">
          <table className="cases-table">
            <thead>
              <tr>
                <th>Case</th>
                <th>Approach</th>
                <th>Question</th>
                <th>Outcome</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={r.response_id}
                  className={r.case_id === caseId ? "selected" : ""}
                  onClick={() => set({ case: r.case_id, focus: r.approach })}
                >
                  <td className="mono">{r.case_id}</td>
                  <td>{APPROACH_LABELS[r.approach]}</td>
                  <td className="q-cell">
                    {r.question}
                    {r.role !== "employee" && <span className="role-tag">{r.role}</span>}
                  </td>
                  <td>
                    <span className={`outcome ${GOOD.has(r.outcome) ? "outcome-good" : r.outcome === "partial" ? "outcome-mid" : "outcome-bad"}`}>
                      {OUTCOME_LABELS[r.outcome] ?? r.outcome}
                    </span>
                    {r.reviewed && <span className="badge badge-info tiny">reviewed</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!rows.length && <p className="muted pad">No responses match these filters.</p>}
        </section>

        <section className="panel case-detail">
          {!detail && <p className="muted pad">Select a case to see the question, reference facts, each approach's answer, grading and reviews.</p>}
          {detail && <CaseDetailPanel detail={detail} focus={(p.get("focus") as ApproachId) ?? null} isFixture={run?.mode === "fixture"} onReviewed={() => setRefresh((n) => n + 1)} />}
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
          <option key={k} value={k}>{v}</option>
        ))}
      </select>
    </label>
  );
}

function CaseDetailPanel({ detail, focus, isFixture, onReviewed }: { detail: CaseDetail; focus: ApproachId | null; isFixture: boolean; onReviewed: () => void }) {
  const c = detail.case;
  const [tab, setTab] = useState<ApproachId>(focus ?? detail.responses[0].approach);
  useEffect(() => setTab(focus ?? detail.responses[0].approach), [c.case_id, focus]); // eslint-disable-line react-hooks/exhaustive-deps
  const row = detail.responses.find((r) => r.approach === tab) ?? detail.responses[0];
  const g = row.grade;

  return (
    <div className="detail">
      <p className="eyebrow">
        {c.case_id} · {CATEGORY_LABELS[c.category]} · {c.split === "held_out" ? "held-out" : "development"} · asked as <strong>{c.user_role}</strong>
      </p>
      <h2 className="detail-q">{c.question}</h2>
      <div className="reference">
        <h4>Expected behavior</h4>
        <p>
          <span className="badge badge-neutral">{c.answerability.replace("_", " ")}</span> {c.reference_answer}
        </p>
        {c.required_facts.length > 0 && (
          <ul className="facts">
            {c.required_facts.map((f, i) => {
              const hit = g.facts[i];
              return (
                <li key={i} className={hit?.found ? "fact-hit" : "fact-miss"}>
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
              {" "}· must not cite: <span className="mono">{c.forbidden_document_ids.join(", ")}</span>
            </>
          )}
        </p>
        {c.notes && <p className="muted small">Note: {c.notes}</p>}
      </div>

      <div className="tabs" role="tablist">
        {detail.responses.map((r) => (
          <button key={r.approach} role="tab" aria-selected={r.approach === tab} className={`tab ${r.approach === tab ? "tab-active" : ""}`} onClick={() => setTab(r.approach)}>
            {APPROACH_LABELS[r.approach]}
            <span className={`dot ${GOOD.has(r.grade.outcome) ? "dot-good" : r.grade.outcome === "partial" ? "dot-mid" : "dot-bad"}`} />
          </button>
        ))}
      </div>

      <AnswerCard response={row.response} role={c.user_role} />

      <div className="grade-grid">
        <div>
          <h4>Automated grade</h4>
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
                  {g.citation_check.structurally_valid ? "valid" : "invalid"} · {g.citation_check.supports_deterministic ? "from an acceptable source" : "not from an acceptable source"}
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
            <dd>
              {row.final_label ? `${LABEL_COPY[row.final_label]} (${SOURCE_COPY[row.final_label_source]})` : "n/a (not an answerable case)"}
            </dd>
          </dl>
        </div>
        <div>
          <h4>
            Model judge <span className="badge badge-neutral tiny">model-judged</span>
          </h4>
          {row.judge ? (
            row.judge.verdict ? (
              <>
                <p>
                  <strong>{LABEL_COPY[row.judge.verdict]}</strong> · citations support the answer:{" "}
                  {row.judge.citations_support === null || row.judge.citations_support === undefined ? "n/a" : row.judge.citations_support ? "yes" : "no"}
                </p>
                <p className="muted small">{row.judge.rationale}</p>
                <p className="muted small mono">{row.judge.model}</p>
              </>
            ) : (
              <p className="bad-text small">Judge failed: {row.judge.error}</p>
            )
          ) : (
            <p className="muted small">{isFixture ? "No model judge in fixture mode." : "Not judged (only answered, answerable cases are sent to the judge)."}</p>
          )}
        </div>
      </div>

      <details className="retrieval">
        <summary>Retrieved passages ({row.response.retrieved_passages?.length ?? 0}) and raw output</summary>
        <table className="mini-table">
          <tbody>
            {row.response.retrieved_passages?.map((p) => {
              const d = row.retrieved_documents.find((x) => x.document_id === p.document_id);
              return (
                <tr key={p.passage_id}>
                  <td className="mono">{p.passage_id}</td>
                  <td>{d?.title}</td>
                  <td className="num">{p.score.toFixed(2)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {row.response.raw_output && <pre className="raw">{row.response.raw_output}</pre>}
        <p className="muted small">
          {row.response.approach_version} {row.response.prompt_version ? `· prompt ${row.response.prompt_version}` : ""} {row.response.model ? `· ${row.response.model}` : ""}
          {row.response.input_tokens !== null && ` · ${row.response.input_tokens} in / ${row.response.output_tokens} out tokens`}
        </p>
      </details>

      <ReviewBox key={row.response_id} responseId={row.response_id} reviews={row.reviews} canReview={c.answerability === "answerable"} onReviewed={onReviewed} />
      <p className="small">
        <a href={href("ask")}>Try this question in Ask →</a>
      </p>
    </div>
  );
}

function ReviewBox({ responseId, reviews, canReview, onReviewed }: { responseId: string; reviews: CaseDetail["responses"][0]["reviews"]; canReview: boolean; onReviewed: () => void }) {
  const [verdict, setVerdict] = useState("correct");
  const [note, setNote] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [saving, setSaving] = useState(false);
  const save = async () => {
    setSaving(true);
    try {
      await api.review(responseId, verdict, note, reviewer);
      setNote("");
      onReviewed();
    } finally {
      setSaving(false);
    }
  };
  return (
    <div className="review-box">
      <h4>Human review</h4>
      {reviews.length > 0 && (
        <ul className="reviews">
          {reviews.map((r) => (
            <li key={r.review_id}>
              <strong>{LABEL_COPY[r.verdict]}</strong> <span className="muted small">{r.reviewer ?? "anonymous"} · {r.created_at}</span>
              {r.note && <p className="small">{r.note}</p>}
            </li>
          ))}
        </ul>
      )}
      <p className="muted small">
        A review sets the final label for metrics. The automated grade and any model-judge verdict above are kept unchanged.
        {!canReview && " Correctness reviews apply to answerable cases; notes are still recorded."}
      </p>
      <div className="review-form">
        <div className="radio-row" role="radiogroup" aria-label="Verdict">
          {Object.entries(LABEL_COPY).map(([k, v]) => (
            <label key={k} className="check">
              <input type="radio" name={`verdict-${responseId}`} checked={verdict === k} onChange={() => setVerdict(k)} /> {v}
            </label>
          ))}
        </div>
        <textarea placeholder="Note (what is right or wrong, and why)" value={note} onChange={(e) => setNote(e.target.value)} rows={2} />
        <div className="review-actions">
          <input placeholder="Your name (optional)" value={reviewer} onChange={(e) => setReviewer(e.target.value)} />
          <button className="btn" onClick={save} disabled={saving}>{saving ? "Saving…" : "Save review"}</button>
        </div>
      </div>
    </div>
  );
}
