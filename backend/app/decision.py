"""Apply the launch criteria stored with a run to its held-out metrics and recommend an action."""

from __future__ import annotations

import hashlib
import operator
from collections import Counter

import yaml

from .approaches.base import APPROACH_LABELS, APPROACH_NAMES
from .corpus import get_corpus
from .db import Database
from .grading import citation_is_valid
from .results import load_rows, run_cases, run_validity, summarize_rows
from .settings import CONFIG_DIR

OPS = {"<=": operator.le, ">=": operator.ge}

ROLLOUT_TESTS = [
    "Shadow mode: run guarded RAG on real employee questions (with consent) for 2 weeks without showing answers, and label a random sample of 200.",
    "Red-team access control with HR and Finance: at least 50 adversarial prompts per restricted document, including prompt-injection text placed inside policy documents.",
    "Freshness: confirm the policy sync picks up a superseded document within one business day, and that stale answers disappear.",
    "Usability: 8 to 10 employee sessions to check whether people open citations and understand abstentions, and what they do next.",
    "Operations: define who owns wrong answers, the escalation path to policy owners, and a weekly review of abstained questions as a content-gap backlog.",
    "Load and cost: measure p95 latency and spend at expected peak volume, with a hard monthly budget alert.",
]

NEXT_EXPERIMENTS = {
    "access_safety": "Stop. Trace every disclosure to its path (retrieval, context, citation, preview), add a regression test for it, and re-run the full held-out set before anything else.",
    "correctness": "Inspect the incorrect answerable cases. If the right document was not retrieved, test hybrid retrieval (BM25 plus embeddings) and a larger top_k on the development split; if it was retrieved but misread, revise the prompt on the development split only. Then run once on a fresh held-out set, because this one has now been inspected.",
    "citation_validity": "Check whether invalid citations are malformed IDs, uncited answers or citations to passages outside the context. Test passage-ID-only citation formatting on the development split.",
    "abstention_quality": "Review the invented answers. Test a stricter retrieval floor and an explicit 'is this question covered?' check on the development split, and add more unanswerable near-miss questions to the next held-out set.",
    "latency_p95": "Profile model time against retrieval time. Test a smaller or faster model, lower effort, and fewer passages in context; show a streaming answer in the UI.",
    "cost_per_question": "Test a cheaper model tier, fewer passages in context, and prompt caching for the fixed system prompt, and re-measure correctness to check the quality trade.",
}


# How much evidence a criterion needs before it counts as met (`evidence` in launch_criteria.yaml):
# - "point": the observed value must meet the threshold (the default).
# - "interval": the whole 95% interval must meet it. A criterion whose interval straddles the threshold is
#   "insufficient evidence": more cases are needed before anyone can say which side it is on.
EVIDENCE_MODES = ("point", "interval")
# Criteria whose metric is a rate with a Wilson interval, so "interval" evidence can apply to them.
RATE_CRITERIA = ("correctness", "citation_validity", "abstention_quality")


def validate_criteria(cfg: dict) -> dict:
    """Reject criteria that would be applied in a way nobody intended. Returns `cfg` unchanged."""
    for c in cfg.get("criteria", []):
        evidence = c.get("evidence", "point")
        if evidence not in EVIDENCE_MODES:
            raise ValueError(f"criterion {c['id']}: evidence must be one of {EVIDENCE_MODES}, not {evidence!r}")
        if evidence == "interval" and c["id"] not in RATE_CRITERIA:
            raise ValueError(
                f"criterion {c['id']}: evidence 'interval' needs a rate criterion ({', '.join(RATE_CRITERIA)})"
            )
        min_n = c.get("min_n")
        if min_n is not None and (not isinstance(min_n, int) or isinstance(min_n, bool) or min_n < 1):
            raise ValueError(f"criterion {c['id']}: min_n must be a positive integer, not {min_n!r}")
    return cfg


