from __future__ import annotations

import time
from dataclasses import dataclass

from ..corpus import Corpus
from ..llm import LLMProvider
from ..retrieval import Retriever, ScoredPassage
from ..schemas import ApproachResponse

APPROACH_NAMES = ("search", "basic_rag", "guarded_rag")
APPROACH_LABELS = {"search": "Search", "basic_rag": "Basic RAG", "guarded_rag": "Guarded RAG"}

ABSTAIN_MESSAGE = (
    "I couldn't find a policy that answers this among the policies available to your role. "
    "Try rephrasing, browse the policy library, or contact the policy owner."
)


@dataclass
class ApproachContext:
    corpus: Corpus
    retriever: Retriever
    llm: LLMProvider | None


class Approach:
    name: str = ""

    def __init__(self, ctx: ApproachContext, config: dict):
        self.ctx = ctx
        self.config = config
        self.version = config["version"]

    def run(self, question: str, role: str) -> ApproachResponse:
        raise NotImplementedError

    def retrieve(self, question: str, role: str) -> list[ScoredPassage]:
        r = self.config["retrieval"]
        return self.ctx.retriever.retrieve(question, role, k=r["top_k"], k1=r.get("k1", 1.5), b=r.get("b", 0.75))

    def base_response(self, hits: list[ScoredPassage], start: float) -> ApproachResponse:
        return ApproachResponse(
            approach=self.name,
            answer="",
            status="error",
            citations=[],
            retrieved_document_ids=_unique([h.passage.document_id for h in hits]),
            latency_ms=round((time.perf_counter() - start) * 1000, 1),
            input_tokens=None,
            output_tokens=None,
            estimated_cost_usd=None,
            approach_version=self.version,
            retrieved_passages=[
                {"passage_id": h.passage.passage_id, "document_id": h.passage.document_id, "score": h.score}
                for h in hits
            ],
        )


def format_passages(corpus: Corpus, hits: list[ScoredPassage]) -> str:
    if not hits:
        return "(no passages found)"
    blocks = []
    for h in hits:
        p = h.passage
        title = corpus.get(p.document_id).title
        blocks.append(f"[{p.passage_id}] {title} — {p.heading}\n{p.text}")
    return "\n\n".join(blocks)


def _unique(items):
    seen, out = set(), []
    for i in items:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def build_approaches(ctx: ApproachContext) -> dict[str, Approach]:
    from ..prompts import load_approach_config
    from .basic_rag import BasicRAG
    from .guarded_rag import GuardedRAG
    from .search import KeywordSearch

    return {
        "search": KeywordSearch(ctx, load_approach_config("search")),
        "basic_rag": BasicRAG(ctx, load_approach_config("basic_rag")),
        "guarded_rag": GuardedRAG(ctx, load_approach_config("guarded_rag")),
    }
