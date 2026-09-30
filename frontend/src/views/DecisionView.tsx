import { useState } from "react";
import { api } from "../api";
import { ErrorNotice, Loading } from "../components/Notice";
import { StateBadge } from "../components/StatusBadge";
import { APPROACHES, APPROACH_LABELS, msText, pct, usdText } from "../format";
import { href, navigate } from "../router";
import type { Criterion, DecisionResponse } from "../types";
import { useAsync } from "../useAsync";
import { RunPicker, useRuns } from "./RunPicker";

function fmt(unit: Criterion["unit"], v: number | null): string {
  if (v === null || v === undefined) return "—";
  if (unit === "rate") return pct(v, 1);
  if (unit === "ms") return msText(v);
  if (unit === "usd") return usdText(v);
  return String(v);
}

/** Extra precision, used when rounding would make a failing value look equal to its threshold. */
function fmtPrecise(unit: Criterion["unit"], v: number): string {
  if (unit === "rate") return pct(v, 2);
  if (unit === "ms") return `${Math.round(v).toLocaleString()} ms`;
  if (unit === "usd") return `$${v.toFixed(5)}`;
  return String(v);
}

function measured(c: Criterion): string {
  if (c.state === "insufficient" && c.value === null) return "not measured";
  let base = fmt(c.unit, c.value);
  if (c.state === "fail" && c.value !== null && base === fmt(c.unit, c.threshold)) base = fmtPrecise(c.unit, c.value);
  if (c.unit === "rate" && c.numerator !== undefined) return `${base} (${c.numerator}/${c.n})`;
  if (c.n !== null) return `${base} (n=${c.n})`;
  return base;
}

/**
 * Says when human reviews changed correctness labels of the target (the verdict) or the baseline (the lift).
 * Reviews that agree with the automated label are confirmations and are only counted. Mirrors the backend's
 * `human_override_note`, which writes the same sentence into the memo.
 */
function humanOverrides(d: NonNullable<DecisionResponse["decision"]>): string | null {
  const approaches = [...new Set([d.target_approach, ...(d.comparison ? [d.comparison.baseline] : [])])];
  const parts: string[] = [];
  let confirmed = 0;
  for (const a of approaches) {
    const entry = d.approaches[a];
    const reviews = entry?.human_reviews;
    if (!reviews) continue;
    const s = entry.label_sources;
    const total = s ? s.human + s.model_judge + s.deterministic : 0;
    confirmed += reviews.reviewed - reviews.changed;
    if (reviews.changed) parts.push(`${reviews.changed} of ${total} for ${APPROACH_LABELS[a]}`);
  }
  if (!parts.length) return null;
  const more = confirmed ? ` ${confirmed} more review(s) confirmed the automated label.` : "";
  return `Human review changed correctness labels: ${parts.join("; ")}.${more} Check those reviews in Inspect before relying on this verdict or the comparison.`;
}

type DecisionData = NonNullable<DecisionResponse["decision"]>;

/** "2026-09-30T13:37:30Z" → "2026-09-30 13:37 UTC". */
function dateText(iso: string): string {
  return iso.replace("T", " ").replace(/:\d{2}Z$/, " UTC");
}

/**
 * The decision run of record (R1.1): who named this run as the one the decision rests on, or a form to name it.
 * Designating locks human reviews of this run's held-out responses, so its verdict can no longer move.
 */
function RunOfRecord({ d, recordElsewhere, onDesignated }: { d: DecisionData; recordElsewhere: boolean; onDesignated: () => void }) {
  const [name, setName] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (d.designation) {
    const r = d.designation;
    return (
      <div className="notice notice-record" role="note">
        <strong>Decision run of record</strong> · by {r.designated_by} on {dateText(r.designated_at)}
        {r.note && <> · {r.note}</>}
        <p className="small">Human reviews of this run's held-out responses are locked, so this verdict can no longer change.</p>
      </div>
    );
  }
  if (d.designation_blocker) {
    return (
      <p className="muted small" role="note">
        This run can't be the decision run of record: {d.designation_blocker}
      </p>
    );
  }
  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.designate(d.run_id, name.trim(), note);
      onDesignated();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };
  return (
    <section className="panel" aria-label="Decision run of record">
      <h3>Mark as decision run of record</h3>
      <p className="small">
        Name the run this decision rests on. It becomes the run the Decision view and the memo use, even when newer runs exist, and human
        reviews of its held-out responses are locked so the verdict can't be changed afterwards. Development-split reviews stay open.
        {recordElsewhere && " Another run is the run of record now; marking this one moves the designation and unlocks the other run's reviews."}
      </p>
      <div className="record-form">
        <input aria-label="Your name" placeholder="Your name (required)" required value={name} onChange={(e) => setName(e.target.value)} />
        <input className="record-note" aria-label="Designation note" placeholder="Note (optional, e.g. the review meeting)" maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} />
        <button className="btn btn-primary" onClick={save} disabled={saving || !name.trim()}>
          {saving ? "Saving…" : "Mark as decision run of record"}
        </button>
      </div>
      {error && <ErrorNotice error={error} />}
    </section>
  );
}