def criteria_config() -> tuple[dict, str]:
    raw = (CONFIG_DIR / "launch_criteria.yaml").read_text()
    return validate_criteria(yaml.safe_load(raw)), hashlib.sha256(raw.encode()).hexdigest()[:12]


def _interval_state(comp: str, threshold: float, low: float, high: float) -> str:
    """Where a 95% interval sits relative to a threshold: wholly meeting it, wholly missing it, or straddling it."""
    if comp == ">=":
        return "pass" if low >= threshold else "fail" if high < threshold else "insufficient"
    return "pass" if high <= threshold else "fail" if low > threshold else "insufficient"


def _get(metrics: dict, dotted: str):
    cur = metrics
    for part in dotted.split("."):
        if cur is None:
            return None
        cur = cur.get(part)
    return cur


def _examples(criterion_id: str, rows: list[dict], threshold: float) -> list[str]:
    """Case IDs that illustrate why a criterion failed, most relevant first."""

    def ids(selected: list[dict]) -> list[str]:
        return [r["case_id"] for r in selected]

    if criterion_id == "access_safety":
        return ids([r for r in rows if r["grade"]["disclosures"]])
    if criterion_id == "correctness":
        return ids([r for r in rows if r["case"]["answerability"] == "answerable" and r["final_label"] != "correct"])
    if criterion_id == "citation_validity":
        return ids(
            [r for r in rows if r["response"]["status"] == "answered" and not citation_is_valid(r["grade"], r["judge"])]
        )
    if criterion_id == "abstention_quality":
        return ids(
            [r for r in rows if r["case"]["answerability"] == "unanswerable" and not r["grade"]["abstained_correctly"]]
        )
    if criterion_id == "latency_p95":
        slow = [r for r in rows if (r["response"].get("latency_ms") or 0) > threshold]
        return ids(sorted(slow, key=lambda r: -r["response"]["latency_ms"]))
    if criterion_id == "cost_per_question":
        priced = [r for r in rows if r["response"].get("estimated_cost_usd") is not None]
        return ids(sorted(priced, key=lambda r: -r["response"]["estimated_cost_usd"]))
    return []


def evaluate_criteria(metrics: dict, rows: list[dict], cfg: dict) -> list[dict]:
    default_min_n = cfg.get("min_sample_size", 5)
    min_coverage = cfg.get("min_measurement_coverage", 1.0)
    out = []
    for c in cfg["criteria"]:
        cid, thr, comp = c["id"], c["threshold"], c["comparator"]
        evidence = c.get("evidence", "point")
        min_n = c.get("min_n", default_min_n)
        value = _get(metrics, c["metric"])
        entry = {
            "id": cid,
            "label": c["label"],
            "comparator": comp,
            "threshold": thr,
            "unit": c["unit"],
            "value": value,
            "n": None,
            "state": None,
            "reason": None,
            "confidence": None,
            "evidence": evidence,
            "min_n": min_n,
            "example_case_ids": [],
        }
        if cid == "access_safety":
            entry["n"] = metrics["access_safety"]["n_cases"]
        elif cid in ("correctness", "citation_validity", "abstention_quality"):
            m = metrics[cid]
            entry.update(n=m["denominator"], numerator=m["numerator"], ci_low=m["ci_low"], ci_high=m["ci_high"])
        elif cid == "latency_p95":
            entry["n"] = metrics["latency"]["n"]
        elif cid == "cost_per_question":
            entry["n"] = metrics["cost"]["n_with_usage"]

        measurement = {"latency_p95": metrics.get("latency"), "cost_per_question": metrics.get("cost")}.get(cid)
        if cid == "access_safety" and value:
            # One disclosure is a hard stop at any sample size; there is nothing to be uncertain about.
            entry["state"] = "fail"
        elif measurement is not None and metrics.get("fixture_rows"):
            entry["state"] = "insufficient"
            entry["reason"] = "not measured: fixture responses have no latency or token usage"
        elif measurement is not None and measurement["coverage"] < min_coverage:
            entry["state"] = "insufficient"
            entry["reason"] = (
                f"measured for only {entry['n']} of {metrics['n_cases']} cases (minimum {min_coverage:.0%} coverage)"
            )
        elif value is None or (entry["n"] is not None and entry["n"] < min_n):
            entry["state"] = "insufficient"
            entry["reason"] = f"only {entry['n'] or 0} evaluated cases (minimum {min_n})"
        elif evidence == "interval":
            entry["state"] = _interval_state(comp, thr, entry["ci_low"], entry["ci_high"])
            if entry["state"] == "insufficient":
                entry["reason"] = (
                    f"95% interval {entry['ci_low']:.1%}–{entry['ci_high']:.1%} straddles the threshold; "
                    "this criterion requires the whole interval to clear it, so more cases are needed"
                )
        else:
            entry["state"] = "pass" if OPS[comp](value, thr) else "fail"
            if "ci_low" in entry and entry["ci_low"] is not None:
                crosses = (
                    entry["ci_low"] < thr <= entry["ci_high"]
                    if comp == ">="
                    else entry["ci_low"] <= thr < entry["ci_high"]
                )
                entry["confidence"] = "low" if crosses else "ok"
        if measurement is not None and entry["state"] in ("pass", "fail") and measurement["coverage"] < 1:
            entry["reason"] = f"based on the {entry['n']} of {metrics['n_cases']} cases that were measured"
        if entry["state"] == "fail":
            entry["example_case_ids"] = _examples(cid, rows, thr)[:8]
        out.append(entry)
    return out


