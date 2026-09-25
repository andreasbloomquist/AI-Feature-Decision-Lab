"""Apply the pre-registered launch criteria to a run's held-out metrics."""
from __future__ import annotations

import hashlib
import operator

import yaml

from .approaches.base import APPROACH_LABELS, APPROACH_NAMES
from .dataset import load_dataset
from .db import Database
from .evaluation import summarize_run
from .grading import final_label
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


def criteria_config() -> tuple[dict, str]:
    raw = (CONFIG_DIR / "launch_criteria.yaml").read_text()
    return yaml.safe_load(raw), hashlib.sha256(raw.encode()).hexdigest()[:12]


def _get(metrics: dict, dotted: str):
    cur = metrics
    for part in dotted.split("."):
        if cur is None:
            return None
        cur = cur.get(part)
    return cur


def _examples(criterion_id: str, rows: list[dict], threshold) -> list[str]:
    if criterion_id == "access_safety":
        return [r["case"]["case_id"] for r in rows if r["grade"]["disclosures"]]
    if criterion_id == "correctness":
        return [
            r["case"]["case_id"] for r in rows if r["case"]["answerability"] == "answerable"
            and final_label(r["grade"], r["judge"], r["review"])[0] != "correct"
        ]
    if criterion_id == "citation_validity":
        bad = []
        for r in rows:
            if r["response"]["status"] != "answered":
                continue
            cc = r["grade"]["citation_check"] or {}
            support = (r["judge"] or {}).get("citations_support")
            if support is None:
                support = cc.get("supports_deterministic")
            if not (cc.get("structurally_valid") and support):
                bad.append(r["case"]["case_id"])
        return bad
    if criterion_id == "abstention_quality":
        return [r["case"]["case_id"] for r in rows if r["case"]["answerability"] == "unanswerable" and not r["grade"]["abstained_correctly"]]
    if criterion_id == "latency_p95":
        slow = [r for r in rows if (r["response"].get("latency_ms") or 0) > threshold]
        return [r["case"]["case_id"] for r in sorted(slow, key=lambda r: -r["response"]["latency_ms"])]
    if criterion_id == "cost_per_question":
        priced = [r for r in rows if r["response"].get("estimated_cost_usd") is not None]
        return [r["case"]["case_id"] for r in sorted(priced, key=lambda r: -r["response"]["estimated_cost_usd"])[:5]]
    return []


def evaluate_criteria(metrics: dict, rows: list[dict], cfg: dict) -> list[dict]:
    min_n = cfg.get("min_sample_size", 5)
    out = []
    for c in cfg["criteria"]:
        cid, thr, comp = c["id"], c["threshold"], c["comparator"]
        value = _get(metrics, c["metric"])
        entry = {"id": cid, "label": c["label"], "comparator": comp, "threshold": thr, "unit": c["unit"],
                 "value": value, "n": None, "state": None, "reason": None, "confidence": None, "example_case_ids": []}
        if cid == "access_safety":
            entry["n"] = metrics["access_safety"]["n_cases"]
        elif cid in ("correctness", "citation_validity", "abstention_quality"):
            m = metrics[cid]
            entry.update(n=m["denominator"], numerator=m["numerator"], ci_low=m["ci_low"], ci_high=m["ci_high"])
        elif cid == "latency_p95":
            entry["n"] = metrics["latency"]["n"]
        elif cid == "cost_per_question":
            entry["n"] = metrics["cost"]["n_with_usage"]

        if cid == "latency_p95" and (metrics["latency"]["n_unmeasured"] or metrics.get("fixture_rows")):
            entry["state"] = "insufficient"
            entry["reason"] = (f"latency not measured for {metrics['latency']['n_unmeasured']} of {metrics['n_cases']} cases"
                               + (" (fixture responses)" if metrics.get("fixture_rows") else ""))
        elif cid == "cost_per_question" and not metrics["cost"]["available"]:
            entry["state"] = "insufficient"
            entry["reason"] = f"token usage unavailable for {metrics['cost']['n_missing']} of {metrics['n_cases']} cases"
        elif value is None or (entry["n"] is not None and entry["n"] < min_n):
            entry["state"] = "insufficient"
            entry["reason"] = f"only {entry['n'] or 0} evaluated cases (minimum {min_n})"
        else:
            entry["state"] = "pass" if OPS[comp](value, thr) else "fail"
            if "ci_low" in entry and entry["ci_low"] is not None:
                crosses = entry["ci_low"] < thr <= entry["ci_high"] if comp == ">=" else entry["ci_low"] <= thr < entry["ci_high"]
                entry["confidence"] = "low" if crosses else "ok"
        if entry["state"] == "fail":
            entry["example_case_ids"] = _examples(cid, rows, thr)[:8]
        out.append(entry)
    return out


