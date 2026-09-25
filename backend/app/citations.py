"""Parse inline citations like [NS-TRV-2026#3] and validate them against what the user may see."""
from __future__ import annotations

import re

from .access import can_access
from .corpus import Corpus
from .schemas import Citation

BRACKET_RE = re.compile(r"\[([^\[\]]{2,200})\]")
ID_RE = re.compile(r"^\s*([A-Z]{2,}(?:-[A-Z0-9]+)+)(?:#(\d+))?\s*$")


def parse_citation_markers(text: str) -> list[tuple[str, str | None]]:
    """Return (document_id, passage_id|None) pairs in order of first appearance."""
    seen, out = set(), []
    for m in BRACKET_RE.finditer(text):
        for part in re.split(r"[,;]", m.group(1)):
            idm = ID_RE.match(part)
            if not idm:
                continue
            doc_id = idm.group(1)
            pid = f"{doc_id}#{idm.group(2)}" if idm.group(2) else None
            key = (doc_id, pid)
            if key not in seen:
                seen.add(key)
                out.append(key)
    return out


def validate_citation(
    corpus: Corpus, role: str, document_id: str, passage_id: str | None, context_passage_ids: set[str]
) -> Citation:
    doc = corpus.get(document_id)
    if doc is None:
        return Citation(document_id, passage_id, None, False, "unknown_document")
    if not can_access(role, doc):
        # Do not reveal the title of a document the user may not see.
        return Citation(document_id, None, None, False, "unauthorized")
    if not doc.is_active:
        return Citation(document_id, passage_id, doc.title, False, "superseded")
    if passage_id is not None and corpus.passage(passage_id) is None:
        return Citation(document_id, passage_id, doc.title, False, "unknown_passage")
    in_context = (
        passage_id in context_passage_ids
        if passage_id
        else any(p.startswith(document_id + "#") for p in context_passage_ids)
    )
    if not in_context:
        return Citation(document_id, passage_id, doc.title, False, "not_in_context")
    if passage_id is None:
        # Document-level citation: point at the first passage of that document that was in context.
        passage_id = sorted(p for p in context_passage_ids if p.startswith(document_id + "#"))[0]
    return Citation(document_id, passage_id, doc.title, True, None)


def validate_all(corpus: Corpus, role: str, text: str, context_passage_ids: set[str]) -> list[Citation]:
    return [validate_citation(corpus, role, d, p, context_passage_ids) for d, p in parse_citation_markers(text)]


def redact_unauthorized_markers(text: str, citations: list[Citation]) -> str:
    """Remove markers that name documents the user may not see, so IDs are not disclosed."""
    bad = {c.document_id for c in citations if c.reason in ("unauthorized",)}
    if not bad:
        return text

    def repl(m: re.Match) -> str:
        parts = re.split(r"[,;]", m.group(1))
        kept = [p for p in parts if not (ID_RE.match(p) and ID_RE.match(p).group(1) in bad)]
        return f"[{', '.join(k.strip() for k in kept)}]" if kept else "[citation removed]"

    return BRACKET_RE.sub(repl, text)
