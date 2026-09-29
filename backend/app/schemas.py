"""The common response object returned by every approach."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

# "access_denied" is returned by the source preview when a role may not open a document. The
# approaches themselves report a restricted question as "abstained", so they never confirm that
# a restricted document exists.
Status = Literal["answered", "abstained", "access_denied", "error"]


@dataclass
class Citation:
    document_id: str
    passage_id: str | None
    title: str | None
    valid: bool
    reason: str | None = None  # why the citation is invalid, e.g. "not_in_context"


@dataclass
class ApproachResponse:
    approach: str
    answer: str
    status: Status
    citations: list[Citation]
    retrieved_document_ids: list[str]
    latency_ms: float | None
    input_tokens: int | None
    output_tokens: int | None
    estimated_cost_usd: float | None
    error: str | None = None
    # Extra fields for inspection. Not part of the common contract, but saved with every run.
    approach_version: str = ""
    prompt_version: str | None = None
    model: str | None = None
    retrieved_passages: list[dict] = field(default_factory=list)  # [{passage_id, document_id, score}]
    guard_reason: str | None = None  # why guarded RAG abstained or withheld an answer
    warnings: list[str] = field(default_factory=list)
    fixture: bool = False  # True when the model output came from saved example data
    raw_output: str | None = None  # model text before parsing, kept for reviewers

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def failed(cls, approach: str, error: str, *, approach_version: str = "") -> ApproachResponse:
        """A response for a case that could not be run at all (exception before any output)."""
        return cls(
            approach=approach,
            answer="",
            status="error",
            citations=[],
            retrieved_document_ids=[],
            latency_ms=None,
            input_tokens=None,
            output_tokens=None,
            estimated_cost_usd=None,
            error=error,
            approach_version=approach_version,
        )

    def public_dict(self) -> dict:
        """What an end user's browser receives.

        No raw model output, and a citation to a restricted document is indistinguishable from a
        citation to one that does not exist (same placeholder ID, same reason, same warning and
        error text), so users cannot probe for restricted IDs. Stored runs keep the distinction.
        """
        # Imported here because `citations` imports this module for the Citation class.
        from .citations import HIDDEN_REASONS, PUBLIC_HIDDEN_REASON, RESTRICTED, public_reason_text

        d = self.to_dict()
        d.pop("raw_output", None)
        for c in d["citations"]:
            if c["reason"] in HIDDEN_REASONS:
                c.update(document_id=RESTRICTED, passage_id=None, title=None, reason=PUBLIC_HIDDEN_REASON)
        d["warnings"] = [public_reason_text(w) for w in d["warnings"]]
        if d["error"]:
            d["error"] = public_reason_text(d["error"])
        return d