def apply_validity_gate(criteria: list[dict], validity: dict, split: str) -> list[dict]:
    """In a run dominated by provider errors, no criterion is a quality verdict: each becomes
    "insufficient". A disclosure is the exception, because leaked content was really shown."""
    if validity["valid"]:
        return criteria
    reason = (
        f"not assessed: {validity['provider_errors']} of {validity['n_cases']} {split.replace('_', '-')} "
        f"cases failed with provider or runtime errors (limit {validity['max_error_rate']:.0%})"
    )
    out = []
    for c in criteria:
        if c["id"] == "access_safety" and c["state"] == "fail":
            out.append(c)
        else:
            out.append({**c, "state": "insufficient", "reason": reason, "confidence": None, "example_case_ids": []})
    return out


def recommend(
    criteria: list[dict], is_fixture: bool, validity: dict | None = None, target_label: str = "Guarded RAG"
) -> dict:
    fails = [c for c in criteria if c["state"] == "fail"]
    insufficient = [c for c in criteria if c["state"] == "insufficient"]
    if is_fixture:
        return {
            "verdict": "demonstration_only",
            "headline": "Demonstration only: fixture data is not evidence",
            "summary": "These results come from saved example responses written to exercise the interface. "
            "They are not model measurements and cannot support a launch decision. Run a live evaluation.",
        }
    if any(c["id"] == "access_safety" for c in fails):
        return {
            "verdict": "do_not_launch",
            "headline": "Do not launch: restricted content was disclosed",
            "summary": f"{target_label} disclosed restricted content to an unauthorized role. This is a hard stop regardless of other results.",
        }
    if validity is not None and not validity["valid"]:
        return {
            "verdict": "insufficient_evidence",
            "headline": "Insufficient evidence: run dominated by errors",
            "summary": f"Run dominated by errors: {validity['provider_errors']} of {validity['n_cases']} cases failed "
            f"for {target_label} ({validity['error_rate']:.0%}, above the {validity['max_error_rate']:.0%} limit) "
            "because of provider or runtime errors, such as a bad API key, an outage or rate limits. These results "
            "say nothing about answer quality. Fix the cause and re-run the evaluation.",
        }
    if fails:
        names = ", ".join(c["label"].lower() for c in fails)
        return {
            "verdict": "do_not_launch_yet",
            "headline": "Do not launch yet",
            "summary": f"{target_label} misses {len(fails)} of {len(criteria)} launch criteria ({names}). Fix these and re-test on a fresh held-out set.",
        }
    if insufficient:
        names = ", ".join(c["label"].lower() for c in insufficient)
        return {
            "verdict": "insufficient_evidence",
            "headline": "Insufficient evidence",
            "summary": f"No criterion failed, but these could not be assessed: {names}.",
        }
    low = [c for c in criteria if c.get("confidence") == "low"]
    summary = f"{target_label} meets every launch criterion on the held-out set. Proceed to a limited pilot, not a general launch."
    if low:
        summary += (
            " Note: the confidence interval for "
            + ", ".join(c["label"].lower() for c in low)
            + " still crosses the threshold, so confirm it in the pilot."
        )
    return {"verdict": "limited_pilot", "headline": "Proceed to a limited pilot", "summary": summary}


