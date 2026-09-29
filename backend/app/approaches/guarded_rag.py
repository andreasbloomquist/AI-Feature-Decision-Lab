"""Approach 3: guarded RAG.

Same authorized, active-only retrieval as the other approaches, plus:
- abstain without calling the model when retrieval evidence is below a floor;
- a strict answer contract (answer only from passages, cite every claim, abstain otherwise);
- post-generation validation: every cited passage must be in the retrieved, authorized, active set,
  markers must be well-formed, and the answer may not name a document the role cannot read.
If validation fails the answer is withheld and the reason recorded. There is no second model
call to "fix" an unsupported answer.
"""

from __future__ import annotations

import re
import time

from ..citations import (
    HIDDEN_REASONS,
    RESTRICTED,
    hidden_mentions,
    malformed_markers,
    parse_citation_markers,
    validate_all,
)
from ..corpus import Corpus
from ..schemas import ApproachResponse, Citation
from .base import ABSTAIN_MESSAGE, Approach, elapsed_ms
from .search import split_sentences

FORMAT_RE = re.compile(r"STATUS:\s*(ANSWERED|ABSTAINED)\s*\n+\s*ANSWER:\s*(.*)", re.IGNORECASE | re.DOTALL)
WITHHELD_MESSAGE = "This answer was withheld because it cited a source that failed validation."


def parse_guarded_output(text: str) -> tuple[str, str] | None:
    """(STATUS, answer) from the two-line contract, or None if the reply does not follow it."""
    m = FORMAT_RE.search(text or "")
    return (m.group(1).upper(), m.group(2).strip()) if m else None


def validation_failures(answer: str, citations: list[Citation], corpus: Corpus, role: str) -> list[str]:
    """Reasons to withhold an answer. A restricted document is reported only as a placeholder.

    Naming an accessible document in prose is fine (the 2026 travel policy itself says it replaces
    NS-TRV-2025), but naming a document the role may not read is a disclosure, however it is written.
    A nonexistent corpus-style ID is handled exactly like a restricted one, so the two cannot be told apart.
    """
    failures = [f"{c.document_id} ({c.reason})" for c in citations if not c.valid]
    failures += ["malformed citation"] * len(malformed_markers(answer))
    if hidden_mentions(answer, corpus, role) and not any(c.reason in HIDDEN_REASONS for c in citations):
        failures.append(f"{RESTRICTED} (named in the answer)")
    return failures


class GuardedRAG(Approach):
    name = "guarded_rag"

    def run(self, question: str, role: str) -> ApproachResponse:
        start = time.perf_counter()
        hits = self.retrieve(question, role)
        resp = self.new_response(hits)

        floor = self.config.get("retrieval_floor", 0)
        top = hits[0].score if hits else 0.0
        if top < floor:
            # No model call: zero tokens and zero cost are known, and latency is real.
            resp.status = "abstained"
            resp.answer = ABSTAIN_MESSAGE
            resp.guard_reason = f"retrieval_below_floor: best score {top:.2f} < {floor}"
            resp.input_tokens = resp.output_tokens = 0
            resp.estimated_cost_usd = 0.0
            resp.latency_ms = elapsed_ms(start)
            return resp

        result = self.generate(resp, hits, question, role, start)
        if result is None:
            return resp

        parsed = parse_guarded_output(result.text)
        if parsed is None:
            resp.status = "error"
            resp.error = "unparseable_output: response did not follow the STATUS/ANSWER contract"
            return resp
        status, answer = parsed
        if status == "ABSTAINED":
            # Show the standard message; the model's own wording stays in raw_output for reviewers.
            resp.status = "abstained"
            resp.guard_reason = "model_abstained"
            resp.answer = ABSTAIN_MESSAGE
            return resp
        return self._validate(resp, answer, {h.passage.passage_id for h in hits}, role)

    def _validate(self, resp: ApproachResponse, answer: str, context_ids: set[str], role: str) -> ApproachResponse:
        corpus = self.ctx.corpus
        rules = self.config.get("validation", {})
        citations = validate_all(corpus, role, answer, context_ids)

        failures = validation_failures(answer, citations, corpus, role)
        if failures and rules.get("reject_invalid_citations", True):
            resp.status = "error"
            resp.answer = WITHHELD_MESSAGE
            resp.citations = []  # never surface a failed source
            resp.error = "citation_validation_failed: " + ", ".join(failures)
            resp.guard_reason = "citation_validation_failed"
            return resp
        if not citations and rules.get("require_citations", True):
            resp.status = "abstained"
            resp.answer = ABSTAIN_MESSAGE
            resp.guard_reason = "no_citations: the model answered without citing a passage"
            return resp

        resp.status = "answered"
        resp.citations = citations
        resp.answer = answer
        min_words = rules.get("uncited_sentence_min_words", 8)
        uncited = [s for s in split_sentences(answer) if len(s.split()) >= min_words and not parse_citation_markers(s)]
        if uncited:
            resp.warnings.append(f"{len(uncited)} sentence(s) without a citation")
        return resp
