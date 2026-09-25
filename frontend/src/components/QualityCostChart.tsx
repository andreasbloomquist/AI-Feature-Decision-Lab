import { useState } from "react";
import { APPROACHES, APPROACH_LABELS, pct, usdText } from "../format";
import type { ApproachId, Metrics } from "../types";

// Categorical slots 1-3 of the reference palette (validated all-pairs for 3 series).
export const SERIES_COLORS: Record<ApproachId, string> = {
  search: "var(--series-1)",
  basic_rag: "var(--series-2)",
  guarded_rag: "var(--series-3)",
};

const W = 560, H = 300;
const M = { l: 56, r: 24, t: 20, b: 44 };

export function QualityCostChart({
  metrics, costThreshold, qualityThreshold, isFixture,
}: {
  metrics: Partial<Record<ApproachId, Metrics>>;
  costThreshold: number;
  qualityThreshold: number;
  isFixture: boolean;
}) {
  const [hover, setHover] = useState<ApproachId | null>(null);
  const points = APPROACHES.flatMap((a) => {
    const m = metrics[a];
    if (!m) return [];
    const cost = m.cost.per_question_usd;
    const q = m.correctness.value;
    return [{ a, cost, q, m, plottable: cost !== null && q !== null }];
  });
  const plotted = points.filter((p) => p.plottable);
  const maxCost = Math.max(costThreshold * 1.5, ...plotted.map((p) => (p.cost as number) * 1.15));
  const x = (v: number) => M.l + (v / maxCost) * (W - M.l - M.r);
  const y = (v: number) => M.t + (1 - v) * (H - M.t - M.b);
  const xticks = [0, maxCost / 3, (2 * maxCost) / 3, maxCost];

  return (
    <figure className="chart">
      <figcaption>
        <strong>Quality versus cost</strong>
        <span className="muted small">
          {" "}
          Correctness on answerable cases vs. average model cost per question. Dashed lines are launch thresholds.
          {isFixture && " Demo data: model cost is not measured in fixture mode."}
        </span>
      </figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Scatter chart of correctness against cost per question">
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <g key={t}>
            <line x1={M.l} x2={W - M.r} y1={y(t)} y2={y(t)} className="grid" />
            <text x={M.l - 8} y={y(t) + 4} className="tick" textAnchor="end">{pct(t)}</text>
          </g>
        ))}
        {xticks.map((t) => (
          <text key={t} x={x(t)} y={H - M.b + 18} className="tick" textAnchor="middle">{usdText(t)}</text>
        ))}
        <line x1={M.l} x2={W - M.r} y1={y(0)} y2={y(0)} className="axis" />
        <line x1={x(costThreshold)} x2={x(costThreshold)} y1={M.t} y2={y(0)} className="threshold" />
        <line x1={M.l} x2={W - M.r} y1={y(qualityThreshold)} y2={y(qualityThreshold)} className="threshold" />
        <text x={x(costThreshold) + 4} y={M.t + 10} className="tick">max {usdText(costThreshold)}</text>
        <text x={W - M.r} y={y(qualityThreshold) - 6} className="tick" textAnchor="end">min {pct(qualityThreshold)}</text>
        <text x={(W + M.l) / 2} y={H - 6} className="axis-label" textAnchor="middle">Average model cost per question (USD)</text>
        <text x={14} y={(H - M.b) / 2} className="axis-label" textAnchor="middle" transform={`rotate(-90 14 ${(H - M.b) / 2})`}>Correct</text>
        {plotted.map((p) => (
          <g key={p.a} onMouseEnter={() => setHover(p.a)} onMouseLeave={() => setHover(null)} onFocus={() => setHover(p.a)} onBlur={() => setHover(null)} tabIndex={0}>
            <circle cx={x(p.cost as number)} cy={y(p.q as number)} r={14} fill="transparent" />
            <circle cx={x(p.cost as number)} cy={y(p.q as number)} r={6} fill={SERIES_COLORS[p.a]} stroke="var(--surface)" strokeWidth={2} />
            <text x={x(p.cost as number) + 10} y={y(p.q as number) - 8} className="point-label">{APPROACH_LABELS[p.a]}</text>
          </g>
        ))}
      </svg>
      {hover && (() => {
        const p = points.find((pp) => pp.a === hover)!;
        return (
          <div className="chart-tip" role="status">
            <strong>{APPROACH_LABELS[p.a]}</strong> · correct {pct(p.q, 1)} ({p.m.correctness.numerator}/{p.m.correctness.denominator}) · {usdText(p.cost)} per question (n={p.m.cost.n_with_usage})
          </div>
        );
      })()}
      <ul className="legend">
        {points.map((p) => (
          <li key={p.a}>
            <span className="swatch" style={{ background: SERIES_COLORS[p.a] }} /> {APPROACH_LABELS[p.a]}
            {!p.plottable && <span className="muted small"> — not plotted: cost {p.m.cost.n_missing ? `unavailable for ${p.m.cost.n_missing} of ${p.m.n_cases} cases` : "unavailable"}</span>}
          </li>
        ))}
      </ul>
    </figure>
  );
}
