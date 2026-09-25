import type { RunSummary } from "../types";

export function runLabel(r: RunSummary): string {
  const date = r.created_at.replace("T", " ").replace("Z", " UTC");
  return r.mode === "fixture" ? `DEMO · fixture data · ${date}` : `LIVE · ${r.model_config.model} · ${date}`;
}

export function RunPicker({ runs, value, onChange }: { runs: RunSummary[]; value: string | null; onChange: (id: string) => void }) {
  return (
    <label className="inline-field">
      <span className="field-label">Evaluation run</span>
      <select value={value ?? ""} onChange={(e) => onChange(e.target.value)} aria-label="Evaluation run">
        {runs.map((r) => (
          <option key={r.run_id} value={r.run_id}>
            {runLabel(r)}
          </option>
        ))}
      </select>
    </label>
  );
}
