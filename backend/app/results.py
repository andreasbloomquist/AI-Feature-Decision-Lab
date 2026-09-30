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


# Usability of a completed run, by (database file, run id, split). Whether a run is usable depends only on
# its stored criteria and its provider errors, and neither changes after the run completes (human reviews
# change labels, never errors), so the answer is computed once instead of on every /api/runs request.
_USABLE_CACHE: dict[tuple[str, str, str], bool] = {}


def _is_usable_live_run(db: Database, run: dict, split: str) -> bool:
    """A full live run that covers `split`, includes the target approach and is not dominated by errors."""
    if run["mode"] != "live" or not run["status"].startswith("completed") or run.get("partial"):
        return False
    if split not in run["splits"]:
        return False
    key = (str(db.path), run["run_id"], split)
    if key not in _USABLE_CACHE:
        full = db.get_run(run["run_id"]) or {}
        cfg = (full.get("config_snapshot") or {}).get("launch_criteria") or {}
        target = cfg.get("target_approach", "guarded_rag")
        cases = run_cases(full)
        rows = [r for r in db.responses_for_run(run["run_id"]) if r["approach"] == target]
        rows = [{**r, "case": cases[r["case_id"]]} for r in rows if cases[r["case_id"]]["split"] == split]
        _USABLE_CACHE[key] = bool(rows) and run_validity(compute_metrics(rows), cfg)["valid"]
    return _USABLE_CACHE[key]


# The one split a decision run of record is designated for, locked on and counted on. Launch criteria
# name the split they evaluate (`evaluated_split`); a run whose stored criteria evaluate a different split
# cannot be designated, so the designation, the review lock and the decision always agree on the split.
DECISION_SPLIT = "held_out"


def designation_blocker(db: Database, run: dict, split: str = DECISION_SPLIT) -> str | None:
    """Why `run` cannot be the decision run of record for `split`, or None when it can.

    The rule is the same as for the default decision run (`_is_usable_live_run`); the reasons only make
    the refusal readable.
    """
    if run["mode"] != "live":
        return "Fixture runs are demonstration data and can never be the decision run of record."
    if not run["status"].startswith("completed"):
        return f"Only a completed run can be the decision run of record (this run is {run['status']})."
    if run.get("partial"):
        return "A partial run (limited to some cases or approaches) can never be the decision run of record."
    if split not in run["splits"]:
        return (
            f"This run does not cover the {split.replace('_', '-')} split, so it cannot be the decision run of record."
        )
    full = db.get_run(run["run_id"]) or {}
    evaluated = ((full.get("config_snapshot") or {}).get("launch_criteria") or {}).get("evaluated_split", split)
    if evaluated != split:
        return (
            f"This run's launch criteria evaluate the {evaluated.replace('_', '-')} split, so it cannot be the "
            f"decision run of record for the {split.replace('_', '-')} split."
        )
    if not _is_usable_live_run(db, run, split):
        return (
            "This run has no usable results for the target approach: it is missing or dominated by provider "
            "errors, so it cannot be the decision run of record."
        )
    return None


def run_of_record(db: Database, split: str = DECISION_SPLIT) -> tuple[dict | None, dict | None, str | None]:
    """(run, designation, problem) for the current decision run of record for `split`.

    All three are None when nothing is designated. A designation is only accepted for a usable run, and
    usability does not change after a run completes, so `problem` should never be set; if it is, the run is
    None (the caller falls back to the newest usable run) and `problem` says why, so the fallback is shown
    rather than silent.
    """
    designation = db.current_designation(split)
    if designation is None:
        return None, None, None
    run = next((r for r in db.list_runs() if r["run_id"] == designation["run_id"]), None)
    problem = "the run no longer exists." if run is None else designation_blocker(db, run, split)
    if problem:
        return None, designation, problem
    return run, designation, None


def latest_runs(db: Database, split: str = DECISION_SPLIT) -> tuple[dict | None, dict | None]:
    """(the live decision run for `split`, newest fixture run); either may be None.

    The decision run is the designated decision run of record when there is one. Otherwise it is the newest
    usable live run: a development-only live run (`make eval-dev`), a partial debug run (`--case`,
    `--approach`) and a run dominated by provider errors are all skipped, so none of them hides the last
    good full result.
    """
    runs = db.list_runs()
    record, _, _ = run_of_record(db, split)
    live = record or next((r for r in runs if _is_usable_live_run(db, r, split)), None)
    fixture = next((r for r in runs if r["mode"] == "fixture"), None)
    return live, fixture


def split_response_ids(db: Database, run_id: str, split: str = DECISION_SPLIT) -> list[str]:
    """The IDs of a run's responses whose case is in `split`, using the cases stored with the run."""
    run = db.get_run(run_id)
    cases = run_cases(run) if run else {}
    return [
        r["response_id"] for r in db.responses_for_run(run_id) if (cases.get(r["case_id"]) or {}).get("split") == split
    ]


def held_out_usage(db: Database, dataset_version: str, split: str = DECISION_SPLIT) -> dict:
    """How many live runs have evaluated `split` of this dataset version.

    Every live run that exposed answers on the split counts, whatever its outcome: partial, failed and
    error-dominated runs included, because each one let someone look at held-out results. A run still marked
    `running` counts as soon as it has stored a response on the split: a process killed mid-run leaves that
    status forever, while its answers stay visible. Those are listed in `in_progress_run_ids` too. Fixture
    runs never count: they are not model evaluations.
    """
    runs, in_progress = [], []
    for r in db.list_runs():
        if r["mode"] != "live" or r["dataset_version"] != dataset_version or split not in r["splits"]:
            continue
        if r["status"] == "running":
            if not split_response_ids(db, r["run_id"], split):
                continue
            in_progress.append(r["run_id"])
        runs.append(r)
    runs.sort(key=lambda r: (r["created_at"], r["run_id"]))
    return {
        "dataset_version": dataset_version,
        "split": split,
        "evaluations": len(runs),
        "run_ids": [r["run_id"] for r in runs],
        "in_progress_run_ids": [r["run_id"] for r in runs if r["run_id"] in in_progress],
    }
