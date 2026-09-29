import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { mockFetch } from "./fetchMock";

afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = "";
});

const setHash = async (hash: string) => {
  await act(async () => {
    window.location.hash = hash;
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  });
};

describe("App source drawer", () => {
  it("closes for good when you navigate away, and doesn't reopen when you come back", async () => {
    const response = {
      approach: "search", answer: "Receipts are required. [NS-EXP-001#2]", status: "answered",
      citations: [{ document_id: "NS-EXP-001", passage_id: "NS-EXP-001#2", title: "Expense Reimbursement Policy", valid: true, reason: null }],
      retrieved_document_ids: ["NS-EXP-001"], latency_ms: 3, input_tokens: 0, output_tokens: 0, estimated_cost_usd: 0, error: null,
    };
    mockFetch({
      "/api/config": { settings: { mode: "fixture" }, roles: [{ id: "employee", label: "Employee" }], launch_criteria: { criteria: [] } },
      "/api/sample-questions": [],
      "/api/ask": { mode: "fixture", fixture: true, role: "employee", responses: [response] },
      "/api/documents": () => ({ status: 404, body: { detail: "not found" } }),
      "/api/runs": [],
      "/api/decision": { live_available: false, decision: null },
    });
    await setHash("#/ask");
    render(<App />);
    await act(async () => screen.getByRole("button", { name: "Ask" }).click());
    await act(async () => (await screen.findByRole("button", { name: /Source 1/ })).click());
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    await setHash("#/decision");
    expect(screen.queryByRole("dialog")).toBeNull();
    await setHash("#/ask");
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
