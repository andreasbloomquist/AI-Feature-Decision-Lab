import { api } from "../api";
import type { RunSummary } from "../types";
import { useAsync } from "../useAsync";

export function runLabel(r: RunSummary): string {
  const date = r.created_at.replace("T", " ").replace("Z", " UTC");
  const scope = r.splits.length === 1 ? ` · ${r.splits[0].replace("_", "-")} only` : "";
  const record = r.designated ? " · run of record" : "";
  return r.mode === "fixture" ? `DEMO · fixture data · ${date}` : `LIVE · ${r.model_config.model} · ${date}${scope}${record}`;
}

/**
 * The run a view opens by default: the newest completed live run that covers the decision split,
 * otherwise the newest fixture run. A development-only tuning run never hides the last full result.
 */
export function defaultRunId(runs: RunSummary[], split = "held_out"): string | null {
  // For the held-out split, use the run the backend decides on (it may be none, e.g. when every live
  // run was dominated by errors). Otherwise take the newest complete, non-partial live run.
  const backendMarks = split === "held_out" && runs.some((r) => r.latest !== undefined);
  const live = backendMarks
    ? runs.find((r) => r.latest)
    : runs.find((r) => r.mode === "live" && r.status.startsWith("completed") && !r.partial && r.splits.includes(split));
  return (live ?? runs.find((r) => r.mode === "fixture") ?? runs[0])?.run_id ?? null;
}

export function useRuns() {
  return useAsync("runs", api.runs);
}

export function RunPicker({ runs, value, onChange }: { runs: RunSummary[]; value: string | null; onChange: (id: string) => void }) {
  return (
    <label className="inline-field">
      <span className="field-label">Evaluation run</span>
      <select value={value ?? ""} onChange={(e) => onChange(e.target.value)}>
        {value && !runs.some((r) => r.run_id === value) && <option value={value}>Unknown run {value}</option>}
        {runs.map((r) => (
          <option key={r.run_id} value={r.run_id}>
            {runLabel(r)}
          </option>
        ))}
      </select>
    </label>
  );
}
