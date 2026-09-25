"""The common response object returned by every approach."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

Status = Literal["answered", "abstained", "access_denied", "error"]
STATUSES = ("answered", "abstained", "access_denied", "error")


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
    def from_dict(cls, d: dict) -> "ApproachResponse":
        d = dict(d)
        d["citations"] = [Citation(**c) for c in d.get("citations", [])]
        return cls(**d)

    def public_dict(self) -> dict:
        """What an end user's browser receives: no raw model output."""
        d = self.to_dict()
        d.pop("raw_output", None)
        return d
