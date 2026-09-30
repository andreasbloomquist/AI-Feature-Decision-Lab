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
                      {c.evidence === "interval" && <div className="muted tiny-text">whole 95% interval</div>}
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
