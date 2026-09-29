"""Parse inline citations like [NS-TRV-2026#3] and validate them against what the user may see.

Document IDs are matched case-insensitively everywhere, so `[ns-hr-001#2]` is treated exactly
like `[NS-HR-001#2]`. A document the user may not read is never named back to them: its
citation is replaced by a placeholder and any mention in the answer text is redacted. A
corpus-shaped ID that does not exist is treated the same way, so the difference between
"restricted" and "missing" cannot be used to probe which restricted IDs exist.
"""

from __future__ import annotations

import re

from .access import can_access
from .corpus import Corpus
from .schemas import Citation

RESTRICTED = "[restricted]"  # stands in for a restricted document's ID in citation lists
REDACTED_MENTION = "restricted document"  # replaces a restricted ID inside answer text
HIDDEN_REASONS = ("unauthorized", "unknown_document")  # shown to the user as one public reason
PUBLIC_HIDDEN_REASON = "unavailable"
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


def _is_hidden_id(token: str, corpus: Corpus, role: str) -> bool:
    """A restricted document, or an unknown ID shaped like a corpus ID (same prefix, e.g. `NS-`)."""
    doc_id = token.upper()
    doc = corpus.get(doc_id)
    if doc is None:
        return doc_id.split("-", 1)[0] in {d.split("-", 1)[0] for d in corpus.documents}
    return not can_access(role, doc)


def hidden_mentions(text: str, corpus: Corpus, role: str) -> set[str]:
    """Restricted or nonexistent corpus-style IDs named anywhere in the text."""
    return {t.upper() for t in ID_TOKEN_RE.findall(text) if _is_hidden_id(t, corpus, role)}


def redact_restricted_mentions(text: str, corpus: Corpus, role: str) -> str:
    """Replace every mention of a document the role may not read, or that does not exist, with a placeholder."""

    def repl(m: re.Match) -> str:
        return REDACTED_MENTION if _is_hidden_id(m.group(1), corpus, role) else m.group(0)

    return ID_TOKEN_RE.sub(repl, text)


# "NS-ZZ-999 (unknown_document)" or "[restricted] (unauthorized)" inside a warning or error string.
_HIDDEN_REASON_RE = re.compile(
    r"(?:"
    + re.escape(RESTRICTED)
    + r"|[A-Za-z]{2,}(?:-[A-Za-z0-9]+)+(?:#\d+)?) \((?:"
    + "|".join(HIDDEN_REASONS)
    + r")\)"
)


def public_reason_text(text: str) -> str:
    """Rewrite invalid-citation notes so a restricted and a nonexistent document read the same."""
    return _HIDDEN_REASON_RE.sub(f"{RESTRICTED} ({PUBLIC_HIDDEN_REASON})", text)
