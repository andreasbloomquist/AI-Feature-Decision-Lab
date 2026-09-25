"""Approach 3: guarded RAG.

Same authorized, active-only retrieval, plus:
- abstain without calling the model when retrieval evidence is below a floor;
- a strict answer contract (answer only from passages, cite every claim, abstain otherwise);
- post-generation validation: every cited passage must be in the retrieved, authorized, active set.
  If validation fails the answer is withheld and the reason recorded. There is no second
  unrestricted model call to "fix" an unsupported answer.
"""
from __future__ import annotations

import re
import time

from ..citations import BRACKET_RE, validate_all
from ..llm import LLMError, fixture_key
from ..pricing import estimate_cost_usd
from ..prompts import load_prompt
from ..schemas import ApproachResponse
from .base import ABSTAIN_MESSAGE, Approach, format_passages
from .search import split_sentences

FORMAT_RE = re.compile(r"STATUS:\s*(ANSWERED|ABSTAINED)\s*\n+\s*ANSWER:\s*(.*)", re.IGNORECASE | re.DOTALL)


def parse_guarded_output(text: str) -> tuple[str, str] | None:
    m = FORMAT_RE.search(text or "")
    if not m:
        return None
    return m.group(1).upper(), m.group(2).strip()


class GuardedRAG(Approach):
    name = "guarded_rag"

    def run(self, question: str, role: str) -> ApproachResponse:
        start = time.perf_counter()
        prompt = load_prompt(self.config["prompt_file"])
        hits = self.retrieve(question, role)
        resp = self.base_response(hits, start)
        resp.prompt_version = prompt.version
        llm = self.ctx.llm
        resp.model = llm.model if llm else None
        resp.fixture = bool(llm and llm.is_fixture)

        floor = self.config.get("retrieval_floor", 0)
        top = hits[0].score if hits else 0.0
        if top < floor:
            # Known zero cost: no model call was made.
            resp.status = "abstained"
            resp.answer = ABSTAIN_MESSAGE
            resp.guard_reason = f"retrieval_below_floor: best score {top:.2f} < {floor}"
            resp.input_tokens = resp.output_tokens = 0
            resp.estimated_cost_usd = 0.0
            resp.fixture = False
            resp.latency_ms = round((time.perf_counter() - start) * 1000, 1)
            return resp

        system, user = prompt.render(passages=format_passages(self.ctx.corpus, hits), question=question, role=role)
        try:
            result = llm.generate(
                system, user, max_tokens=self.config["generation"]["max_tokens"],
                fixture_key=fixture_key(self.name, question, role),
            )
        except LLMError as e:
            resp.status = "error"
            resp.error = f"{e.kind}: {e.message}"
            resp.latency_ms = e.latency_ms
            return resp

        resp.raw_output = result.text
        resp.latency_ms = result.latency_ms
        resp.input_tokens, resp.output_tokens = result.input_tokens, result.output_tokens
        resp.estimated_cost_usd = estimate_cost_usd(result.model, result.input_tokens, result.output_tokens)

        parsed = parse_guarded_output(result.text)
        if parsed is None:
            resp.status = "error"
            resp.error = "unparseable_output: response did not follow the STATUS/ANSWER contract"
            return resp
        status, answer = parsed
        if status == "ABSTAINED":
            resp.status = "abstained"
            resp.guard_reason = "model_abstained"
            # Show the standard message; the model's own wording is kept in raw_output for reviewers.
            resp.answer = ABSTAIN_MESSAGE
            return resp

        context_ids = {h.passage.passage_id for h in hits}
        citations = validate_all(self.ctx.corpus, role, answer, context_ids)
        vcfg = self.config.get("validation", {})
        invalid = [c for c in citations if not c.valid]
        if invalid and vcfg.get("reject_invalid_citations", True):
            resp.status = "error"
            resp.citations = []  # never surface invalid citations as sources
            resp.answer = "This answer was withheld because it cited a source that failed validation."
            resp.error = "citation_validation_failed: " + ", ".join(
                f"{'[restricted]' if c.reason == 'unauthorized' else c.document_id} ({c.reason})" for c in invalid
            )
            resp.guard_reason = "citation_validation_failed"
            return resp
        if not citations and vcfg.get("require_citations", True):
            resp.status = "abstained"
            resp.answer = ABSTAIN_MESSAGE
            resp.guard_reason = "no_citations: the model answered without citing a passage"
            return resp

        resp.status = "answered"
        resp.citations = citations
        resp.answer = answer
        min_words = vcfg.get("uncited_sentence_min_words", 8)
        uncited = [
            s for s in split_sentences(answer)
            if len(s.split()) >= min_words and not BRACKET_RE.search(s)
        ]
        if uncited:
            resp.warnings.append(f"{len(uncited)} sentence(s) without a citation")
        return resp
