"""Shared machinery for the three approaches: retrieval, the common response object and the model call.

Every approach gets the same role-filtered, active-only retrieval, so differences in results come
from how the answer is produced, not from what was retrieved.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from ..corpus import Corpus
from ..llm import LLMError, LLMProvider, LLMResult, fixture_key
from ..pricing import estimate_cost_usd
from ..prompts import PromptTemplate, load_prompt
from ..retrieval import DEFAULT_B, DEFAULT_K1, BM25Index, Retriever, ScoredPassage
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


def elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


def format_passages(corpus: Corpus, hits: list[ScoredPassage]) -> str:
    """Passages as the model sees them: `[ID] Title — Heading` followed by the text."""
    if not hits:
        return "(no passages found)"
    return "\n\n".join(
        f"[{h.passage.passage_id}] {corpus.get(h.passage.document_id).title} — {h.passage.heading}\n{h.passage.text}"
        for h in hits
    )


class Approach:
    name: str = ""

    def __init__(self, ctx: ApproachContext, config: dict):
        self.ctx = ctx
        self.config = config
        self.version: str = config["version"]
        retrieval = config["retrieval"]
        self.top_k: int = retrieval["top_k"]
        self.k1: float = retrieval.get("k1", DEFAULT_K1)
        self.b: float = retrieval.get("b", DEFAULT_B)

    def run(self, question: str, role: str) -> ApproachResponse:
        raise NotImplementedError

    # ---- retrieval --------------------------------------------------------------------
    def index(self, role: str) -> BM25Index:
        return self.ctx.retriever.index_for(role, self.k1, self.b)

    def retrieve(self, question: str, role: str) -> list[ScoredPassage]:
        return self.index(role).search(question, self.top_k)

    def new_response(self, hits: list[ScoredPassage]) -> ApproachResponse:
        return ApproachResponse(
            approach=self.name,
            answer="",
            status="error",
            citations=[],
            retrieved_document_ids=list(dict.fromkeys(h.passage.document_id for h in hits)),
            latency_ms=None,
            input_tokens=None,
            output_tokens=None,
            estimated_cost_usd=None,
            approach_version=self.version,
            retrieved_passages=[
                {"passage_id": h.passage.passage_id, "document_id": h.passage.document_id, "score": h.score}
                for h in hits
            ],
        )

    # ---- generation -------------------------------------------------------------------
    def prompt(self) -> PromptTemplate:
        return load_prompt(self.config["prompt_file"])

    def generate(
        self, resp: ApproachResponse, hits: list[ScoredPassage], question: str, role: str, start: float
    ) -> LLMResult | None:
        """Call the model once and record model, tokens, cost and latency on `resp`.

        Returns None after marking `resp` as an error if the call failed. There is never a retry
        beyond the SDK's transport-level retry, and never a second "repair" call.
        """
        llm = self.ctx.llm
        if llm is None:
            raise RuntimeError(f"{self.name} needs an LLM provider")
        prompt = self.prompt()
        resp.prompt_version = prompt.version
        resp.model = llm.model
        resp.fixture = llm.is_fixture
        system, user = prompt.render(passages=format_passages(self.ctx.corpus, hits), question=question, role=role)
        try:
            result = llm.generate(
                system,
                user,
                max_tokens=self.config["generation"]["max_tokens"],
                fixture_key=fixture_key(self.name, question, role),
            )
        except LLMError as e:
            resp.status = "error"
            resp.error = f"{e.kind}: {e.message}"
            resp.latency_ms = e.latency_ms
            return None
        resp.raw_output = result.text
        # Fixture replays carry no latency; everything else is wall-clock time for the whole approach.
        resp.latency_ms = None if llm.is_fixture else elapsed_ms(start)
        resp.input_tokens, resp.output_tokens = result.input_tokens, result.output_tokens
        resp.estimated_cost_usd = estimate_cost_usd(result.model, result.input_tokens, result.output_tokens)
        return result


def build_approaches(ctx: ApproachContext) -> dict[str, Approach]:
    # Imported here because each approach module imports this one for the Approach base class.
    from ..prompts import load_approach_config
    from .basic_rag import BasicRAG
    from .guarded_rag import GuardedRAG
    from .search import KeywordSearch

    return {
        "search": KeywordSearch(ctx, load_approach_config("search")),
        "basic_rag": BasicRAG(ctx, load_approach_config("basic_rag")),
        "guarded_rag": GuardedRAG(ctx, load_approach_config("guarded_rag")),
    }
