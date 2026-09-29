import { act, render, renderHook, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { ConfigContext } from "../configContext";
import { usdText } from "../format";
import type { AppConfig } from "../types";
import { useAsync } from "../useAsync";
import { AskView } from "../views/AskView";
import { DecisionView } from "../views/DecisionView";
import { mockFetch } from "./fetchMock";

afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = "";
});

describe("useAsync", () => {
  it("never returns data loaded for a previous key", async () => {
    const resolvers: Record<string, (v: string) => void> = {};
    const load = (k: string) => () => new Promise<string>((resolve) => (resolvers[k] = resolve));
    const { result, rerender } = renderHook(({ k }: { k: string | null }) => useAsync(k, load(k ?? "")), { initialProps: { k: "run-a" as string | null } });
    await act(async () => resolvers["run-a"]("A data"));
    expect(result.current.data).toBe("A data");

    rerender({ k: "run-b" });
    expect(result.current).toMatchObject({ data: null, loading: true });
    rerender({ k: null });
    expect(result.current).toMatchObject({ data: null, loading: false });
  });

  it("keeps the current data on screen while reloading the same key", async () => {
    let n = 0;
    const { result } = renderHook(() => useAsync("same", async () => ++n));
    await waitFor(() => expect(result.current.data).toBe(1));
    act(() => result.current.reload());
    expect(result.current).toMatchObject({ data: 1, loading: true });
    await waitFor(() => expect(result.current).toMatchObject({ data: 2, loading: false }));
  });
});

describe("DecisionView with an unknown run", () => {
  it("keeps the run picker and a way back to the latest run", async () => {
    mockFetch({ "/api/decision": () => ({ status: 404, body: { detail: "run not found" } }), "/api/runs": [] });
    render(<DecisionView runParam="deleted-run" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("run not found");
    expect(screen.getByRole("link", { name: "Use the latest run" })).toHaveAttribute("href", "#/decision");
  });
});

describe("ErrorBoundary", () => {
  it("shows a message instead of a blank page when a view throws", () => {
    const Broken = () => {
      throw new Error("bad response shape");
    };
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <ErrorBoundary resetKey="compare">
        <Broken />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("bad response shape");
  });
});

describe("AskView role from a deep link", () => {
  it("sends the role it shows, falling back to Employee for an unknown role", async () => {
    const fetchMock = mockFetch({ "/api/sample-questions": [], "/api/ask": { mode: "live", fixture: false, role: "employee", responses: [] } });
    const config = { roles: [{ id: "employee", label: "Employee" }, { id: "hr", label: "HR" }], settings: { mode: "live" } } as unknown as AppConfig;
    render(
      <ConfigContext.Provider value={config}>
        <AskView initialQuestion="Who approves travel?" initialRole="bogus" />
      </ConfigContext.Provider>,
    );
    expect(screen.getByRole("combobox")).toHaveValue("employee");
    await act(async () => screen.getByRole("button", { name: "Ask" }).click());
    const askCall = fetchMock.mock.calls.find(([url]) => String(url).includes("/api/ask"))!;
    expect(JSON.parse(String(askCall[1]!.body)).role).toBe("employee");
  });
});

describe("usdText", () => {
  it("never shows a measured, nonzero cost as zero", () => {
    expect(usdText(0.00002)).toBe("<$0.0001");
    expect(usdText(0)).toBe("$0");
  });
});

describe("DecisionView human overrides", () => {
  it("stays quiet when reviews only confirm the automated labels", async () => {
    const decision = {
      run_id: "live-1", run_mode: "live", run_created_at: "", model_config: {}, evaluated_split: "held_out", n_cases: 45,
      criteria_version: "1.1.0", criteria_hash: "abc", criteria_changed_since_run: false, criteria_registered_on: "2026-09-25",
      correctness_source: null, target_approach: "guarded_rag",
      recommendation: { verdict: "limited_pilot", headline: "Proceed to a limited pilot", summary: "" },
      approaches: { guarded_rag: { label: "Guarded RAG", criteria: [], passes: 0, total: 0, human_reviews: { reviewed: 4, changed: 0 } } },
      comparison: null, next_experiments: [], rollout_tests: [], limitations: [],
    };
    mockFetch({ "/api/decision": { live_available: true, decision }, "/api/runs": [] });
    render(<DecisionView runParam={null} />);
    expect(await screen.findByText("Proceed to a limited pilot")).toBeInTheDocument();
    expect(screen.queryByText(/Human review changed/)).toBeNull();
  });

  it("says when the verdict rests on human-reviewed labels", async () => {
    const decision = {
      run_id: "live-1", run_mode: "live", run_created_at: "", model_config: {}, evaluated_split: "held_out", n_cases: 45,
      criteria_version: "1.1.0", criteria_hash: "abc", criteria_changed_since_run: false, criteria_registered_on: "2026-09-25",
      correctness_source: null, target_approach: "guarded_rag",
      recommendation: { verdict: "limited_pilot", headline: "Proceed to a limited pilot", summary: "" },
      approaches: {
        guarded_rag: {
          label: "Guarded RAG", criteria: [], passes: 0, total: 0,
          label_sources: { human: 3, model_judge: 29, deterministic: 3 }, human_reviews: { reviewed: 3, changed: 2 },
        },
      },
      comparison: null, next_experiments: [], rollout_tests: [], limitations: [],
    };
    mockFetch({ "/api/decision": { live_available: true, decision }, "/api/runs": [] });
    render(<DecisionView runParam={null} />);
    expect(await screen.findByText(/changed correctness labels: 2 of 35 for Guarded RAG\. 1 more review\(s\) confirmed/)).toBeInTheDocument();
  });
});

describe("ErrorBoundary retry", () => {
  it("offers Try again, which re-renders the view", () => {
    let fail = true;
    const Flaky = () => {
      if (fail) throw new Error("transient");
      return <p>recovered</p>;
    };
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <ErrorBoundary resetKey="ask?">
        <Flaky />
      </ErrorBoundary>,
    );
    fail = false;
    act(() => screen.getByRole("button", { name: "Try again" }).click());
    expect(screen.getByText("recovered")).toBeInTheDocument();
  });
});
