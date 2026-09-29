import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { InspectView } from "../views/InspectView";
import { mockFetch } from "./fetchMock";

afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = "";
});

const response = {
  response_id: "resp-1", approach: "guarded_rag", succeeded: false, reviews: [], review: null, judge: null,
  final_label: null, final_label_source: "deterministic",
  grade: { outcome: "incorrect", deterministic_label: "incorrect", facts: [], disclosures: [], citation_check: null, withheld: false },
  response: { approach: "guarded_rag", answer: "An answer.", status: "answered", citations: [], retrieved_document_ids: [], latency_ms: 900,
    input_tokens: 10, output_tokens: 5, estimated_cost_usd: 0.001, error: null, raw_output: "An answer." },
};
const detail = {
  case: { case_id: "S05", question: "Q?", user_role: "employee", category: "single_document", split: "held_out", answerability: "answerable",
    reference_answer: "A.", required_facts: [], acceptable_document_ids: [], forbidden_document_ids: [], forbidden_facts: [], notes: "" },
  responses: [response],
};

describe("Review form", () => {
  it("needs an explicit verdict and a reviewer name before it can be saved", async () => {
    mockFetch({ "/api/runs/live-1/cases/S05": detail, "/api/runs/live-1/cases": [], "/api/runs": [] });
    await act(async () => {
      render(<InspectView route={{ view: "inspect", params: new URLSearchParams("run=live-1&case=S05&focus=guarded_rag") }} />);
    });
    const save = await screen.findByRole("button", { name: "Save review" });
    expect(save).toBeDisabled();
    for (const radio of screen.getAllByRole("radio")) expect(radio).not.toBeChecked();
    fireEvent.click(screen.getByRole("radio", { name: "Incorrect" }));
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByRole("textbox", { name: "Reviewer name" }), { target: { value: "Dana (Policy owner)" } });
    expect(save).toBeEnabled();
  });
});
