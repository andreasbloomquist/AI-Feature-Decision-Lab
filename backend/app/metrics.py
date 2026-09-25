"""Aggregate metrics. Every rate carries its numerator, denominator and a Wilson 95% interval."""
from __future__ import annotations

import math
import statistics

from .grading import final_label


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float | None, float | None]:
    if n == 0:
        return None, None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)


def rate(k: int, n: int, **extra) -> dict:
    lo, hi = wilson(k, n)
    return {"value": round(k / n, 4) if n else None, "numerator": k, "denominator": n, "ci_low": lo, "ci_high": hi, **extra}


def percentile(values: list[float], pct: float) -> float | None:
    """Nearest-rank percentile (no interpolation), so p95 is always an observed latency."""
    if not values:
        return None
    ordered = sorted(values)
    k = max(1, math.ceil(pct / 100 * len(ordered)))
    return ordered[k - 1]


def compute_metrics(rows: list[dict]) -> dict:
    """rows: [{case, response, grade, judge, review}] for ONE approach and ONE split."""
    answerable = [r for r in rows if r["case"]["answerability"] == "answerable"]
    labels = [final_label(r["grade"], r.get("judge"), r.get("review")) for r in answerable]
    correct = sum(1 for lab, _ in labels if lab == "correct")
    partial = sum(1 for lab, _ in labels if lab == "partially_correct")
    sources = {src: sum(1 for _, s in labels if s == src) for src in ("human", "model_judge", "deterministic")}
    det_correct = sum(1 for r in answerable if r["grade"]["deterministic_label"] == "correct")

    answered = [r for r in rows if r["response"]["status"] == "answered"]
    valid_cites = 0
    judge_support_used = 0
    for r in answered:
        cc = r["grade"]["citation_check"] or {}
        support = cc.get("supports_deterministic", False)
        j = r.get("judge") or {}
        if j.get("citations_support") is not None:
            support = j["citations_support"]
            judge_support_used += 1
        if cc.get("structurally_valid") and support:
            valid_cites += 1

    unanswerable = [r for r in rows if r["case"]["answerability"] == "unanswerable"]
    abst_ok = sum(1 for r in unanswerable if r["grade"]["abstained_correctly"])

    denied = [r for r in rows if r["case"]["answerability"] == "access_denied"]
    denied_ok = sum(1 for r in denied if r["grade"]["outcome"] == "safe_decline")
    disclosures = sum(len(r["grade"]["disclosures"]) for r in rows)
    disclosure_cases = [r["case"]["case_id"] for r in rows if r["grade"]["disclosures"]]

    fixture_rows = sum(1 for r in rows if r["response"].get("fixture"))
    measured = [r["response"]["latency_ms"] for r in rows if r["response"].get("latency_ms") is not None]
    if fixture_rows:
        # Mixing fixture replays (no latency) with a few locally measured rows would give a
        # misleading percentile, so latency is reported as not measured.
        measured = []

    costs = [r["response"]["estimated_cost_usd"] for r in rows]
    known = [c for c in costs if c is not None]
    missing = len(costs) - len(known)
    cost = {
        "available": bool(rows) and missing == 0,
        "n_with_usage": len(known),
        "n_missing": missing,
        "total_usd": round(sum(known), 6) if known else None,
        "per_question_usd": round(sum(known) / len(known), 6) if known and missing == 0 else None,
        "per_question_known_usd": round(sum(known) / len(known), 6) if known else None,
    }
    tokens_in = [r["response"]["input_tokens"] for r in rows if r["response"].get("input_tokens") is not None]
    tokens_out = [r["response"]["output_tokens"] for r in rows if r["response"].get("output_tokens") is not None]

    errors = [r for r in rows if r["response"]["status"] == "error"]
    status_counts: dict[str, int] = {}
    for r in rows:
        status_counts[r["response"]["status"]] = status_counts.get(r["response"]["status"], 0) + 1

    return {
        "n_cases": len(rows),
        "correctness": rate(correct, len(answerable), partial=partial, label_sources=sources),
        "correctness_deterministic": rate(det_correct, len(answerable)),
        "citation_validity": rate(valid_cites, len(answered), judge_support_used=judge_support_used),
        "abstention_quality": rate(abst_ok, len(unanswerable)),
        "access_denied_handling": rate(denied_ok, len(denied)),
        "access_safety": {"disclosures": disclosures, "cases_with_disclosure": disclosure_cases, "n_cases": len(rows)},
        "latency": {
            "n": len(measured),
            "n_unmeasured": len(rows) - len(measured),
            "p50_ms": round(statistics.median(measured), 1) if measured else None,
            "p95_ms": percentile(measured, 95),
        },
        "cost": cost,
        "tokens": {
            "input_total": sum(tokens_in) if tokens_in else None,
            "output_total": sum(tokens_out) if tokens_out else None,
            "n_with_usage": min(len(tokens_in), len(tokens_out)),
        },
        "errors": {"count": len(errors), "n": len(rows), "case_ids": [r["case"]["case_id"] for r in errors]},
        "status_counts": status_counts,
        "fixture_rows": fixture_rows,
    }
