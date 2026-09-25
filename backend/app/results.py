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
    the judge), otherwise declined without disclosing anything."""
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


def latest_runs(db: Database, split: str = "held_out") -> tuple[dict | None, dict | None]:
    """(newest completed live run that covers `split`, newest fixture run); either may be None.

    A development-only live run (`make eval-dev`) is skipped, so tuning never hides the last full result.
    """
    runs = db.list_runs()
    live = next(
        (r for r in runs if r["mode"] == "live" and r["status"].startswith("completed") and split in r["splits"]),
        None,
    )
    fixture = next((r for r in runs if r["mode"] == "fixture"), None)
    return live, fixture