def run_criteria(run: dict) -> tuple[dict, str]:
    """The criteria stored with the run when it was created, so later edits cannot change its verdict."""
    snapshot = run.get("config_snapshot") or {}
    if snapshot.get("launch_criteria") and snapshot.get("launch_criteria_hash"):
        return snapshot["launch_criteria"], snapshot["launch_criteria_hash"]
    return criteria_config()


def build_decision(db: Database, run_id: str) -> dict:
    run = db.get_run(run_id)
    cfg, cfg_hash = run_criteria(run)
    split = cfg.get("evaluated_split", "held_out")
    split_rows = [r for r in load_rows(db, run_id) if r["case"]["split"] == split]
    split_metrics = summarize_rows(split_rows).get(split, {})
    is_fixture = run["mode"] == "fixture"

    per_approach = {}
    for a in APPROACH_NAMES:
        if a not in split_metrics:
            continue
        validity = run_validity(split_metrics[a], cfg)
        crit = evaluate_criteria(split_metrics[a], [r for r in split_rows if r["approach"] == a], cfg)
        crit = apply_validity_gate(crit, validity, split)
        per_approach[a] = {
            "label": APPROACH_LABELS[a],
            "criteria": crit,
            "passes": sum(c["state"] == "pass" for c in crit),
            "total": len(crit),
            "run_validity": validity,
            # Where the correctness labels came from, so a verdict that rests on human overrides says so.
            "label_sources": (split_metrics[a].get("correctness") or {}).get("label_sources"),
            "human_reviews": (split_metrics[a].get("correctness") or {}).get("human_reviews"),
        }

    target = cfg.get("target_approach", "guarded_rag")
    baseline = cfg.get("baseline_approach", "search")
    if target in per_approach:
        rec = recommend(
            per_approach[target]["criteria"], is_fixture, per_approach[target]["run_validity"], APPROACH_LABELS[target]
        )
    else:
        rec = {
            "verdict": "insufficient_evidence",
            "headline": "Insufficient evidence",
            "summary": f"This run has no {split} results for {APPROACH_LABELS.get(target, target)}.",
        }

    # Only a measured failure suggests an experiment; missing evidence is fixed by measuring, not tuning.
    failing = [c["id"] for c in per_approach.get(target, {}).get("criteria", []) if c["state"] == "fail"]
    return {
        "run_id": run_id,
        "run_mode": run["mode"],
        "run_created_at": run["created_at"],
        "model_config": run["model_config"],
        "evaluated_split": split,
        "n_cases": len({r["case_id"] for r in split_rows}),
        "criteria_version": cfg["version"],
        "criteria_hash": cfg_hash,
        "criteria_changed_since_run": cfg_hash != criteria_config()[1],
        "correctness_source": cfg.get("correctness_source"),
        "criteria_registered_on": str(cfg.get("registered_on")),
        "target_approach": target,
        "run_validity": per_approach[target]["run_validity"] if target in per_approach else None,
        "recommendation": rec,
        "approaches": per_approach,
        "comparison": _comparison(split_metrics, target, baseline),
        "next_experiments": []
        if is_fixture
        else [{"criterion": f, "text": NEXT_EXPERIMENTS[f]} for f in failing if f in NEXT_EXPERIMENTS],
        "rollout_tests": ROLLOUT_TESTS,
        "limitations": limitations(split, list(run_cases(run).values())),
    }


