import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AnswerCard } from "../components/AnswerCard";
import { MetricCell } from "../components/MetricCell";
import { SourceContext } from "../sourceContext";
import type { ApproachResponse } from "../types";

const resp = (over: Partial<ApproachResponse>): ApproachResponse => ({
  approach: "basic_rag", answer: "", status: "answered", citations: [], retrieved_document_ids: ["NS-TRV-2026"],
  latency_ms: 900, input_tokens: 800, output_tokens: 90, estimated_cost_usd: 0.006, error: null, ...over,
});

describe("AnswerCard", () => {
  it("renders valid citations as clickable sources and invalid ones as unverified", () => {
    const open = vi.fn();
    render(
      <SourceContext.Provider value={open}>
        <AnswerCard
          role="employee"
          response={resp({
            answer: "Your VP approves it [NS-TRV-2026#3]. See also [NS-FAKE-001#1].",
            citations: [
              { document_id: "NS-TRV-2026", passage_id: "NS-TRV-2026#3", title: "Travel Policy (2026)", valid: true, reason: null },
              { document_id: "NS-FAKE-001", passage_id: "NS-FAKE-001#1", title: null, valid: false, reason: "unknown_document" },
            ],
          })}
        />
      </SourceContext.Provider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Travel Policy (2026)" }));
    expect(open).toHaveBeenCalledWith({ documentId: "NS-TRV-2026", passageId: "NS-TRV-2026#3", role: "employee" });
    expect(screen.getByText("unverified")).toBeInTheDocument();
    expect(screen.getByText(/not shown as sources/)).toBeInTheDocument();
    // The fabricated document is never offered as a clickable source.
    expect(screen.queryByRole("button", { name: /NS-FAKE/ })).toBeNull();
  });

  it("explains abstentions in plain language", () => {
    render(<AnswerCard role="employee" response={resp({ approach: "guarded_rag", status: "abstained", answer: "x", citations: [] })} />);
    expect(screen.getByText("No supported answer")).toBeInTheDocument();
    expect(screen.getByText(/didn't guess/)).toBeInTheDocument();
  });

  it("explains a timeout and shows unavailable cost", () => {
    render(<AnswerCard role="employee" response={resp({ status: "error", error: "timeout: model request timed out", estimated_cost_usd: null })} />);
    expect(screen.getByText(/took too long/)).toBeInTheDocument();
    expect(screen.getByText("Cost: unavailable")).toBeInTheDocument();
  });

  it("labels fixture responses as demo and hides measurements", () => {
    render(<AnswerCard role="employee" response={resp({ fixture: true, latency_ms: null, estimated_cost_usd: null, answer: "ok" })} />);
    expect(screen.getByText("Demo response")).toBeInTheDocument();
    expect(screen.getByText(/not measured \(demo\)/)).toBeInTheDocument();
  });
});

describe("MetricCell", () => {
  it("shows the denominator beside every percentage", () => {
    render(<MetricCell rate={{ value: 0.8857, numerator: 31, denominator: 35, ci_low: 0.74, ci_high: 0.95 }} />);
    expect(screen.getByText("88.6%")).toBeInTheDocument();
    expect(screen.getByText("31/35")).toBeInTheDocument();
  });
  it("shows no-cases instead of 0%", () => {
    render(<MetricCell rate={{ value: null, numerator: 0, denominator: 0, ci_low: null, ci_high: null }} />);
    expect(screen.getByText("no cases")).toBeInTheDocument();
  });
});
