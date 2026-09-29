import { useRef, useState } from "react";
import { api } from "../api";
import { AnswerCard } from "../components/AnswerCard";
import { ErrorNotice } from "../components/Notice";
import { useConfig } from "../configContext";
import { APPROACHES, APPROACH_LABELS } from "../format";
import type { ApproachId, ApproachResponse } from "../types";
import { useAsync } from "../useAsync";

const DEFAULT_QUESTION = "Can I expense a client dinner without a receipt?";

export function AskView({ initialQuestion, initialRole }: { initialQuestion: string | null; initialRole: string | null }) {
  const config = useConfig();
  const [question, setQuestion] = useState(initialQuestion ?? DEFAULT_QUESTION);
  const [role, setRole] = useState(initialRole ?? "employee");
  // A deep link can carry any role string; fall back to Employee rather than show one role and send another.
  const roles = config?.roles ?? [];
  const effectiveRole = roles.length && !roles.some((r) => r.id === role) ? "employee" : role;
  const [selected, setSelected] = useState<ApproachId[]>([...APPROACHES]);
  const [results, setResults] = useState<{ question: string; role: string; responses: ApproachResponse[] } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const samples = useAsync("samples", api.samples);
  const latestRequest = useRef(0);

  const submit = async (q = question, r = effectiveRole) => {
    if (q.trim().length < 3 || !selected.length) return;
    const requestId = ++latestRequest.current;
    setLoading(true);
    setError(null);
    try {
      const res = await api.ask(q, r, selected);
      // Ignore a slow answer to an earlier question that arrives after a newer one was asked.
      if (requestId === latestRequest.current) setResults({ question: q, role: res.role, responses: res.responses });
    } catch (e) {
      if (requestId === latestRequest.current) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (requestId === latestRequest.current) setLoading(false);
    }
  };

  const toggle = (a: ApproachId) => setSelected((s) => (s.includes(a) ? s.filter((x) => x !== a) : APPROACHES.filter((x) => s.includes(x) || x === a)));

  return (
    <div className="view">
      <section className="panel ask-panel">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <label htmlFor="q" className="field-label">Policy question</label>
          <div className="ask-row">
            <input id="q" className="ask-input" value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="e.g. Who approves travel over $2,000?" maxLength={500} />
            <button className="btn btn-primary" disabled={loading || !selected.length}>{loading ? "Asking…" : "Ask"}</button>
          </div>
          <div className="ask-controls">
            <label className="inline-field">
              <span className="field-label">Asking as</span>
              <select value={effectiveRole} onChange={(e) => setRole(e.target.value)}>
                {roles.map((r) => (
                  <option key={r.id} value={r.id}>{r.label}</option>
                ))}
              </select>
            </label>
            <fieldset className="approach-toggles">
              <legend className="field-label">Approaches</legend>
              {APPROACHES.map((a) => (
                <label key={a} className="check">
                  <input type="checkbox" checked={selected.includes(a)} onChange={() => toggle(a)} /> {APPROACH_LABELS[a]}
                </label>
              ))}
            </fieldset>
          </div>
        </form>
        {config?.settings.mode === "fixture" && samples.data && samples.data.length > 0 && (
          <div className="samples">
            <span className="muted small">Demo mode has saved AI responses for these questions (Search always runs live):</span>
            <div className="sample-list">
              {samples.data.map((s) => (
                <button
                  key={s.case_id}
                  className="sample"
                  onClick={() => {
                    setQuestion(s.question);
                    setRole(s.role);
                    submit(s.question, s.role);
                  }}
                >
                  {s.question}
                  {s.role !== "employee" && <span className="role-tag">{s.role}</span>}
                </button>
              ))}
            </div>
          </div>
        )}
      </section>

      {error && <ErrorNotice error={error} />}
      {results && (
        <p className="muted small answers-for" aria-live="polite">
          Answers to “{results.question}” as {config?.roles.find((r) => r.id === results.role)?.label ?? results.role}
        </p>
      )}
      {results && (
        <section className={`answers answers-${results.responses.length}`}>
          {results.responses.map((r) => (
            <AnswerCard key={r.approach} response={r} role={results.role} />
          ))}
        </section>
      )}
      {!results && !error && (
        <p className="muted empty-hint">Ask a question to compare how each approach answers it for the selected role. Click a numbered citation to open the exact source passage.</p>
      )}
    </div>
  );
}
