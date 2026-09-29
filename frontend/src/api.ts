import type {
  AppConfig,
  ApproachId, ApproachResponse, CaseDetail, CaseRow, DecisionResponse, DocumentDetail, Health, RunDetail, RunSummary,
} from "./types";

/** A non-2xx response. `status` is 0 when the server could not be reached at all. */
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

function detailMessage(detail: unknown, status: number): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "error" in detail) return String((detail as { error: unknown }).error);
  if (Array.isArray(detail)) {
    // FastAPI validation errors: name the field and the reason, e.g. "reviewer: String should have at least 1 character".
    const first = detail[0] as { loc?: unknown[]; msg?: string } | undefined;
    const field = first?.loc?.filter((p) => p !== "body").join(".");
    return first?.msg ? `The request was not valid${field ? ` (${field})` : ""}: ${first.msg}.` : "The request was not valid.";
  }
  return `The server returned HTTP ${status}.`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  } catch {
    throw new ApiError(0, "Cannot reach the API. Is the backend running on port 8000?");
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, detailMessage(body?.detail ?? body, res.status));
  return body as T;
}

const qs = (params: Record<string, string | undefined>) => {
  const p = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => v && p.set(k, v));
  const s = p.toString();
  return s ? `?${s}` : "";
};

export const api = {
  health: () => request<Health>("/api/health"),
  config: () => request<AppConfig>("/api/config"),
  samples: () => request<{ case_id: string; question: string; role: string; category: string }[]>("/api/sample-questions"),
  ask: (question: string, role: string, approaches: ApproachId[]) =>
    request<{ mode: string; fixture: boolean; role: string; responses: ApproachResponse[] }>("/api/ask", {
      method: "POST",
      body: JSON.stringify({ question, role, approaches }),
    }),
  document: (id: string, role: string) => request<DocumentDetail>(`/api/documents/${encodeURIComponent(id)}${qs({ role })}`),
  runs: () => request<RunSummary[]>("/api/runs"),
  run: (id: string) => request<RunDetail>(`/api/runs/${encodeURIComponent(id)}`),
  cases: (id: string, filters: Record<string, string | undefined>) =>
    request<CaseRow[]>(`/api/runs/${encodeURIComponent(id)}/cases${qs(filters)}`),
  caseDetail: (id: string, caseId: string) =>
    request<CaseDetail>(`/api/runs/${encodeURIComponent(id)}/cases/${encodeURIComponent(caseId)}`),
  review: (responseId: string, verdict: string, note: string, reviewer: string) =>
    request(`/api/responses/${encodeURIComponent(responseId)}/reviews`, {
      method: "POST",
      body: JSON.stringify({ verdict, note: note || null, reviewer }),
    }),
  decision: (runId?: string) => request<DecisionResponse>(`/api/decision${qs({ run_id: runId })}`),
};