/** How often live runs have evaluated this dataset's held-out set (R1.2). More than once is a warning. */
function HeldOutUsage({ d }: { d: DecisionData }) {
  const u = d.held_out_usage;
  if (!u) return null;
  const times = `${u.evaluations} ${u.evaluations === 1 ? "time" : "times"}`;
  if (u.evaluations > 1) {
    return (
      <div className="notice notice-warn" role="note">
        <strong>Held-out set evaluated {times}.</strong> The held-out set has been evaluated {u.evaluations} times; the verdict may reflect
        tuning against it. Dataset <span className="mono">{u.dataset_version}</span>, runs <span className="mono">{u.run_ids.join(", ")}</span>.
      </div>
    );
  }
  return (
    <p className="muted small" role="note">
      Held-out set evaluated {times} by live runs (dataset <span className="mono">{u.dataset_version}</span>).
    </p>
  );
}

export function DecisionView({ runParam }: { runParam: string | null }) {
  const runs = useRuns();
  const result = useAsync(`decision:${runParam ?? "latest"}`, () => api.decision(runParam ?? undefined));
  const [showAll, setShowAll] = useState(false);

  if (result.error) {
    // Keep the run picker so a stale or unknown run in the URL is never a dead end.
    return (
      <div className="view">
        <div className="toolbar">
          <RunPicker runs={runs.data ?? []} value={runParam} onChange={(id) => navigate("decision", { run: id })} />
          {runParam && <a href={href("decision")}>Use the latest run</a>}
        </div>
        <ErrorNotice error={result.error} onRetry={result.reload} />
      </div>
    );
  }
  const data = result.data;
  if (!data) {
    return (
      <div className="view">
        <Loading />
      </div>
    );
  }
  const d = data.decision;
  const target = d?.approaches[d.target_approach];
  const isFixture = d?.run_mode === "fixture";

  return (
    <div className="view decision">
      <div className="toolbar">
        <RunPicker runs={runs.data ?? []} value={d?.run_id ?? null} onChange={(id) => navigate("decision", { run: id })} />
        <span className="muted small">
          Criteria v{d?.criteria_version} · registered {d?.criteria_registered_on} · hash <span className="mono">{d?.criteria_hash}</span>
        </span>
      </div>

      {d?.criteria_changed_since_run && (
        <div className="notice notice-warn" role="note">
          <strong>Criteria changed since this run.</strong> This verdict uses the criteria stored with the run. The current
          config/launch_criteria.yaml differs; a new run is needed to evaluate against it.
        </div>
      )}
      {!data.live_available && (
        <section className="panel empty-live">
          <h2>No live evaluation yet</h2>
          <p>
            There are no measured model results, so there is no launch recommendation. The criteria below are applied to fixture
            data only to show how the decision works.
          </p>
          <ol className="small">
            <li>
              Copy <span className="mono">.env.example</span> to <span className="mono">.env</span> and set <span className="mono">ANTHROPIC_API_KEY</span>.
            </li>
            <li>
              Run <span className="mono">make eval</span> (about 5–10 minutes for 60 cases × 3 approaches plus judging).
            </li>
            <li>Reload this page. The latest live run is used automatically.</li>
          </ol>
        </section>
      )}

      {d && (
        <>
          <section className={`panel verdict verdict-${d.recommendation.verdict}`}>
            <p className="eyebrow">
              {isFixture ? "Example based only on fixture data" : "Recommendation"} · {APPROACH_LABELS[d.target_approach]} · {d.evaluated_split === "held_out" ? "held-out set" : d.evaluated_split}, {d.n_cases} cases
            </p>
            <h2>{d.recommendation.headline}</h2>
            <p>{d.recommendation.summary}</p>
            {d.comparison && !isFixture && (
              <p className="small">
                Versus {APPROACH_LABELS[d.comparison.baseline] ?? d.comparison.baseline}: correctness {d.comparison.target_correct} vs {d.comparison.baseline_correct}
                {d.comparison.correctness_lift_pp !== null && ` (${d.comparison.correctness_lift_pp > 0 ? "+" : ""}${d.comparison.correctness_lift_pp} points)`} · p95{" "}
                {msText(d.comparison.target_p95_ms)} vs {msText(d.comparison.baseline_p95_ms)} · cost per question {usdText(d.comparison.target_cost_per_question)} vs{" "}
                {usdText(d.comparison.baseline_cost_per_question)}.
              </p>
            )}
            {isFixture && d.comparison && (
              <p className="small muted">
                For illustration only: fixture correctness {d.comparison.target_correct} ({APPROACH_LABELS[d.comparison.target] ?? d.comparison.target}) vs{" "}
                {d.comparison.baseline_correct} ({APPROACH_LABELS[d.comparison.baseline] ?? d.comparison.baseline}
                {d.comparison.baseline === "search" ? ", real" : ""}).
              </p>
            )}
          </section>

          {!isFixture && (
            <>
              <RunOfRecord
                key={d.run_id}
                d={d}
                recordElsewhere={(runs.data ?? []).some((r) => r.designated && r.run_id !== d.run_id)}
                onDesignated={() => {
                  result.reload();
                  runs.reload();
                }}
              />
              <HeldOutUsage d={d} />
            </>
          )}

          {humanOverrides(d) && (
            <div className="notice notice-warn" role="note">
              <strong>Human overrides.</strong> {humanOverrides(d)}
            </div>
          )}

          <section className="panel">
            <div className="section-head">
              <h3>Launch criteria · {APPROACH_LABELS[d.target_approach]}</h3>
              <label className="check small">
                <input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} /> Show all approaches
              </label>
            </div>
            <table className="criteria-table">
              <thead>
                <tr>
                  <th>Criterion</th>
                  <th>Threshold</th>
                  {(showAll ? APPROACHES.filter((a) => d.approaches[a]) : [d.target_approach]).map((a) => (
                    <th key={a}>{APPROACH_LABELS[a]}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {target?.criteria.map((c, i) => (
                  <tr key={c.id}>
                    <th scope="row">{c.label}</th>
                    <td className="mono">
                      {c.comparator} {fmt(c.unit, c.threshold)}
                    </td>
                    {(showAll ? APPROACHES.filter((a) => d.approaches[a]) : [d.target_approach]).map((a) => {
                      const cc = d.approaches[a]!.criteria[i];
                      return (
                        <td key={a} className="criterion-cell">
                          <StateBadge state={cc.state} demo={isFixture} />
                          <div className="small">{measured(cc)}</div>
                          {cc.confidence === "low" && <div className="muted tiny-text">95% CI {pct(cc.ci_low, 1)}–{pct(cc.ci_high, 1)} crosses the threshold</div>}
                          {cc.reason && <div className="muted tiny-text">{cc.reason}</div>}
                          {cc.state === "fail" && cc.example_case_ids.length > 0 && (
                            <div className="examples tiny-text">
                              Examples:{" "}
                              {cc.example_case_ids.map((id) => (
                                <a key={id} className="mono" href={href("inspect", { run: d.run_id, case: id, focus: a, split: d.evaluated_split })}>
                                  {id}
                                </a>
                              ))}
                            </div>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="muted small table-foot">
              These are the criteria stored with this run (config/launch_criteria.yaml at run time), so editing the file later cannot change
              this verdict. Correctness source: {d.correctness_source ?? "human review > model judge > deterministic fact match"}. A criterion with
              too few cases or too few measured values is “insufficient evidence”, never a pass.
            </p>
          </section>

          {d.next_experiments.length > 0 && (
            <section className="panel">
              <h3>Next experiment</h3>
              <ul className="plain-list">
                {d.next_experiments.map((e) => (
                  <li key={e.criterion}>
                    <strong>{target?.criteria.find((c) => c.id === e.criterion)?.label}:</strong> {e.text}
                  </li>
                ))}
              </ul>
            </section>
          )}

          <div className="two-col">
            <section className="panel">
              <h3>What we would test before a real rollout</h3>
              <ol className="plain-list">
                {d.rollout_tests.map((t) => (
                  <li key={t}>{t}</li>
                ))}
              </ol>
            </section>
            <section className="panel">
              <h3>Limits of this experiment</h3>
              <ul className="plain-list">
                {d.limitations.map((t) => (
                  <li key={t}>{t}</li>
                ))}
              </ul>
            </section>
          </div>
        </>
      )}
    </div>
  );
}
