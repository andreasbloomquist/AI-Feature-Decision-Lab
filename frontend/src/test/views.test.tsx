import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { chartPoints } from "../components/QualityCostChart";
import { SourcePanel } from "../components/SourcePanel";
import { href } from "../router";
import type { Metrics, RunSummary } from "../types";
import { DecisionView } from "../views/DecisionView";
import { InspectView } from "../views/InspectView";
import { defaultRunId } from "../views/RunPicker";
import { mockFetch } from "./fetchMock";

afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = "";
});

const run = (over: Partial<RunSummary>): RunSummary => ({
  run_id: "r", created_at: "2026-09-25T00:00:00Z", completed_at: null, mode: "live", status: "completed",
  label: null, splits: ["development", "held_out"], judge_mode: "model", corpus_version: "c", dataset_version: "d",
  prompt_versions: {}, model_config: { model: "m" }, n_responses: 0, ...over,
});

describe("defaultRunId", () => {
  it("prefers the newest live run that covers the held-out split, skipping dev-only runs", () => {
    const runs = [run({ run_id: "dev-only", splits: ["development"] }), run({ run_id: "full" }), run({ run_id: "fx", mode: "fixture" })];
    expect(defaultRunId(runs)).toBe("full");
  });
  it("skips partial debug runs, and follows the backend's latest flag when present", () => {
    expect(defaultRunId([run({ run_id: "debug", partial: true }), run({ run_id: "full" })])).toBe("full");
    const flagged = [run({ run_id: "broken", latest: false }), run({ run_id: "good", latest: true })];
    expect(defaultRunId(flagged)).toBe("good");
    const noneUsable = [run({ run_id: "broken", latest: false }), run({ run_id: "fx", mode: "fixture", latest: false })];
    expect(defaultRunId(noneUsable)).toBe("fx");
  });
  it("falls back to the fixture run when there is no live run", () => {
    expect(defaultRunId([run({ run_id: "fx", mode: "fixture" })])).toBe("fx");
    expect(defaultRunId([])).toBeNull();
  });
});

describe("href", () => {
  it("drops empty params and encodes values", () => {
    expect(href("ask", { q: "Who approves $2,000?", role: "hr", empty: undefined })).toBe("#/ask?q=Who+approves+%242%2C000%3F&role=hr");
  });
});

const metrics = (over: Partial<Metrics["cost"]>, fixtureRows = 0): Metrics =>
  ({
    n_cases: 45,
    correctness: { value: 0.8, numerator: 28, denominator: 35, ci_low: 0.6, ci_high: 0.9 },
    cost: { complete: true, n_with_usage: 45, n_missing: 0, coverage: 1, total_usd: 0.45, per_question_usd: 0.01, ...over },
    fixture_rows: fixtureRows,
  }) as unknown as Metrics;

describe("chartPoints", () => {
  it("never plots missing, partial or demo cost", () => {
    const points = chartPoints(
      {
        search: metrics({}),
        basic_rag: metrics({ per_question_usd: null, n_with_usage: 0, n_missing: 45, coverage: 0 }),
        guarded_rag: metrics({ n_with_usage: 30, n_missing: 15, coverage: 0.67 }),
      },
      0.9,
    );
    expect(points.map((p) => p.skipReason)).toEqual([null, "cost unavailable for 45 of 45 cases", "cost measured for only 30 of 45 cases"]);
    expect(chartPoints({ search: metrics({}, 45) }, 0.9)[0].skipReason).toMatch(/demo/);
  });
});

describe("SourcePanel", () => {
  it("explains unavailable documents, moves focus in, and closes on Escape", async () => {
    mockFetch({ "/api/documents": () => ({ status: 404, body: { detail: { error: "This document does not exist or your role cannot view it." } } }) });
    const onClose = vi.fn();
    render(<SourcePanel target={{ documentId: "NS-HR-001", passageId: null, role: "employee" }} onClose={onClose} />);
    expect(await screen.findByText(/does not exist or your role cannot view it/)).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toHaveAttribute("aria-modal", "true");
    expect(screen.getByRole("button", { name: "Close source" })).toHaveFocus();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});

const decisionBody = (live: boolean) => ({
  live_available: live,
  message: live ? undefined : "No live evaluation yet",
  decision: {
    run_id: "fx", run_mode: live ? "live" : "fixture", run_created_at: "", model_config: {}, evaluated_split: "held_out", n_cases: 45,
    criteria_version: "1.0.0", criteria_hash: "abc", criteria_changed_since_run: false, criteria_registered_on: "2026-09-25",
    correctness_source: "human review > model judge > deterministic fact match", target_approach: "guarded_rag",
    recommendation: { verdict: live ? "do_not_launch_yet" : "demonstration_only", headline: live ? "Do not launch yet" : "Demonstration only", summary: "" },
    approaches: {
      guarded_rag: {
        label: "Guarded RAG", passes: 0, total: 1,
        criteria: [{ id: "correctness", label: "Correct answers", comparator: ">=", threshold: 0.8, unit: "rate", value: 0.5, n: 10, numerator: 5, state: "fail", reason: null, confidence: "ok", example_case_ids: ["S07"] }],
      },
    },
    comparison: null, next_experiments: [], rollout_tests: ["Shadow mode"], limitations: ["Small sample"],
  },
});

describe("DecisionView", () => {
  it("says there is no live evaluation and shows fixture states as demo, not pass/fail", async () => {
    mockFetch({ "/api/decision": decisionBody(false), "/api/runs": [] });
    render(<DecisionView runParam={null} />);
    expect(await screen.findByText("No live evaluation yet")).toBeInTheDocument();
    expect(screen.getByText(/Demo: fail/)).toBeInTheDocument();
    expect(screen.queryByText(/^Fail$/)).toBeNull();
  });

  it("links a failing live criterion to its example cases", async () => {
    mockFetch({ "/api/decision": decisionBody(true), "/api/runs": [] });
    render(<DecisionView runParam={null} />);
    const link = await screen.findByRole("link", { name: "S07" });
    expect(link.getAttribute("href")).toContain("case=S07");
    expect(link.getAttribute("href")).toContain("focus=guarded_rag");
  });

  it("shows an error instead of loading forever", async () => {
    mockFetch({ "/api/decision": () => ({ status: 500, body: { detail: "boom" } }), "/api/runs": [] });
    render(<DecisionView runParam={null} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
  });
});

describe("InspectView", () => {
  it("keeps every filter in row links, so deep links survive navigation", async () => {
    const row = {
      response_id: "x", case_id: "U02", approach: "basic_rag", question: "Phone stipend?", role: "employee", category: "unanswerable",
      split: "development", answerability: "unanswerable", status: "answered", outcome: "invented_answer", error_type: null,
      final_label: null, final_label_source: "n/a", deterministic_label: null, judge_verdict: null, reviewed: false,
      succeeded: false, disclosures: 0, latency_ms: null, fixture: true,
    };
    mockFetch({ "/api/runs/fx/cases": [row], "/api/runs": [run({ run_id: "fx", mode: "fixture" })] });
    const params = new URLSearchParams("run=fx&category=unanswerable&focus=search");
    await act(async () => {
      render(<InspectView route={{ view: "inspect", params }} />);
    });
    const link = await screen.findByRole("link", { name: "U02" });
    const target = new URLSearchParams(link.getAttribute("href")!.split("?")[1]);
    expect(Object.fromEntries(target)).toEqual({ run: "fx", category: "unanswerable", focus: "basic_rag", case: "U02" });
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("1 responses"));
  });
});
