"""Approach 1: keyword search with deterministic answer extraction. No model, no model cost."""

from __future__ import annotations

import re
import time

from ..citations import validate_citation
from ..retrieval import tokenize
from ..schemas import ApproachResponse
from .base import ABSTAIN_MESSAGE, Approach, elapsed_ms

SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")


def split_sentences(text: str) -> list[str]:
    return [s.strip(" -") for s in SENTENCE_RE.split(text) if len(s.strip(" -")) > 3]


class KeywordSearch(Approach):
    name = "search"

    def run(self, question: str, role: str) -> ApproachResponse:
        start = time.perf_counter()
        hits = self.retrieve(question, role)
        resp = self.new_response(hits)
        # No model call, so zero tokens and zero cost are known facts, not assumptions.
        resp.input_tokens = resp.output_tokens = 0
        resp.estimated_cost_usd = 0.0

        min_score = self.config["min_score"]
        top = hits[0].score if hits else 0.0
        if top < min_score:
            resp.status = "abstained"
            resp.answer = ABSTAIN_MESSAGE
            resp.guard_reason = f"best BM25 score {top:.2f} is below the threshold {min_score}"
            resp.latency_ms = elapsed_ms(start)
            return resp

        # Score every sentence of the retrieved passages by the IDF weight of the query terms it
        # contains, scaled by its passage's relative BM25 score; answer with the best one.
        idf = self.index(role).idf
        query_terms = set(tokenize(question))
        best: tuple[float, int, int, list[str]] | None = None  # (score, hit index, sentence index, sentences)
        for hi, h in enumerate(hits):
            sentences = split_sentences(h.passage.text)
            for si, sentence in enumerate(sentences):
                overlap = sum(idf.get(t, 0.0) for t in query_terms & set(tokenize(sentence)))
                score = overlap * (h.score / top)
                if best is None or score > best[0]:
                    best = (score, hi, si, sentences)
        assert best is not None  # hits is non-empty and every passage has at least one sentence
        _, hi, si, sentences = best
        chosen = [sentences[si]]
        if self.config.get("max_sentences", 1) > 1 and si + 1 < len(sentences):
            following = sentences[si + 1]
            if query_terms & set(tokenize(following)):
                chosen.append(following)

        passage = hits[hi].passage
        resp.answer = f"{' '.join(chosen)} [{passage.passage_id}]"
        resp.citations = [
            validate_citation(
                self.ctx.corpus, role, passage.document_id, passage.passage_id, {h.passage.passage_id for h in hits}
            )
        ]
        resp.status = "answered"
        resp.latency_ms = elapsed_ms(start)
        return resp
