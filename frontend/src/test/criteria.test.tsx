import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DecisionView } from "../views/DecisionView";
import { mockFetch } from "./fetchMock";

afterEach(() => vi.unstubAllGlobals());

describe("DecisionView with interval evidence", () => {
  it("says the whole interval must clear the bar, and why the criterion is insufficient", async () => {
    const reason = "95% interval 77.6%–97.0% straddles the threshold; this criterion requires the whole interval to clear it, so more cases are needed";
    const decision = {
      run_id: "live-1", run_mode: "live", run_created_at: "", model_config: {}, evaluated_split: "held_out", n_cases: 45,
      criteria_version: "1.2.0", criteria_hash: "abc", criteria_changed_since_run: false, criteria_registered_on: "2026-09-30",
      correctness_source: null, target_approach: "guarded_rag",
      recommendation: { verdict: "insufficient_evidence", headline: "Insufficient evidence", summary: "" },
      approaches: {
        guarded_rag: {
          label: "Guarded RAG", passes: 0, total: 1,
          criteria: [{
            id: "correctness", label: "Correct answers", comparator: ">=", threshold: 0.8, unit: "rate", value: 0.914, n: 35,
            numerator: 32, ci_low: 0.776, ci_high: 0.97, state: "insufficient", reason, confidence: null, evidence: "interval",
            min_n: 5, example_case_ids: [],
          }],
        },
      },
      comparison: null, next_experiments: [], rollout_tests: [], limitations: [],
    };
    mockFetch({ "/api/decision": { live_available: true, decision }, "/api/runs": [] });
    render(<DecisionView runParam={null} />);
    expect(await screen.findByText("whole 95% interval")).toBeInTheDocument();
    expect(screen.getByText(reason)).toBeInTheDocument();
  });
});
