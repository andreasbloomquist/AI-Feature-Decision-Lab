import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Decision, RunSummary } from "../types";
import { DecisionView } from "../views/DecisionView";
import { InspectView } from "../views/InspectView";
import { runLabel } from "../views/RunPicker";
import { mockFetch } from "./fetchMock";

afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = "";
});

const designation = {
  designation_id: "desig_1", run_id: "live-1", split: "held_out", designated_by: "Dana (PM)",
  note: "Agreed in the launch review", designated_at: "2026-09-30T13:37:30Z",
};

function decision(patch: Partial<Decision> = {}): { live_available: boolean; decision: Partial<Decision> } {
  return {
    live_available: true,
    decision: {
      run_id: "live-1", run_mode: "live", run_created_at: "", model_config: {}, evaluated_split: "held_out", n_cases: 45,
      criteria_version: "1.1.0", criteria_hash: "abc", criteria_changed_since_run: false, criteria_registered_on: "2026-09-25",
      correctness_source: null, target_approach: "guarded_rag",
      recommendation: { verdict: "limited_pilot", headline: "Proceed to a limited pilot", summary: "" },
      approaches: { guarded_rag: { label: "Guarded RAG", passes: 0, total: 0, criteria: [] } },
      comparison: null, next_experiments: [], rollout_tests: [], limitations: [],
      designation: null, designation_blocker: null,
      held_out_usage: { dataset_version: "2026-09-25.2", evaluations: 1, run_ids: ["live-1"] },
      ...patch,
    },
  };
}

const run = (patch: Partial<RunSummary> = {}): RunSummary => ({
  run_id: "live-1", created_at: "2026-09-30T13:00:00Z", completed_at: null, mode: "live", status: "completed", label: null,
  splits: ["development", "held_out"], judge_mode: "none", corpus_version: "c", dataset_version: "d", prompt_versions: {},
  model_config: { model: "claude-x" }, n_responses: 0, partial: false, latest: true, designated: false, ...patch,
});

