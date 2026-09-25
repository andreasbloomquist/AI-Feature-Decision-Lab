import { useState } from "react";
import { APPROACHES, APPROACH_LABELS, pct, usdText } from "../format";
import type { ApproachId, Metrics } from "../types";

// Categorical slots 1-3 of a colour-blind-validated palette; each point is also labelled in text.
export const SERIES_COLORS: Record<ApproachId, string> = {
  search: "var(--series-1)",
  basic_rag: "var(--series-2)",
  guarded_rag: "var(--series-3)",
};

const W = 560;
const H = 300;
const M = { l: 56, r: 24, t: 20, b: 44 };

interface Point {
  approach: ApproachId;
  metrics: Metrics;
  cost: number | null;
  quality: number | null;
  /** Why the point is not plotted, or null if it is. Missing cost is never drawn as $0. */
  skipReason: string | null;
}

export function chartPoints(metrics: Partial<Record<ApproachId, Metrics>>, minCoverage: number): Point[] {
  return APPROACHES.flatMap((approach) => {
    const m = metrics[approach];
    if (!m) return [];
    const cost = m.cost.per_question_usd;
    const quality = m.correctness.value;
    let skipReason: string | null = null;
    if (m.fixture_rows) skipReason = "demo responses have no measured cost";
    else if (cost === null) skipReason = `cost unavailable for ${m.cost.n_missing} of ${m.n_cases} cases`;
    else if (m.cost.coverage < minCoverage) skipReason = `cost measured for only ${m.cost.n_with_usage} of ${m.n_cases} cases`;
    else if (quality === null) skipReason = "no answerable cases";
    return [{ approach, metrics: m, cost, quality, skipReason }];
  });
}

export function QualityCostChart({
  metrics,
  costThreshold,
  qualityThreshold,
  minCoverage,
  isFixture,
}: {
  metrics: Partial<Record<ApproachId, Metrics>>;
  costThreshold: number;
  qualityThreshold: number;
  minCoverage: number;
  isFixture: boolean;
}) {
  const [hover, setHover] = useState<ApproachId | null>(null);
  const points = chartPoints(metrics, minCoverage);
  const plotted = points.filter((p) => p.skipReason === null) as (Point & { cost: number; quality: number })[];
  const maxCost = Math.max(costThreshold * 1.5, ...plotted.map((p) => p.cost * 1.15));
  const x = (v: number) => M.l + (v / maxCost) * (W - M.l - M.r);
  const y = (v: number) => M.t + (1 - v) * (H - M.t - M.b);
  const xticks = [0, maxCost / 3, (2 * maxCost) / 3, maxCost];
  const describe = (p: Point) =>
    `${APPROACH_LABELS[p.approach]}: ${pct(p.quality, 1)} correct (${p.metrics.correctness.numerator}/${p.metrics.correctness.denominator}), ${usdText(p.cost)} per question`;
  const hovered = points.find((p) => p.approach === hover);

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
      <svg viewBox={`0 0 ${W} ${H}`} role="group" aria-label="Scatter chart of correctness against cost per question">
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <g key={t} aria-hidden="true">
            <line x1={M.l} x2={W - M.r} y1={y(t)} y2={y(t)} className="grid" />
            <text x={M.l - 8} y={y(t) + 4} className="tick" textAnchor="end">
              {pct(t)}
            </text>
          </g>
        ))}
        <g aria-hidden="true">
          {xticks.map((t) => (
            <text key={t} x={x(t)} y={H - M.b + 18} className="tick" textAnchor="middle">
              {usdText(t)}
            </text>
          ))}
          <line x1={M.l} x2={W - M.r} y1={y(0)} y2={y(0)} className="axis" />
          <line x1={x(costThreshold)} x2={x(costThreshold)} y1={M.t} y2={y(0)} className="threshold" />
          <line x1={M.l} x2={W - M.r} y1={y(qualityThreshold)} y2={y(qualityThreshold)} className="threshold" />
          <text x={x(costThreshold) + 4} y={M.t + 10} className="tick">
            max {usdText(costThreshold)}
          </text>
          <text x={W - M.r} y={y(qualityThreshold) - 6} className="tick" textAnchor="end">
            min {pct(qualityThreshold)}
          </text>
          <text x={(W + M.l) / 2} y={H - 6} className="axis-label" textAnchor="middle">
            Average model cost per question (USD)
          </text>
          <text x={14} y={(H - M.b) / 2} className="axis-label" textAnchor="middle" transform={`rotate(-90 14 ${(H - M.b) / 2})`}>
            Correct
          </text>
        </g>
        {plotted.map((p) => (
          <g
            key={p.approach}
            role="img"
            aria-label={describe(p)}
            tabIndex={0}
            onMouseEnter={() => setHover(p.approach)}
            onMouseLeave={() => setHover(null)}
            onFocus={() => setHover(p.approach)}
            onBlur={() => setHover(null)}
          >
            <circle cx={x(p.cost)} cy={y(p.quality)} r={14} fill="transparent" />
            <circle cx={x(p.cost)} cy={y(p.quality)} r={6} fill={SERIES_COLORS[p.approach]} stroke="var(--surface)" strokeWidth={2} />
            <text x={x(p.cost) + 10} y={y(p.quality) - 8} className="point-label">
              {APPROACH_LABELS[p.approach]}
            </text>
          </g>
        ))}
      </svg>
      {hovered && (
        <div className="chart-tip" role="status">
          {describe(hovered)} (n={hovered.metrics.cost.n_with_usage})
        </div>
      )}
      <ul className="legend">
        {points.map((p) => (
          <li key={p.approach}>
            <span className="swatch" style={{ background: SERIES_COLORS[p.approach] }} aria-hidden="true" /> {APPROACH_LABELS[p.approach]}
            {p.skipReason && <span className="muted small"> — not plotted: {p.skipReason}</span>}
          </li>
        ))}
      </ul>
    </figure>
  );
}
