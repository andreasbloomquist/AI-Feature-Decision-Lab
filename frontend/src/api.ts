import type {
  ApproachId, ApproachResponse, CaseDetail, CaseRow, DecisionResponse, DocumentDetail, Health, Role, RunDetail, RunSummary,
} from "./types";

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(typeof detail === "string" ? detail : `HTTP ${status}`);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, body?.detail ?? body);
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
  config: () => request<{ roles: Role[]; approaches: { id: ApproachId; label: string }[]; launch_criteria: unknown }>("/api/config"),
  samples: () => request<{ case_id: string; question: string; role: string; category: string }[]>("/api/sample-questions"),
  ask: (question: string, role: string, approaches: ApproachId[]) =>
    request<{ mode: string; fixture: boolean; role: string; responses: ApproachResponse[] }>("/api/ask", {
      method: "POST",
      body: JSON.stringify({ question, role, approaches }),
    }),
  document: (id: string, role: string) => request<DocumentDetail>(`/api/documents/${encodeURIComponent(id)}${qs({ role })}`),
  runs: () => request<RunSummary[]>("/api/runs"),
  run: (id: string) => request<RunDetail>(`/api/runs/${id}`),
  cases: (id: string, filters: Record<string, string | undefined>) => request<CaseRow[]>(`/api/runs/${id}/cases${qs(filters)}`),
  caseDetail: (id: string, caseId: string) => request<CaseDetail>(`/api/runs/${id}/cases/${caseId}`),
  review: (responseId: string, verdict: string, note: string, reviewer: string) =>
    request(`/api/responses/${responseId}/reviews`, {
      method: "POST",
      body: JSON.stringify({ verdict, note: note || null, reviewer: reviewer || null }),
    }),
  decision: (runId?: string) => request<DecisionResponse>(`/api/decision${qs({ run_id: runId })}`),
};