describe("Decision run of record", () => {
  it("needs a name before it designates the run, then shows who designated it", async () => {
    let designated = false;
    const fetch = mockFetch({
      "/api/decision": () => ({ body: decision(designated ? { designation } : {}) }),
      "/api/runs/live-1/designate": () => {
        designated = true;
        return { body: { designation, history: [designation] } };
      },
      "/api/runs": () => ({ body: [run({ designated })] }),
    });
    render(<DecisionView runParam={null} />);
    const button = await screen.findByRole("button", { name: "Mark as decision run of record" });
    expect(screen.getByText(/human reviews of its held-out responses are locked/)).toBeInTheDocument();
    expect(button).toBeDisabled();
    fireEvent.change(screen.getByRole("textbox", { name: "Your name" }), { target: { value: "   " } });
    expect(button).toBeDisabled();
    fireEvent.change(screen.getByRole("textbox", { name: "Your name" }), { target: { value: " Dana (PM) " } });
    fireEvent.change(screen.getByRole("textbox", { name: "Designation note" }), { target: { value: "Agreed in the launch review" } });
    expect(button).toBeEnabled();
    await act(async () => fireEvent.click(button));

    const post = fetch.mock.calls.find(([url]) => String(url).endsWith("/designate"));
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ designated_by: "Dana (PM)", note: "Agreed in the launch review" });
    expect(await screen.findByText("Decision run of record")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark as decision run of record" })).toBeNull();
  });

  it("shows the designation banner with who, when and the note", async () => {
    mockFetch({ "/api/decision": decision({ designation }), "/api/runs": [run({ designated: true })] });
    render(<DecisionView runParam={null} />);
    const banner = (await screen.findByText("Decision run of record")).closest(".notice");
    expect(banner).toHaveTextContent("by Dana (PM) on 2026-09-30 13:37 UTC");
    expect(banner).toHaveTextContent("Agreed in the launch review");
    expect(screen.queryByRole("button", { name: "Mark as decision run of record" })).toBeNull();
    expect(screen.getByRole("option", { name: /run of record/ })).toBeInTheDocument();
  });

  it("explains why an ineligible run cannot be designated instead of offering the form", async () => {
    mockFetch({ "/api/decision": decision({ designation_blocker: "A partial run can never be the decision run of record." }), "/api/runs": [] });
    render(<DecisionView runParam="live-1" />);
    expect(await screen.findByText(/A partial run can never be/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark as decision run of record" })).toBeNull();
  });

  it("marks the designated run in the run picker label", () => {
    expect(runLabel(run({ designated: true }))).toMatch(/· run of record$/);
    expect(runLabel(run())).not.toMatch(/run of record/);
  });
});

describe("Held-out usage", () => {
  it("shows a single evaluation plainly", async () => {
    mockFetch({ "/api/decision": decision(), "/api/runs": [] });
    render(<DecisionView runParam={null} />);
    const note = await screen.findByText(/Held-out set evaluated 1 time by live runs/);
    expect(note.closest(".notice-warn")).toBeNull();
  });

  it("warns when the held-out set was evaluated more than once", async () => {
    const usage = { dataset_version: "2026-09-25.2", evaluations: 3, run_ids: ["live-0", "live-00", "live-1"] };
    mockFetch({ "/api/decision": decision({ held_out_usage: usage }), "/api/runs": [] });
    render(<DecisionView runParam={null} />);
    const warning = (await screen.findByText("Held-out set evaluated 3 times.")).closest(".notice");
    expect(warning).toHaveClass("notice-warn");
    expect(warning).toHaveTextContent("the verdict may reflect tuning against it");
    expect(warning).toHaveTextContent("live-0, live-00, live-1");
  });
});

const response = {
  response_id: "resp-1", approach: "guarded_rag", succeeded: false, reviews: [], review: null, judge: null,
  final_label: null, final_label_source: "deterministic",
  grade: { outcome: "incorrect", deterministic_label: "incorrect", facts: [], disclosures: [], citation_check: null, withheld: false },
  response: { approach: "guarded_rag", answer: "An answer.", status: "answered", citations: [], retrieved_document_ids: [], latency_ms: 900,
    input_tokens: 10, output_tokens: 5, estimated_cost_usd: 0.001, error: null, raw_output: "An answer." },
};
const detail = (split: string) => ({
  case: { case_id: "S05", question: "Q?", user_role: "employee", category: "single_document", split, answerability: "answerable",
    reference_answer: "A.", required_facts: [], acceptable_document_ids: [], forbidden_document_ids: [], forbidden_facts: [], notes: "" },
  responses: [response],
});

async function openCase(routes: Record<string, unknown>) {
  const fetch = mockFetch(routes);
  await act(async () => {
    render(<InspectView route={{ view: "inspect", params: new URLSearchParams("run=live-1&case=S05&focus=guarded_rag") }} />);
  });
  const save = await screen.findByRole("button", { name: "Save review" });
  fireEvent.click(screen.getByRole("radio", { name: "Incorrect" }));
  fireEvent.change(screen.getByRole("textbox", { name: "Reviewer name" }), { target: { value: "Dana" } });
  return { save, fetch };
}

describe("Review lock", () => {
  it("locks reviews of held-out responses in the decision run of record", async () => {
    const { save } = await openCase({
      "/api/runs/live-1/cases/S05": detail("held_out"), "/api/runs/live-1/cases": [], "/api/runs": [run({ designated: true })],
    });
    await waitFor(() => expect(screen.getByText("Reviews are locked.")).toBeInTheDocument());
    expect(save).toBeDisabled();
  });

  it("keeps development reviews open in the decision run of record", async () => {
    const { save } = await openCase({
      "/api/runs/live-1/cases/S05": detail("development"), "/api/runs/live-1/cases": [], "/api/runs": [run({ designated: true })],
    });
    expect(screen.queryByText("Reviews are locked.")).toBeNull();
    expect(save).toBeEnabled();
  });

  it("shows the server's reason when a review is refused because the run was designated meanwhile", async () => {
    const { save } = await openCase({
      "/api/responses/resp-1/reviews": () => ({
        status: 409, body: { detail: "reviews are locked: this response belongs to the decision run of record" },
      }),
      "/api/runs/live-1/cases/S05": detail("held_out"), "/api/runs/live-1/cases": [], "/api/runs": [run()],
    });
    expect(save).toBeEnabled();
    await act(async () => fireEvent.click(save));
    expect(await screen.findByRole("alert")).toHaveTextContent("reviews are locked: this response belongs to the decision run of record");
  });
});
