"""Parse inline citations like [NS-TRV-2026#3] and validate them against what the user may see.

Document IDs are matched case-insensitively everywhere, so `[ns-hr-001#2]` is treated exactly
like `[NS-HR-001#2]`. A document the user may not read is never named back to them: its
citation is replaced by a placeholder and any mention in the answer text is redacted.
"""

from __future__ import annotations

import re

from .access import can_access
from .corpus import Corpus
from .schemas import Citation

RESTRICTED = "[restricted]"  # stands in for a restricted document's ID in citation lists
REDACTED_MENTION = "restricted document"  # replaces a restricted ID inside answer text
BRACKET_RE = re.compile(r"\[([^\[\]]{2,200})\]")
# A single citation inside brackets: DOC-ID or DOC-ID#n, nothing else.
ID_RE = re.compile(r"^\s*([A-Za-z]{2,}(?:-[A-Za-z0-9]+)+)(?:#(\d+))?\s*$")
# Anything shaped like a document ID, anywhere in text.
ID_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9-])([A-Za-z]{2,}(?:-[A-Za-z0-9]+)+)(?:#\d+)?(?![A-Za-z0-9-])")


def _split_marker(content: str) -> list[str]:
    return [p for p in re.split(r"[,;]", content) if p.strip()]


def parse_citation_markers(text: str) -> list[tuple[str, str | None]]:
    """Return (document_id, passage_id | None) pairs in order of first appearance, IDs upper-cased."""
    seen: set[tuple[str, str | None]] = set()
    out: list[tuple[str, str | None]] = []
    for m in BRACKET_RE.finditer(text):
        for part in _split_marker(m.group(1)):
            idm = ID_RE.match(part)
            if not idm:
                continue
            doc_id = idm.group(1).upper()
            key = (doc_id, f"{doc_id}#{idm.group(2)}" if idm.group(2) else None)
            if key not in seen:
                seen.add(key)
                out.append(key)
    return out


def malformed_markers(text: str) -> list[str]:
    """Bracketed text that looks like a citation but does not parse, e.g. `[NS-HR-001 §2]`."""
    bad = []
    for m in BRACKET_RE.finditer(text):
        parts = _split_marker(m.group(1))
        if any(ID_TOKEN_RE.search(p) for p in parts) and not all(ID_RE.match(p) for p in parts):
            bad.append(m.group(0))
    return bad


def mentioned_document_ids(text: str, corpus: Corpus) -> set[str]:
    """Corpus document IDs named anywhere in the text, inside or outside citation brackets."""
    return {t.upper() for t in ID_TOKEN_RE.findall(text)} & set(corpus.documents)


def validate_citation(
    corpus: Corpus, role: str, document_id: str, passage_id: str | None, context_passage_ids: set[str]
) -> Citation:
    doc = corpus.get(document_id)
    if doc is None:
        return Citation(document_id, passage_id, None, False, "unknown_document")
    if not can_access(role, doc):
        # Never echo the ID or title of a document the user may not see.
        return Citation(RESTRICTED, None, None, False, "unauthorized")
    if not doc.is_active:
        return Citation(document_id, passage_id, doc.title, False, "superseded")
    if passage_id is not None and corpus.passage(passage_id) is None:
        return Citation(document_id, passage_id, doc.title, False, "unknown_passage")
    in_doc = sorted(
        (p for p in context_passage_ids if p.startswith(document_id + "#")),
        key=lambda p: int(p.rsplit("#", 1)[1]),
    )
    if passage_id is None and in_doc:
        # Document-level citation: point at the first passage of that document the model was given.
        passage_id = in_doc[0]
    if passage_id not in context_passage_ids:
        return Citation(document_id, passage_id, doc.title, False, "not_in_context")
    return Citation(document_id, passage_id, doc.title, True, None)


def validate_all(corpus: Corpus, role: str, text: str, context_passage_ids: set[str]) -> list[Citation]:
    return [validate_citation(corpus, role, d, p, context_passage_ids) for d, p in parse_citation_markers(text)]


def redact_restricted_mentions(text: str, corpus: Corpus, role: str) -> str:
    """Replace every mention of a document the role may not read with a placeholder."""

    def repl(m: re.Match) -> str:
        doc = corpus.get(m.group(1).upper())
        return REDACTED_MENTION if doc is not None and not can_access(role, doc) else m.group(0)

    return ID_TOKEN_RE.sub(repl, text)
