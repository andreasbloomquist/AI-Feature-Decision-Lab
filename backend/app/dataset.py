"""Load the fixed evaluation dataset."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from functools import lru_cache

import yaml

from .access import ROLE_GROUPS
from .settings import DATA_DIR

EVAL_DIR = DATA_DIR / "eval"
SPLITS = ("development", "held_out")
REQUIRED_FIELDS = [
    "case_id",
    "question",
    "user_role",
    "category",
    "split",
    "answerability",
    "reference_answer",
    "required_facts",
    "acceptable_document_ids",
    "forbidden_document_ids",
    "notes",
]
ALLOWED_VALUES = {
    "user_role": set(ROLE_GROUPS),
    "split": set(SPLITS),
    "answerability": {"answerable", "unanswerable", "access_denied"},
    "category": {"single_document", "multi_document", "outdated_policy", "unanswerable", "role_access"},
}


def validate_cases(cases: list[dict]) -> None:
    """Fail loudly on a malformed dataset instead of producing a run with silently wrong grades."""
    seen: set[str] = set()
    for c in cases:
        missing = [f for f in REQUIRED_FIELDS if f not in c]
        if missing:
            raise ValueError(f"case {c.get('case_id')} missing {missing}")
        for field, allowed in ALLOWED_VALUES.items():
            if c[field] not in allowed:
                raise ValueError(f"case {c['case_id']}: {field}={c[field]!r} is not one of {sorted(allowed)}")
        if c["case_id"] in seen:
            raise ValueError(f"duplicate case_id {c['case_id']}")
        seen.add(c["case_id"])


@lru_cache(maxsize=1)
def load_dataset() -> dict:
    meta = yaml.safe_load((EVAL_DIR / "dataset.yaml").read_text())
    raw = (EVAL_DIR / meta["cases_file"]).read_text(encoding="utf-8")
    cases = [json.loads(line) for line in raw.splitlines() if line.strip()]
    validate_cases(cases)
    digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
    return {
        "meta": meta,
        "version": f"{meta['dataset_id']}@{meta['version']}+{digest}",
        "cases": cases,
        "by_id": {c["case_id"]: c for c in cases},
    }


@lru_cache(maxsize=1)
def load_restricted_markers() -> dict[str, list[str]]:
    return yaml.safe_load((EVAL_DIR / "restricted_markers.yaml").read_text())


def answerability_counts(split: str) -> Counter:
    """How many cases of each answerability label a split has, e.g. {"answerable": 35, ...}."""
    return Counter(c["answerability"] for c in load_dataset()["cases"] if c["split"] == split)
