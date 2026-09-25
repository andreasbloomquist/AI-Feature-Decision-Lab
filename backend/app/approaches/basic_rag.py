"""Approach 2: basic RAG. Retrieve, then ask the model to answer and cite.

Citations are parsed and validated. Invalid ones are flagged as unverified rather than trusted,
but the answer itself is not withheld: that is the difference from guarded RAG.
"""

from __future__ import annotations

import re
import time

from ..citations import redact_restricted_mentions, validate_all
from ..schemas import ApproachResponse
from .base import Approach

# Basic RAG has no explicit abstention contract, so a plain-language "I can't find this" reply is
# recognised heuristically. It only counts as an abstention when no valid citation is present.
ABSTENTION_PATTERNS = re.compile(
    r"(don't|do not|doesn't|does not|cannot|can't|unable to) "
    r"(know|find|contain|mention|address|cover|include|specify|answer)"
    r"|no information|not (covered|mentioned|specified|addressed|included)",
    re.IGNORECASE,
)


def looks_like_abstention(text: str) -> bool:
    return bool(ABSTENTION_PATTERNS.search(text))


class BasicRAG(Approach):
    name = "basic_rag"

    def run(self, question: str, role: str) -> ApproachResponse:
        start = time.perf_counter()
        hits = self.retrieve(question, role)
        resp = self.new_response(hits)
        result = self.generate(resp, hits, question, role, start)
        if result is None:
            return resp

        context_ids = {h.passage.passage_id for h in hits}
        resp.citations = validate_all(self.ctx.corpus, role, result.text, context_ids)
        resp.answer = redact_restricted_mentions(result.text.strip(), self.ctx.corpus, role)
        if not resp.answer:
            resp.status = "error"
            resp.error = "empty_output: the model returned no text"
            return resp

        has_valid_citation = any(c.valid for c in resp.citations)
        if not has_valid_citation and looks_like_abstention(resp.answer):
            resp.status = "abstained"
            return resp

        resp.status = "answered"
        if not resp.citations:
            resp.warnings.append("no citations in answer")
        invalid = [c for c in resp.citations if not c.valid]
        if invalid:
            resp.warnings.append("invalid citations: " + ", ".join(f"{c.document_id} ({c.reason})" for c in invalid))
        return resp