def human_override_note(decision: dict) -> str | None:
    """A sentence for the memo when human reviews changed correctness labels of the target or the baseline.

    Both matter: the verdict uses the target's labels and the lift over the baseline uses both. A review
    that agrees with the automated label is a confirmation, not an override, and is counted separately.
    """
    parts, confirmed = [], 0
    approaches = [decision["target_approach"]]
    if decision.get("comparison"):
        approaches.append(decision["comparison"]["baseline"])
    for a in dict.fromkeys(approaches):
        entry = decision["approaches"].get(a) or {}
        reviews = entry.get("human_reviews") or {}
        total = sum((entry.get("label_sources") or {}).values())
        confirmed += reviews.get("reviewed", 0) - reviews.get("changed", 0)
        if reviews.get("changed"):
            parts.append(f"{reviews['changed']} of {total} for {APPROACH_LABELS[a]}")
    if not parts:
        return None
    note = f"Human review changed correctness labels: {'; '.join(parts)}."
    if confirmed:
        note += f" {confirmed} more review(s) confirmed the automated label."
    return note + " Check those reviews in the Inspect view before relying on this verdict or the comparison."


def _comparison(split_metrics: dict, target: str, baseline: str) -> dict | None:
    """Target versus baseline on correctness, latency and cost: the product question in numbers."""
    if target not in split_metrics or baseline not in split_metrics:
        return None
    t, b = split_metrics[target], split_metrics[baseline]
    tc, bc = t["correctness"]["value"], b["correctness"]["value"]
    return {
        "target": target,
        "baseline": baseline,
        "correctness_lift_pp": round((tc - bc) * 100, 1) if tc is not None and bc is not None else None,
        "target_correct": f"{t['correctness']['numerator']}/{t['correctness']['denominator']}",
        "baseline_correct": f"{b['correctness']['numerator']}/{b['correctness']['denominator']}",
        "target_p95_ms": t["latency"]["p95_ms"],
        "baseline_p95_ms": b["latency"]["p95_ms"],
        "target_cost_per_question": t["cost"]["per_question_usd"],
        "baseline_cost_per_question": b["cost"]["per_question_usd"],
    }


def _denominator_note(counts: Counter) -> str:
    sizes = [n for n in counts.values() if n]
    if not sizes:
        return "No cases in this split, so no rate can be computed."
    return (
        f"Small denominators: {counts['answerable']} answerable, {counts['unanswerable']} unanswerable and "
        f"{counts['access_denied']} access-denied cases, so one case moves a rate by {100 / max(sizes):.0f} to "
        f"{100 / min(sizes):.0f} points. Confidence intervals are shown for that reason."
    )


def limitations(split: str, cases: list[dict]) -> list[str]:
    """Limits of the experiment, with sample sizes computed from the run's own dataset snapshot."""
    counts = Counter(c["answerability"] for c in cases if c["split"] == split)
    return [
        f"{len(cases)} synthetic questions ({sum(counts.values())} in the {split.replace('_', '-')} set) on a "
        f"{len(get_corpus().documents)}-document synthetic corpus. Enough to demonstrate a decision process, "
        "not to establish production reliability.",
        _denominator_note(counts),
        "Questions were written by the same author as the documents, so they are cleaner and closer to the "
        "document wording than real employee questions.",
        "Deterministic fact matching is strict about figures and lenient about wording; the model judge is itself "
        "a model and can be wrong. Human review is the tie-breaker.",
        "Latency was measured from one machine and region at low concurrency; production latency and cost at "
        "peak volume are untested.",
        "Roles are selected in the UI, not authenticated. Access control is enforced and tested in the backend "
        "(retrieval, model context, citations, previews), not against a real identity provider.",
    ]
