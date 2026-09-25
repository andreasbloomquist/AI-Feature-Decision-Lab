import type { ReactNode } from "react";
import { api } from "../api";
import { MetricCell } from "../components/MetricCell";
import { ErrorNotice, Loading } from "../components/Notice";
import { QualityCostChart, SERIES_COLORS } from "../components/QualityCostChart";
import { useConfig } from "../configContext";
import { APPROACHES, APPROACH_LABELS, msText, usdText } from "../format";
import { href, navigate } from "../router";
import type { ApproachId, Metrics } from "../types";
import { useAsync } from "../useAsync";
import { defaultRunId, RunPicker, useRuns } from "./RunPicker";

const SPLITS = [
  ["held_out", "Held-out"],
  ["development", "Development"],
  ["all", "All"],
] as const;

export function CompareView({ runParam, splitParam }: { runParam: string | null; splitParam: string | null }) {
  const config = useConfig();
  const runs = useRuns();
  const runId = runParam ?? defaultRunId(runs.data ?? []);
  const run = useAsync(runId, () => api.run(runId!));
  const split = splitParam ?? "held_out";
  const go = (patch: { run?: string; split?: string }) => navigate("compare", { run: runId ?? undefined, split, ...patch });

  const criteria = config?.launch_criteria.criteria ?? [];
  const threshold = (id: string) => criteria.find((c) => c.id === id)?.threshold;
  const metrics = run.data?.metrics[split] ?? {};
  const isFixture = run.data?.mode === "fixture";
  const cols = APPROACHES.filter((a) => metrics[a]);
  const hasLive = (runs.data ?? []).some((r) => r.mode === "live");

  const row = (label: string, hint: string, render: (m: Metrics, a: ApproachId) => ReactNode) => (
    <tr>
      <th scope="row">
        {label}
        <span className="row-hint">{hint}</span>
      </th>
      {cols.map((a) => (
        <td key={a}>{render(metrics[a]!, a)}</td>
      ))}
    </tr>
  );
  const splitSize = (key: string) => {
    const m = run.data?.metrics[key];
    const first = m && Object.values(m)[0];
    return first ? ` (${first.n_cases})` : " (none)";
  };

  return (
    <div className="view">
      <div className="toolbar">
        <RunPicker runs={runs.data ?? []} value={runId} onChange={(id) => go({ run: id })} />
        <label className="inline-field">
          <span className="field-label">Split</span>
          <select value={split} onChange={(e) => go({ split: e.target.value })}>
            {SPLITS.map(([k, v]) => (
              <option key={k} value={k}>
                {v}
                {splitSize(k)}
              </option>
            ))}
          </select>
        </label>
      </div>

      {runs.error && <ErrorNotice error={runs.error} onRetry={runs.reload} />}
      {run.error && <ErrorNotice error={run.error} onRetry={run.reload} />}
      {run.loading && <Loading />}

      {run.data && isFixture && (
        <div className="notice notice-demo">
          <strong>Fixture data — demonstration only.</strong> Search results are real (it needs no model). Basic and Guarded RAG
          answers are saved examples written to exercise this interface, not model outputs, so their scores measure the fixture
          and their latency and cost are not measured. Do not compare these numbers with a live run.
        </div>
      )}
      {run.data && !hasLive && (
        <div className="notice">
          <strong>No live evaluation yet.</strong> Set <span className="mono">ANTHROPIC_API_KEY</span> and run{" "}
          <span className="mono">make eval</span> to measure real model behavior.
        </div>
      )}
      {run.data && cols.length === 0 && (
        <div className="notice">
          This run has no {split.replace("_", "-")} cases. It covered: {run.data.splits.join(", ")}.
        </div>
      )}

      {run.data && cols.length > 0 && (
        <>
          <section className="panel">
            <table className="compare-table">
              <thead>
                <tr>
                  <td />
                  {cols.map((a) => (
                    <th key={a} scope="col">
                      <span className="swatch" style={{ background: SERIES_COLORS[a] }} aria-hidden="true" /> {APPROACH_LABELS[a]}
                      <span className="row-hint">{run.data!.prompt_versions[a]?.approach_version}</span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr className="group-row">
                  <td colSpan={cols.length + 1}>Quality</td>
                </tr>
                {row("Answer correctness", "answerable cases; human review, then model judge, then fact match", (m) => (
                  <MetricCell rate={m.correctness} />
                ))}
                {row("Deterministic fact match", "required facts present, answerable cases", (m) => <MetricCell rate={m.correctness_deterministic} />)}
                {row("Citation validity", "answered cases with valid, authorized, supporting citations", (m) => (
                  <MetricCell rate={m.citation_validity} emptyLabel="no answered cases" />
                ))}
                {row("Abstention quality", "unanswerable cases correctly declined", (m) => <MetricCell rate={m.abstention_quality} />)}
                <tr className="group-row">
                  <td colSpan={cols.length + 1}>Safety</td>
                </tr>
                {row("Restricted disclosures", "facts, passages or IDs shown to an unauthorized role (target 0)", (m) => (
                  <span className={m.access_safety.disclosures ? "bad-text" : ""}>
                    <span className="metric-value">{m.access_safety.disclosures}</span>{" "}
                    <span className="metric-n">in {m.access_safety.n_cases} cases</span>
                  </span>
                ))}
                {row("Access-denied handling", "restricted questions declined without disclosure", (m) => <MetricCell rate={m.access_denied_handling} />)}
                <tr className="group-row">
                  <td colSpan={cols.length + 1}>Operations</td>
                </tr>
                {row("Latency p50 / p95", "wall-clock per question", (m) =>
                  m.latency.n ? (
                    <span>
                      <span className="metric-value">
                        {msText(m.latency.p50_ms)} / {msText(m.latency.p95_ms)}
                      </span>{" "}
                      <span className="metric-n">
                        n={m.latency.n}
                        {m.latency.n_unmeasured ? ` of ${m.n_cases}` : ""}
                      </span>
                    </span>
                  ) : (
                    <span className="muted">not measured{m.fixture_rows ? " (demo)" : ""}</span>
                  ),
                )}
                {row("Model cost per question", "from recorded token usage", (m) =>
                  m.cost.per_question_usd !== null && !m.fixture_rows ? (
                    <span>
                      <span className="metric-value">{usdText(m.cost.per_question_usd)}</span>{" "}
                      <span className="metric-n">
                        total {usdText(m.cost.total_usd)}, n={m.cost.n_with_usage}
                        {m.cost.n_missing ? ` of ${m.n_cases}` : ""}
                      </span>
                    </span>
                  ) : (
                    <span className="muted">
                      unavailable ({m.cost.n_missing} of {m.n_cases} without usage)
                    </span>
                  ),
                )}
                {row("Errors", "timeouts, validation failures, provider errors", (m, a) => (
                  <a
                    href={href("inspect", { run: runId ?? undefined, split: split === "all" ? undefined : split, outcome: "error", approach: a })}
                    className={m.errors.count ? "bad-text" : ""}
                  >
                    {m.errors.count} <span className="metric-n">of {m.errors.n}</span>
                  </a>
                ))}
                {row("Status mix", "answered · abstained · error", (m) => (
                  <span className="small">
                    {m.status_counts.answered ?? 0} · {m.status_counts.abstained ?? 0} · {m.status_counts.error ?? 0}
                  </span>
                ))}
              </tbody>
            </table>
            <p className="muted small table-foot">
              Every percentage shows its numerator/denominator; hover for the 95% Wilson interval. Run {run.data.run_id} ·{" "}
              {run.data.model_config.model} · corpus {run.data.corpus_version} · dataset {run.data.dataset_version} · judge{" "}
              {run.data.judge_mode}.
            </p>
          </section>
          <section className="panel">
            <QualityCostChart
              metrics={metrics}
              costThreshold={threshold("cost_per_question") ?? 0.02}
              qualityThreshold={threshold("correctness") ?? 0.8}
              minCoverage={config?.launch_criteria.min_measurement_coverage ?? 1}
              isFixture={isFixture}
            />
          </section>
        </>
      )}
    </div>
  );
}
