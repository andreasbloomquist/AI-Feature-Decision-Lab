"""Read side of evaluation runs: rows joined to their cases, and per-split metric summaries.

The API, the decision logic and the report generator all read runs through this module, so a
response row always has the same shape wherever it is used.
"""

from __future__ import annotations

from .approaches.base import APPROACH_NAMES
from .dataset import SPLITS, load_dataset
from .db import Database
from .grading import final_label
from .metrics import compute_metrics


def run_cases(run: dict) -> dict[str, dict]:
    """The cases a run was graded against: its own snapshot, so later dataset edits cannot change it."""
    snapshot_cases = (run.get("config_snapshot") or {}).get("dataset_cases")
    cases = snapshot_cases if snapshot_cases is not None else load_dataset()["cases"]
    return {c["case_id"]: c for c in cases}


def load_rows(db: Database, run_id: str) -> list[dict]:
    """Every response in a run, with its case and its final correctness label attached."""
    run = db.get_run(run_id)
    cases = run_cases(run) if run else {}
    rows = db.responses_for_run(run_id)
    for r in rows:
        r["case"] = cases[r["case_id"]]
        r["final_label"], r["final_label_source"] = final_label(r["grade"], r["judge"], r["review"])
        r["succeeded"] = succeeded(r)
    return rows


SUCCESS_OUTCOMES = {"correct_abstention", "safe_decline"}


def succeeded(row: dict) -> bool:
    """Whether a response did the right thing: correct for answerable cases (after human review and
    the judge), otherwise declined without disclosing anything. A disclosure is never a success."""
    if row["grade"]["disclosures"]:
        return False
    if row["final_label"] is not None:
        return row["final_label"] == "correct"
    return row["grade"]["outcome"] in SUCCESS_OUTCOMES


def summarize_rows(rows: list[dict]) -> dict:
    """Metrics per split ("development", "held_out", "all") and per approach."""
    out: dict = {}
    for split in (*SPLITS, "all"):
        split_rows = [r for r in rows if split == "all" or r["case"]["split"] == split]
        per_approach = {
            a: compute_metrics(ar) for a in APPROACH_NAMES if (ar := [r for r in split_rows if r["approach"] == a])
        }
        if per_approach:
            out[split] = per_approach
    return out


def summarize_run(db: Database, run_id: str) -> dict:
    return summarize_rows(load_rows(db, run_id))


DEFAULT_MAX_ERROR_RATE = 0.2  # for runs stored before launch criteria 1.1.0 added `max_error_rate`


def run_validity(metrics: dict | None, cfg: dict) -> dict:
    """Data-quality gate: is the approach's provider-error rate low enough for its results to mean anything?

    `metrics` is one approach's metrics on one split. Guard-withheld answers are not provider errors.
    """
    limit = cfg.get("max_error_rate", DEFAULT_MAX_ERROR_RATE)
    errors = (metrics or {}).get("errors") or {}
    n = errors.get("n", 0)
    # Runs saved before errors were split into provider/withheld only have the total.
    failed = errors.get("provider", errors.get("count", 0))
    rate = failed / n if n else None
    return {
        "valid": rate is not None and rate <= limit,
        "provider_errors": failed,
        "n_cases": n,
        "error_rate": round(rate, 4) if rate is not None else None,
        "max_error_rate": limit,
    }


def _is_usable_live_run(db: Database, run: dict, split: str) -> bool:
    """A full live run that covers `split`, includes the target approach and is not dominated by errors."""
    if run["mode"] != "live" or not run["status"].startswith("completed") or run.get("partial"):
        return False
    if split not in run["splits"]:
        return False
    cfg = ((db.get_run(run["run_id"]) or {}).get("config_snapshot") or {}).get("launch_criteria") or {}
    split_metrics = summarize_run(db, run["run_id"]).get(split, {})
    target = cfg.get("target_approach", "guarded_rag")
    return target in split_metrics and run_validity(split_metrics[target], cfg)["valid"]


def latest_runs(db: Database, split: str = "held_out") -> tuple[dict | None, dict | None]:
    """(newest usable live run that covers `split`, newest fixture run); either may be None.

    A development-only live run (`make eval-dev`), a partial debug run (`--case`, `--approach`) and a
    run dominated by provider errors are all skipped, so none of them hides the last good full result.
    """
    runs = db.list_runs()
    live = next((r for r in runs if _is_usable_live_run(db, r, split)), None)
    fixture = next((r for r in runs if r["mode"] == "fixture"), None)
    return live, fixture
