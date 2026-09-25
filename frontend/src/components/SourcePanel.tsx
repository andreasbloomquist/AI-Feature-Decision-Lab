import { useEffect, useRef, useState } from "react";
import { ApiError, api } from "../api";
import type { SourceTarget } from "../sourceContext";
import type { DocumentDetail } from "../types";

export function SourcePanel({ target, onClose }: { target: SourceTarget; onClose: () => void }) {
  const [doc, setDoc] = useState<DocumentDetail | null>(null);
  const [error, setError] = useState<{ status: number; message: string } | null>(null);
  const highlighted = useRef<HTMLElement | null>(null);

  useEffect(() => {
    setDoc(null);
    setError(null);
    api
      .document(target.documentId, target.role)
      .then(setDoc)
      .catch((e: ApiError) =>
        setError({
          status: e.status,
          message: e.status === 403 ? "Your role can't view this document." : e.status === 404 ? "Document not found." : "Could not load the document.",
        }),
      );
  }, [target.documentId, target.role]);

  useEffect(() => {
    highlighted.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [doc]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside className="drawer" role="dialog" aria-label="Source document" onClick={(e) => e.stopPropagation()}>
        <header className="drawer-head">
          <span className="eyebrow">Source · viewing as {target.role}</span>
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>
        {!doc && !error && <p className="muted">Loading…</p>}
        {error && (
          <div className={`notice ${error.status === 403 ? "notice-warn" : "notice-bad"}`}>
            <strong>{error.status === 403 ? "Restricted" : "Unavailable"}</strong>
            <p>{error.message}</p>
          </div>
        )}
        {doc && (
          <>
            <h2 className="drawer-title">{doc.title}</h2>
            {doc.status === "superseded" && (
              <div className="notice notice-warn">
                <strong>Superseded policy</strong> — replaced by <span className="mono">{doc.superseded_by}</span>. Not current policy.
              </div>
            )}
            <dl className="meta-grid">
              <dt>Document ID</dt>
              <dd className="mono">{doc.document_id}</dd>
              <dt>Owner</dt>
              <dd>{doc.owner}</dd>
              <dt>Effective</dt>
              <dd>{doc.effective_date}</dd>
              <dt>Status</dt>
              <dd>{doc.status}</dd>
              <dt>Access</dt>
              <dd>{doc.access_groups.join(", ")}</dd>
              {doc.country.length > 0 && (
                <>
                  <dt>Country</dt>
                  <dd>{doc.country.join(", ")}</dd>
                </>
              )}
              {doc.supersedes && (
                <>
                  <dt>Replaces</dt>
                  <dd className="mono">{doc.supersedes}</dd>
                </>
              )}
            </dl>
            <div className="passages">
              {doc.passages.map((p) => {
                const hit = p.passage_id === target.passageId;
                return (
                  <section
                    key={p.passage_id}
                    ref={hit ? (el) => void (highlighted.current = el) : undefined}
                    className={`passage ${hit ? "passage-hit" : ""}`}
                  >
                    <h4>
                      {p.heading} <span className="mono muted small">{p.passage_id}</span>
                      {hit && <span className="badge badge-info">Cited passage</span>}
                    </h4>
                    {p.text.split("\n").map((line, i) =>
                      line.trim() ? <p key={i}>{line.replace(/^- /, "• ")}</p> : null,
                    )}
                  </section>
                );
              })}
            </div>
          </>
        )}
      </aside>
    </div>
  );
}
