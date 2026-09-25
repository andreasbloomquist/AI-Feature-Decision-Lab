import { describe, expect, it } from "vitest";
import { measurementText, rateText, segmentAnswer, usdText } from "../format";
import type { ApproachResponse } from "../types";

const base: ApproachResponse = {
  approach: "guarded_rag", answer: "", status: "answered", citations: [], retrieved_document_ids: [],
  latency_ms: 1200, input_tokens: 1000, output_tokens: 100, estimated_cost_usd: 0.0075, error: null,
};

describe("format", () => {
  it("shows unavailable instead of zero when cost is missing", () => {
    expect(usdText(null)).toBe("unavailable");
    expect(usdText(0)).toBe("$0");
    expect(measurementText({ ...base, estimated_cost_usd: null }).cost).toBe("unavailable");
  });

  it("never presents fixture latency or cost as measured", () => {
    const m = measurementText({ ...base, fixture: true });
    expect(m.latency).toMatch(/not measured/);
    expect(m.cost).toMatch(/unavailable/);
  });

  it("labels search cost as no model", () => {
    expect(measurementText({ ...base, approach: "search", estimated_cost_usd: 0 }).cost).toBe("$0 (no model)");
  });

  it("always includes the sample count in a rate", () => {
    expect(rateText({ value: 0.8, numerator: 28, denominator: 35, ci_low: 0.6, ci_high: 0.9 })).toBe("80.0% (28/35)");
    expect(rateText({ value: null, numerator: 0, denominator: 0, ci_low: null, ci_high: null })).toBe("n = 0");
  });

  it("segments citation markers and ignores other brackets", () => {
    const segs = segmentAnswer("A [NS-TRV-2026#3]. B [note] C [NS-EXP-001, NS-ENT-001#2]");
    expect(segs.filter((s) => s.kind === "cite").map((s) => (s.kind === "cite" ? s.ids : []))).toEqual([
      ["NS-TRV-2026#3"],
      ["NS-EXP-001", "NS-ENT-001#2"],
    ]);
    expect(segs.some((s) => s.kind === "text" && s.text.includes("[note]"))).toBe(true);
  });
});
