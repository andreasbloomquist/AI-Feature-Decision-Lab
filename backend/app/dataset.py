"""Load the fixed evaluation dataset."""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache

import yaml

from .settings import DATA_DIR

EVAL_DIR = DATA_DIR / "eval"
REQUIRED_FIELDS = [
    "case_id", "question", "user_role", "category", "split", "answerability", "reference_answer",
    "required_facts", "acceptable_document_ids", "forbidden_document_ids", "notes",
]


@lru_cache(maxsize=1)
def load_dataset() -> dict:
    meta = yaml.safe_load((EVAL_DIR / "dataset.yaml").read_text())
    raw = (EVAL_DIR / meta["cases_file"]).read_text(encoding="utf-8")
    cases = [json.loads(line) for line in raw.splitlines() if line.strip()]
    for c in cases:
        missing = [f for f in REQUIRED_FIELDS if f not in c]
        if missing:
            raise ValueError(f"case {c.get('case_id')} missing {missing}")
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
