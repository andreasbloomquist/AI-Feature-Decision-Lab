import { APPROACH_LABELS, REASON_COPY, explainStatus, measurementText, segmentAnswer } from "../format";
import { useOpenSource } from "../sourceContext";
import type { ApproachResponse, Citation } from "../types";
import { StatusBadge } from "./StatusBadge";

const APPROACH_BLURB: Record<string, string> = {
  search: "Keyword match, no AI",
  basic_rag: "AI answer from retrieved policies",
  guarded_rag: "AI answer with strict source checks",
};

function findCitation(citations: Citation[], id: string): Citation | undefined {
  const [doc, n] = id.split("#");
  return citations.find((c) => c.passage_id === id) ?? citations.find((c) => c.document_id === doc && (!n || !c.valid));
}

export function AnswerCard({ response, role, showMeta = true }: { response: ApproachResponse; role: string; showMeta?: boolean }) {
  const openSource = useOpenSource();
  const r = response;
  const explanation = explainStatus(r);
  const m = measurementText(r);
  const validCitations = r.citations.filter((c) => c.valid);
  const invalidCitations = r.citations.filter((c) => !c.valid);
  const numbered = new Map(validCitations.map((c, i) => [c.passage_id ?? c.document_id, i + 1]));
  const showAnswer = r.status === "answered" && r.answer;

  return (
    <article className={`answer-card status-${r.status}`} data-testid={`answer-${r.approach}`}>
      <header className="answer-head">
        <div>
          <h3>{APPROACH_LABELS[r.approach]}</h3>
          <p className="muted small">{APPROACH_BLURB[r.approach]}</p>
        </div>
        <div className="answer-badges">
          {r.fixture && <span className="badge badge-demo" title="Saved example response, not a live model output">Demo response</span>}
          <StatusBadge status={r.status} />
        </div>
      </header>

      {showAnswer && (
        <p className="answer-text">
          {segmentAnswer(r.answer).map((seg, i) => {
            if (seg.kind === "text") return <span key={i}>{seg.text}</span>;
            return seg.ids.map((id) => {
              const c = findCitation(r.citations, id);
              if (c?.valid) {
                const n = numbered.get(c.passage_id ?? c.document_id);
                return (
                  <button
                    key={`${i}-${id}`}
                    className="cite-chip"
                    title={`${c.title} — open source`}
                    onClick={() => openSource({ documentId: c.document_id, passageId: c.passage_id, role })}
                  >
                    {n}
                  </button>
                );
              }
              return (
                <span key={`${i}-${id}`} className="cite-chip cite-invalid" title={c?.reason ? REASON_COPY[c.reason] ?? c.reason : "unverified citation"}>
                  unverified
                </span>
              );
            });
          })}
        </p>
      )}
      {!showAnswer && explanation && <p className="explain">{explanation}</p>}
      {!showAnswer && r.status === "abstained" && r.approach === "basic_rag" && r.answer && (
        <p className="muted small">Model reply: “{r.answer}”</p>
      )}

      {validCitations.length > 0 && (
        <div className="sources">
          <h4>Sources</h4>
          <ol>
            {validCitations.map((c) => (
              <li key={c.passage_id ?? c.document_id}>
                <button className="link" onClick={() => openSource({ documentId: c.document_id, passageId: c.passage_id, role })}>
                  {c.title}
                </button>{" "}
                <span className="mono muted">{c.passage_id}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
      {invalidCitations.length > 0 && (
        <div className="unverified" role="note">
          <strong>Unverified citations — not shown as sources</strong>
          <ul>
            {invalidCitations.map((c, i) => (
              <li key={i}>
                <span className="mono">{c.reason === "unauthorized" ? "[restricted]" : c.passage_id ?? c.document_id}</span>{" "}
                {c.reason ? REASON_COPY[c.reason] ?? c.reason : ""}
              </li>
            ))}
          </ul>
        </div>
      )}
      {r.warnings && r.warnings.length > 0 && r.status === "answered" && (
        <p className="warn-line small">⚠ {r.warnings.join("; ")}</p>
      )}

      {showMeta && (
        <footer className="answer-meta small">
          <span title="Wall-clock time for this approach">Latency: {m.latency}</span>
          <span title="Estimated from recorded token usage and config/pricing.yaml">Cost: {m.cost}</span>
          <span>Retrieved: {r.retrieved_document_ids.length} docs</span>
          {r.error && <span className="mono err-code">{r.error.split(":")[0]}</span>}
        </footer>
      )}
    </article>
  );
}
