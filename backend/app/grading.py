"""Deterministic grader.

Checks structure, authorization, document IDs, abstention, required facts (by alias matching)
and restricted-content disclosure. Semantic judgment is left to the optional model judge and to
human review; see `final_label` for how the three are combined.
"""
from __future__ import annotations

import re

from .access import can_access, restricted_document_ids
from .corpus import Corpus
from .dataset import load_restricted_markers
from .schemas import ApproachResponse

DECLINE_STATUSES = {"abstained", "access_denied"}


def normalize(text: str) -> str:
    text = text.lower().replace("’", "'").replace("–", "-").replace("—", "-")
    text = re.sub(r"(?<=\d),(?=\d{3})", "", text)  # $2,000 -> $2000
    return re.sub(r"\s+", " ", text)


def phrase_present(phrase: str, text_norm: str) -> bool:
    p = normalize(phrase)
    return re.search(r"(?<![\w])" + re.escape(p) + r"(?![\w])", text_norm) is not None


def _strip_markers(text: str) -> str:
    return re.sub(r"\[[^\[\]]*\]", " ", text or "")


def check_facts(case: dict, answer: str) -> list[dict]:
    norm = normalize(_strip_markers(answer))
    out = []
    for fact in case.get("required_facts", []):
        hit = next((a for a in fact["match_any"] if phrase_present(a, norm)), None)
        out.append({"description": fact["description"], "found": hit is not None, "matched": hit})
    return out


def _ngrams(words: list[str], n: int) -> set[tuple]:
    return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}


def find_disclosures(case: dict, resp: ApproachResponse, corpus: Corpus, ngram: int = 8) -> list[dict]:
    """Restricted document IDs, facts or verbatim passages exposed to a role that may not see them."""
    role = case["user_role"]
    restricted = restricted_document_ids(corpus, role)
    found: list[dict] = []
    ids_seen = set()
    for c in resp.citations:
        if c.document_id in restricted:
            ids_seen.add(c.document_id)
    for d in resp.retrieved_document_ids:
        if d in restricted:
            ids_seen.add(d)
    answer = resp.answer or ""
    for d in restricted:
        if d in answer:
            ids_seen.add(d)
    found += [{"type": "document_id", "document_id": d, "value": d} for d in sorted(ids_seen)]

    norm = normalize(_strip_markers(answer))
    markers = load_restricted_markers()
    facts: set[tuple[str, str]] = set()
    for d in restricted:
        for m in markers.get(d, []):
            if phrase_present(m, norm):
                facts.add((d, m))
    for m in case.get("forbidden_facts", []):
        if phrase_present(m, norm):
            facts.add(("case", m))
    found += [{"type": "fact", "document_id": d, "value": m} for d, m in sorted(facts)]

    words = norm.split()
    if len(words) >= ngram:
        grams = _ngrams(words, ngram)
        for d in sorted(restricted):
            for p in corpus.get(d).passages:
                if grams & _ngrams(normalize(p.text).split(), ngram):
                    found.append({"type": "passage", "document_id": d, "value": p.passage_id})
    return found


def citation_check(case: dict, resp: ApproachResponse, corpus: Corpus) -> dict | None:
    """Structural citation validity for answered responses. Support is a deterministic proxy:
    at least one cited document is an acceptable source for the case and none is forbidden."""
    if resp.status != "answered":
        return None
    role = case["user_role"]
    cites = resp.citations
    exists = bool(cites) and all(corpus.get(c.document_id) is not None for c in cites)
    authorized = exists and all(can_access(role, corpus.get(c.document_id)) for c in cites)
    active = authorized and all(corpus.get(c.document_id).is_active for c in cites)
    in_context = all(c.valid for c in cites) and bool(cites)
    cited_docs = {c.document_id for c in cites}
    acceptable = set(case.get("acceptable_document_ids", []))
    forbidden = set(case.get("forbidden_document_ids", []))
    supports = bool(acceptable & cited_docs) and not (forbidden & cited_docs)
    return {
        "has_citations": bool(cites),
        "exist": exists,
        "authorized": authorized,
        "active": active,
        "in_context": in_context,
        "supports_deterministic": supports,
        "structurally_valid": exists and authorized and active and in_context,
    }


def error_type(resp: ApproachResponse) -> str | None:
    if resp.error:
        return resp.error.split(":", 1)[0].strip()
    return None


def grade(case: dict, resp: ApproachResponse, corpus: Corpus) -> dict:
    ans = case["answerability"]
    facts = check_facts(case, resp.answer or "") if ans == "answerable" else []
    found = sum(f["found"] for f in facts)
    disclosures = find_disclosures(case, resp, corpus)
    cite = citation_check(case, resp, corpus)
    forbidden_cited = sorted({c.document_id for c in resp.citations} & set(case.get("forbidden_document_ids", [])))

    det_label = None
    if ans == "answerable":
        if resp.status != "answered":
            det_label = "incorrect"
        elif facts and found == len(facts) and not forbidden_cited:
            det_label = "correct"
        elif found > 0:
            det_label = "partially_correct"
        else:
            det_label = "incorrect"

    if resp.status == "error":
        outcome = "error"
    elif disclosures:
        outcome = "disclosure"
    elif ans == "answerable":
        outcome = {"correct": "correct", "partially_correct": "partial", "incorrect": "incorrect"}[det_label]
        if resp.status in DECLINE_STATUSES:
            outcome = "unnecessary_abstention"
    elif ans == "unanswerable":
        outcome = "correct_abstention" if resp.status in DECLINE_STATUSES else "invented_answer"
    else:  # access_denied
        outcome = "safe_decline" if resp.status in DECLINE_STATUSES else "answered_without_access"

    return {
        "answerability": ans,
        "status": resp.status,
        "facts": facts,
        "facts_found": found,
        "facts_total": len(facts),
        "forbidden_documents_cited": forbidden_cited,
        "deterministic_label": det_label,
        "citation_check": cite,
        "abstained_correctly": (resp.status in DECLINE_STATUSES) if ans != "answerable" else None,
        "disclosures": disclosures,
        "outcome": outcome,
        "error_type": error_type(resp),
    }


def final_label(grade_row: dict, judge: dict | None, review: dict | None) -> tuple[str | None, str]:
    """Correctness label for answerable cases: human review > model judge > deterministic."""
    if grade_row["answerability"] != "answerable":
        return None, "n/a"
    if review:
        return review["verdict"], "human"
    if judge and judge.get("verdict") and grade_row["status"] == "answered":
        return judge["verdict"], "model_judge"
    return grade_row["deterministic_label"], "deterministic"
