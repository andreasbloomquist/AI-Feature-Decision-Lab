import { pct } from "../format";
import type { Rate } from "../types";

/** A rate with its sample count always visible, and the 95% interval on hover/second line. */
export function MetricCell({ rate, emptyLabel = "no cases" }: { rate: Rate | undefined; emptyLabel?: string }) {
  if (!rate || rate.denominator === 0) return <span className="muted">{emptyLabel}</span>;
  return (
    <span className="metric-cell" title={`95% interval ${pct(rate.ci_low)}–${pct(rate.ci_high)}`}>
      <span className="metric-value">{pct(rate.value, 1)}</span>{" "}
      <span className="metric-n">
        {rate.numerator}/{rate.denominator}
      </span>
      <span className="metric-ci">
        95% CI {pct(rate.ci_low)}–{pct(rate.ci_high)}
      </span>
    </span>
  );
}
