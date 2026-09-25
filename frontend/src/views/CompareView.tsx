import { useEffect, useState } from "react";
import { api } from "../api";
import { MetricCell } from "../components/MetricCell";
import { QualityCostChart, SERIES_COLORS } from "../components/QualityCostChart";
import { APPROACHES, APPROACH_LABELS, msText, usdText } from "../format";
import { href } from "../router";
import type { ApproachId, Metrics, RunDetail, RunSummary } from "../types";
import { RunPicker } from "./RunPicker";

const SPLIT_LABELS: Record<string, string> = { held_out: "Held-out (45)", development: "Development (15)", all: "All (60)" };

export function CompareView({ runId, onRun }: { runId: string | null; onRun: (id: string) => void }) {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [run, setRun] = useState<RunDetail | null>(null);
  const [split, setSplit] = useState("held_out");

  useEffect(() => {
    api.runs().then((rs) => {
      setRuns(rs);
      if (!runId && rs.length) onRun((rs.find((r) => r.mode === "live") ?? rs[0]).run_id);
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (runId) api.run(runId).then(setRun);
  }, [runId]);

  const metrics = run?.metrics[split] ?? {};
  const isFixture = run?.mode === "fixture";
  const cols = APPROACHES.filter((a) => metrics[a]);
  const row = (label: string, hint: string, render: (m: Metrics, a: ApproachId) => React.ReactNode) => (
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

  return (
    <div className="view">
      <div className="toolbar">
        <RunPicker runs={runs} value={runId} onChange={onRun} />
        <label className="inline-field">
          <span className="field-label">Split</span>
          <select value={split} onChange={(e) => setSplit(e.target.value)}>
            {Object.entries(SPLIT_LABELS).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </label>
      </div>

      {run && isFixture && (
        <div className="notice notice-demo">
          <strong>Fixture data — demonstration only.</strong> Search results are real (it needs no model). Basic and Guarded RAG
          answers are saved examples written to exercise this interface, not model outputs, so their scores measure the fixture
          and their latency and cost are not measured. Do not compare these numbers with a live run.
        </div>
      )}
      {run && !runs.some((r) => r.mode === "live") && (
        <div className="notice">
          <strong>No live evaluation yet.</strong> Set <span className="mono">ANTHROPIC_API_KEY</span> and run{" "}
          <span className="mono">make eval</span> to measure real model behavior.
        </div>
      )}

      {run && (
        <>
          <section className="panel">
            <table className="compare-table">
              <thead>
                <tr>
                  <th />
                  {cols.map((a) => (
                    <th key={a} scope="col">
                      <span className="swatch" style={{ background: SERIES_COLORS[a] }} /> {APPROACH_LABELS[a]}
                      <span className="row-hint">{run.prompt_versions[a]?.approach_version}</span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr className="group-row"><td colSpan={cols.length + 1}>Quality</td></tr>
                {row("Answer correctness", `answerable cases · ${metrics[cols[0]]?.correctness.label_sources?.model_judge ? "includes model-judged" : "deterministic fact match"}`, (m) => (
                  <MetricCell rate={m.correctness} />
                ))}
                {row("Deterministic fact match", "required facts present, answerable cases", (m) => <MetricCell rate={m.correctness_deterministic} />)}
                {row("Citation validity", "answered cases with valid, authorized, supporting citations", (m) => <MetricCell rate={m.citation_validity} emptyLabel="no answered cases" />)}
                {row("Abstention quality", "unanswerable cases correctly declined", (m) => <MetricCell rate={m.abstention_quality} />)}
                <tr className="group-row"><td colSpan={cols.length + 1}>Safety</td></tr>
                {row("Restricted disclosures", "facts, passages or IDs shown to an unauthorized role (target 0)", (m) => (
                  <span className={m.access_safety.disclosures ? "bad-text" : ""}>
                    <span className="metric-value">{m.access_safety.disclosures}</span> <span className="metric-n">in {m.access_safety.n_cases} cases</span>
                  </span>
                ))}
                {row("Access-denied handling", "restricted questions declined without disclosure", (m) => <MetricCell rate={m.access_denied_handling} />)}
                <tr className="group-row"><td colSpan={cols.length + 1}>Operations</td></tr>
                {row("Latency p50 / p95", "wall-clock per question", (m) =>
                  m.latency.n ? (
                    <span>
                      <span className="metric-value">{msText(m.latency.p50_ms)} / {msText(m.latency.p95_ms)}</span> <span className="metric-n">n={m.latency.n}</span>
                    </span>
                  ) : (
                    <span className="muted">not measured{m.fixture_rows ? " (demo)" : ""}</span>
                  ),
                )}
                {row("Model cost per question", "from recorded token usage", (m) =>
                  m.cost.available ? (
                    <span>
                      <span className="metric-value">{usdText(m.cost.per_question_usd)}</span>{" "}
                      <span className="metric-n">total {usdText(m.cost.total_usd)}, n={m.cost.n_with_usage}</span>
                    </span>
                  ) : (
                    <span className="muted">unavailable ({m.cost.n_missing} of {m.n_cases} without usage)</span>
                  ),
                )}
                {row("Errors", "timeouts, validation failures, provider errors", (m) => (
                  <a href={href("inspect", { run: run.run_id, split: split === "all" ? undefined : split, outcome: "error" })} className={m.errors.count ? "bad-text" : ""}>
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
              Every percentage shows its numerator/denominator; hover for the 95% Wilson interval. Run {run.run_id} ·{" "}
              {run.model_config.model} · corpus {run.corpus_version} · dataset {run.dataset_version} · judge {run.judge_mode}.
            </p>
          </section>
          <section className="panel">
            <QualityCostChart metrics={metrics} costThreshold={0.02} qualityThreshold={0.8} isFixture={isFixture} />
          </section>
        </>
      )}
    </div>
  );
}
