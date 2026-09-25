import { useEffect, useState } from "react";
import { api } from "../api";
import { AnswerCard } from "../components/AnswerCard";
import { APPROACHES, APPROACH_LABELS } from "../format";
import type { ApproachId, ApproachResponse, Health, Role } from "../types";

export function AskView({ health, roles }: { health: Health | null; roles: Role[] }) {
  const [question, setQuestion] = useState("Can I expense a client dinner without a receipt?");
  const [role, setRole] = useState("employee");
  const [selected, setSelected] = useState<ApproachId[]>([...APPROACHES]);
  const [samples, setSamples] = useState<{ question: string; role: string; case_id: string }[]>([]);
  const [results, setResults] = useState<{ role: string; responses: ApproachResponse[] } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.samples().then(setSamples).catch(() => setSamples([]));
  }, []);

  const submit = async (q = question, r = role) => {
    if (q.trim().length < 3 || !selected.length) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.ask(q, r, selected);
      setResults({ role: res.role, responses: res.responses });
    } catch {
      setError("The server did not respond. Is the backend running on port 8000?");
    } finally {
      setLoading(false);
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
              <select value={role} onChange={(e) => setRole(e.target.value)} aria-label="User role">
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
        {health?.mode === "fixture" && samples.length > 0 && (
          <div className="samples">
            <span className="muted small">Demo mode has saved AI responses for these questions (Search always runs live):</span>
            <div className="sample-list">
              {samples.map((s) => (
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

      {error && <div className="notice notice-bad">{error}</div>}
      {results && (
        <section className={`answers answers-${results.responses.length}`} aria-live="polite">
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
