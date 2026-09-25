"""Approach 1: keyword search with deterministic answer extraction. No model, no model cost."""
from __future__ import annotations

import re
import time

from ..citations import validate_citation
from ..retrieval import tokenize
from ..schemas import ApproachResponse
from .base import ABSTAIN_MESSAGE, Approach

SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")


def split_sentences(text: str) -> list[str]:
    return [s.strip(" -") for s in SENTENCE_RE.split(text) if len(s.strip(" -")) > 3]


class KeywordSearch(Approach):
    name = "search"

    def run(self, question: str, role: str) -> ApproachResponse:
        start = time.perf_counter()
        hits = self.retrieve(question, role)
        index = self.ctx.retriever.index_for(role)
        resp = self.base_response(hits, start)
        resp.model = None
        resp.input_tokens = 0  # no model call: zero tokens and zero cost are known, not assumed
        resp.output_tokens = 0
        resp.estimated_cost_usd = 0.0

        top = hits[0].score if hits else 0.0
        if not hits or top < self.config["min_score"]:
            resp.status = "abstained"
            resp.answer = ABSTAIN_MESSAGE
            resp.guard_reason = f"best BM25 score {top:.2f} is below the threshold {self.config['min_score']}"
            resp.latency_ms = round((time.perf_counter() - start) * 1000, 1)
            return resp

        q = set(tokenize(question))
        best = None  # (score, hit, sentence_index, sentences)
        for h in hits:
            sentences = split_sentences(h.passage.text)
            for i, s in enumerate(sentences):
                overlap = sum(index.idf.get(t, 0.0) for t in q & set(tokenize(s)))
                score = overlap * (h.score / top)
                if best is None or score > best[0]:
                    best = (score, h, i, sentences)
        _, hit, i, sentences = best
        chosen = [sentences[i]]
        if self.config.get("max_sentences", 1) > 1 and i + 1 < len(sentences):
            nxt = sentences[i + 1]
            if q & set(tokenize(nxt)):
                chosen.append(nxt)
        pid = hit.passage.passage_id
        resp.answer = f"{' '.join(chosen)} [{pid}]"
        resp.citations = [
            validate_citation(self.ctx.corpus, role, hit.passage.document_id, pid, {h.passage.passage_id for h in hits})
        ]
        resp.status = "answered"
        resp.latency_ms = round((time.perf_counter() - start) * 1000, 1)
        return resp