def recommend(criteria: list[dict], is_fixture: bool) -> dict:
    fails = [c for c in criteria if c["state"] == "fail"]
    insufficient = [c for c in criteria if c["state"] == "insufficient"]
    if is_fixture:
        return {"verdict": "demonstration_only", "headline": "Demonstration only: fixture data is not evidence",
                "summary": "These results come from saved example responses written to exercise the interface. "
                           "They are not model measurements and cannot support a launch decision. Run a live evaluation."}
    if any(c["id"] == "access_safety" for c in fails):
        return {"verdict": "do_not_launch", "headline": "Do not launch: restricted content was disclosed",
                "summary": "Guarded RAG disclosed restricted content to an unauthorized role. This is a hard stop regardless of other results."}
    if fails:
        names = ", ".join(c["label"].lower() for c in fails)
        return {"verdict": "do_not_launch_yet", "headline": "Do not launch yet",
                "summary": f"Guarded RAG misses {len(fails)} of {len(criteria)} launch criteria ({names}). Fix these and re-test on a fresh held-out set."}
    if insufficient:
        names = ", ".join(c["label"].lower() for c in insufficient)
        return {"verdict": "insufficient_evidence", "headline": "Insufficient evidence",
                "summary": f"No criterion failed, but these could not be assessed: {names}."}
    low = [c for c in criteria if c.get("confidence") == "low"]
    summary = "Guarded RAG meets every pre-registered criterion on the held-out set. Proceed to a limited pilot, not a general launch."
    if low:
        summary += " Note: the confidence interval for " + ", ".join(c["label"].lower() for c in low) + " still crosses the threshold, so confirm it in the pilot."
    return {"verdict": "limited_pilot", "headline": "Proceed to a limited pilot", "summary": summary}


def build_decision(db: Database, run_id: str) -> dict:
    run = db.get_run(run_id)
    cfg, cfg_hash = criteria_config()
    split = cfg.get("evaluated_split", "held_out")
    dataset = load_dataset()
    summary = summarize_run(db, run_id)
    rows = db.responses_for_run(run_id)
    for r in rows:
        r["case"] = dataset["by_id"][r["case_id"]]
    split_rows = [r for r in rows if r["case"]["split"] == split]
    split_metrics = summary.get(split, {})
    is_fixture = run["mode"] == "fixture"

    per_approach = {}
    for a in APPROACH_NAMES:
        if a not in split_metrics:
            continue
        crit = evaluate_criteria(split_metrics[a], [r for r in split_rows if r["approach"] == a], cfg)
        per_approach[a] = {"label": APPROACH_LABELS[a], "criteria": crit,
                           "passes": sum(c["state"] == "pass" for c in crit), "total": len(crit)}

    target = cfg.get("target_approach", "guarded_rag")
    baseline = cfg.get("baseline_approach", "search")
    rec = recommend(per_approach[target]["criteria"], is_fixture) if target in per_approach else {
        "verdict": "insufficient_evidence", "headline": "Insufficient evidence",
        "summary": f"This run has no {split} results for {APPROACH_LABELS.get(target, target)}."}

    comparison = None
    if target in split_metrics and baseline in split_metrics:
        t, b = split_metrics[target], split_metrics[baseline]
        tc, bc = t["correctness"]["value"], b["correctness"]["value"]
        comparison = {
            "target": target, "baseline": baseline,
            "correctness_lift_pp": round((tc - bc) * 100, 1) if tc is not None and bc is not None else None,
            "target_correct": f"{t['correctness']['numerator']}/{t['correctness']['denominator']}",
            "baseline_correct": f"{b['correctness']['numerator']}/{b['correctness']['denominator']}",
            "target_p95_ms": t["latency"]["p95_ms"], "baseline_p95_ms": b["latency"]["p95_ms"],
            "target_cost_per_question": t["cost"]["per_question_usd"],
            "baseline_cost_per_question": b["cost"]["per_question_usd"],
        }

    failing = [c["id"] for c in per_approach.get(target, {}).get("criteria", []) if c["state"] in ("fail", "insufficient")]
    return {
        "run_id": run_id,
        "run_mode": run["mode"],
        "run_created_at": run["created_at"],
        "model_config": run["model_config"],
        "evaluated_split": split,
        "n_cases": len({r["case"]["case_id"] for r in split_rows}),
        "criteria_version": cfg["version"],
        "criteria_hash": cfg_hash,
        "criteria_registered_on": str(cfg.get("registered_on")),
        "target_approach": target,
        "recommendation": rec,
        "approaches": per_approach,
        "comparison": comparison,
        "next_experiments": [{"criterion": f, "text": NEXT_EXPERIMENTS[f]} for f in failing if f in NEXT_EXPERIMENTS and not is_fixture],
        "rollout_tests": ROLLOUT_TESTS,
        "limitations": LIMITATIONS,
    }


LIMITATIONS = [
    "60 synthetic questions (45 held out) on a 21-document synthetic corpus. Enough to demonstrate a decision process, not to establish production reliability.",
    "Small denominators: 6 unanswerable and about 35 answerable held-out cases, so one case moves a rate by 3 to 17 points. Confidence intervals are shown for that reason.",
    "Questions were written by the same author as the documents, so they are cleaner and closer to the document wording than real employee questions.",
    "Deterministic fact matching is strict about figures and lenient about wording; the model judge is itself a model and can be wrong. Human review is the tie-breaker.",
    "Latency was measured from one machine and region at low concurrency; production latency and cost at peak volume are untested.",
    "Roles are selected in the UI, not authenticated. Access control is tested at the retrieval layer only.",
]
