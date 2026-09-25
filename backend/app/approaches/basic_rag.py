"""Approach 2: basic RAG. Retrieve, then ask the model to answer and cite. Citations are parsed and
checked, and invalid ones are flagged rather than trusted, but the answer is not withheld."""
from __future__ import annotations

import re
import time

from ..citations import redact_unauthorized_markers, validate_all
from ..llm import LLMError, fixture_key
from ..pricing import estimate_cost_usd
from ..prompts import load_prompt
from ..schemas import ApproachResponse
from .base import Approach, format_passages

ABSTENTION_PATTERNS = re.compile(
    r"(don't|do not|doesn't|does not|cannot|can't|unable to) (know|find|contain|mention|address|cover|include|specify|answer)"
    r"|no information|not (covered|mentioned|specified|addressed|included)",
    re.IGNORECASE,
)


def looks_like_abstention(text: str) -> bool:
    return bool(ABSTENTION_PATTERNS.search(text))


class BasicRAG(Approach):
    name = "basic_rag"

    def run(self, question: str, role: str) -> ApproachResponse:
        start = time.perf_counter()
        prompt = load_prompt(self.config["prompt_file"])
        hits = self.retrieve(question, role)
        resp = self.base_response(hits, start)
        resp.prompt_version = prompt.version
        llm = self.ctx.llm
        resp.model = llm.model if llm else None
        resp.fixture = bool(llm and llm.is_fixture)
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
        context_ids = {h.passage.passage_id for h in hits}
        citations = validate_all(self.ctx.corpus, role, result.text, context_ids)
        resp.citations = citations
        resp.answer = redact_unauthorized_markers(result.text.strip(), citations)
        if not resp.answer:
            resp.status = "error"
            resp.error = "empty_output: the model returned no text"
            return resp
        valid = [c for c in citations if c.valid]
        if not valid and looks_like_abstention(resp.answer):
            resp.status = "abstained"
        else:
            resp.status = "answered"
            if not citations:
                resp.warnings.append("no citations in answer")
            invalid = [c for c in citations if not c.valid]
            if invalid:
                resp.warnings.append(
                    "invalid citations: " + ", ".join(f"{c.document_id} ({c.reason})" for c in invalid)
                )
        return resp
