import { useEffect, useRef } from "react";
import { api } from "../api";
import type { SourceTarget } from "../sourceContext";
import { useAsync } from "../useAsync";
import { Loading } from "./Notice";

/** Modal drawer showing a cited document, fetched with the asker's role so authorization applies. */
export function SourcePanel({ target, onClose }: { target: SourceTarget; onClose: () => void }) {
  const doc = useAsync(`${target.documentId}:${target.role}`, () => api.document(target.documentId, target.role));
  const dialog = useRef<HTMLElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const highlighted = useRef<HTMLElement | null>(null);

  // Move focus into the dialog, keep Tab inside it, and give focus back to the citation on close.
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    closeButton.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key !== "Tab" || !dialog.current) return;
      const focusable = dialog.current.querySelectorAll<HTMLElement>("button, a[href], [tabindex]:not([tabindex='-1'])");
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      previous?.focus();
    };
  }, [onClose]);

  useEffect(() => {
    highlighted.current?.scrollIntoView?.({ block: "center", behavior: "smooth" });
  }, [doc.data]);

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside ref={dialog} className="drawer" role="dialog" aria-modal="true" aria-labelledby="source-title" onClick={(e) => e.stopPropagation()}>
        <header className="drawer-head">
          <span className="eyebrow">Source · viewing as {target.role}</span>
          <button ref={closeButton} className="icon-btn" onClick={onClose} aria-label="Close source">
            ×
          </button>
        </header>
        {doc.loading && <Loading />}
        {doc.error && (
          <div className="notice notice-warn" role="alert">
            <strong id="source-title">Not available</strong>
            <p>{doc.error}</p>
          </div>
        )}
        {doc.data && (
          <>
            <h2 id="source-title" className="drawer-title">
              {doc.data.title}
            </h2>
            {doc.data.status === "superseded" && (
              <div className="notice notice-warn">
                <strong>Superseded policy</strong> — replaced by <span className="mono">{doc.data.superseded_by}</span>. Not current policy.
              </div>
            )}
            <dl className="meta-grid">
              <dt>Document ID</dt>
              <dd className="mono">{doc.data.document_id}</dd>
              <dt>Owner</dt>
              <dd>{doc.data.owner}</dd>
              <dt>Effective</dt>
              <dd>{doc.data.effective_date}</dd>
              <dt>Status</dt>
              <dd>{doc.data.status}</dd>
              <dt>Access</dt>
              <dd>{doc.data.access_groups.join(", ")}</dd>
              {doc.data.country.length > 0 && (
                <>
                  <dt>Country</dt>
                  <dd>{doc.data.country.join(", ")}</dd>
                </>
              )}
              {doc.data.supersedes && (
                <>
                  <dt>Replaces</dt>
                  <dd className="mono">{doc.data.supersedes}</dd>
                </>
              )}
            </dl>
            <div className="passages">
              {doc.data.passages.map((p) => {
                const hit = p.passage_id === target.passageId;
                return (
                  <section
                    key={p.passage_id}
                    ref={hit ? (el) => void (highlighted.current = el) : undefined}
                    className={`passage ${hit ? "passage-hit" : ""}`}
                    aria-current={hit ? "true" : undefined}
                  >
                    <h3 className="passage-heading">
                      {p.heading} <span className="mono muted small">{p.passage_id}</span>
                      {hit && <span className="badge badge-info">Cited passage</span>}
                    </h3>
                    {p.text.split("\n").map((line, i) => (line.trim() ? <p key={i}>{line.replace(/^- /, "• ")}</p> : null))}
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
