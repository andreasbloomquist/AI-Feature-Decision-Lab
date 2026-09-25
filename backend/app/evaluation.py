"""Evaluation runner. Every run is a new, immutable record with the versions and configuration it used."""
from __future__ import annotations

import argparse
import json
import secrets
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .approaches import APPROACH_NAMES, ApproachContext, build_approaches
from .corpus import get_corpus
from .dataset import load_dataset
from .db import Database, now_iso
from .grading import grade
from .judge import judge_response
from .llm import FixtureProvider, LLMProvider, make_provider
from .metrics import compute_metrics
from .prompts import load_approach_config, load_prompt
from .retrieval import Retriever
from .schemas import ApproachResponse
from .settings import CONFIG_DIR, RESULTS_DIR, Settings, load_settings, public_settings

SPLITS = ("development", "held_out")


def config_snapshot(settings: Settings) -> dict:
    approaches = {}
    for name in APPROACH_NAMES:
        cfg = load_approach_config(name)
        entry = {"config": cfg}
        if cfg.get("prompt_file"):
            p = load_prompt(cfg["prompt_file"])
            entry["prompt"] = {"version": p.version, "path": p.path, "system": p.system, "user": p.user}
        approaches[name] = entry
    judge = load_prompt("prompts/judge.v1.md")
    return {
        "approaches": approaches,
        "judge_prompt": {"version": judge.version, "system": judge.system, "user": judge.user},
        "pricing": yaml.safe_load((CONFIG_DIR / "pricing.yaml").read_text()),
        "launch_criteria": yaml.safe_load((CONFIG_DIR / "launch_criteria.yaml").read_text()),
        "settings": public_settings(settings),
    }


def prompt_versions() -> dict:
    out = {}
    for name in APPROACH_NAMES:
        cfg = load_approach_config(name)
        out[name] = {"approach_version": cfg["version"],
                     "prompt_version": load_prompt(cfg["prompt_file"]).version if cfg.get("prompt_file") else None}
    out["judge"] = {"prompt_version": load_prompt("prompts/judge.v1.md").version}
    return out


def _safe_run(approach, case: dict) -> ApproachResponse:
    """A failing case must never stop the run: any exception becomes a visible error response."""
    try:
        return approach.run(case["question"], case["user_role"])
    except Exception as e:  # noqa: BLE001 - deliberately broad, recorded below
        return ApproachResponse(
            approach=approach.name, answer="", status="error", citations=[], retrieved_document_ids=[],
            latency_ms=None, input_tokens=None, output_tokens=None, estimated_cost_usd=None,
            error=f"internal_error: {type(e).__name__}: {str(e)[:200]}", approach_version=approach.version,
            warnings=[traceback.format_exc(limit=2)[-500:]],
        )


def run_evaluation(
    db: Database,
    *,
    mode: str,
    splits: tuple[str, ...] = SPLITS,
    approaches: tuple[str, ...] = APPROACH_NAMES,
    llm: LLMProvider | None = None,
    judge_llm: LLMProvider | None = None,
    settings: Settings | None = None,
    concurrency: int = 4,
    label: str | None = None,
    case_ids: list[str] | None = None,
    export_dir: Path | None = RESULTS_DIR / "runs",
    progress: bool = False,
) -> str:
    settings = settings or load_settings()
    if mode not in ("live", "fixture"):
        raise ValueError("mode must be live or fixture")
    corpus = get_corpus()
    dataset = load_dataset()
    if llm is None:
        llm = FixtureProvider() if mode == "fixture" else make_provider(settings)
    if mode == "live" and llm.is_fixture:
        raise RuntimeError("live mode requested but no provider key is configured")

    cases = [c for c in dataset["cases"] if c["split"] in splits and (not case_ids or c["case_id"] in case_ids)]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{mode}-{stamp}-{secrets.token_hex(2)}"
    model_config = {
        "provider": "fixture" if mode == "fixture" else settings.provider,
        "model": llm.model,
        "effort": None if mode == "fixture" else settings.effort,
        "judge_model": judge_llm.model if judge_llm else None,
        "timeout_s": settings.timeout_s,
        "max_retries": settings.max_retries,
    }
    db.create_run({
        "run_id": run_id, "created_at": now_iso(), "mode": mode, "status": "running", "label": label,
        "splits": list(splits), "judge_mode": "model" if judge_llm else "none",
        "corpus_version": corpus.version, "dataset_version": dataset["version"],
        "prompt_versions": prompt_versions(), "model_config": model_config,
        "config_snapshot": config_snapshot(settings),
    })

    ctx = ApproachContext(corpus=corpus, retriever=Retriever(corpus), llm=llm)
    impls = build_approaches(ctx)
    tasks = [(c, impls[a]) for c in cases for a in approaches]
    failures = 0

    def work(task):
        case, approach = task
        resp = _safe_run(approach, case)
        g = grade(case, resp, corpus)
        j = None
        if judge_llm and case["answerability"] == "answerable" and resp.status == "answered":
            try:
                j = judge_response(judge_llm, case, resp, corpus)
            except Exception as e:  # noqa: BLE001
                j = {"verdict": None, "error": f"judge_internal_error: {e}"}
        db.add_response(run_id, case["case_id"], approach.name, resp.to_dict(), g, j)
        return resp.status

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        for i, status in enumerate(pool.map(work, tasks), 1):
            failures += status == "error"
            if progress and (i % 20 == 0 or i == len(tasks)):
                print(f"  {i}/{len(tasks)} responses ({failures} errors)", file=sys.stderr, flush=True)

    summary = summarize_run(db, run_id)
    db.finish_run(run_id, "completed_with_errors" if failures else "completed", summary)
    if export_dir:
        export_run(db, run_id, export_dir)
    return run_id


def summarize_run(db: Database, run_id: str) -> dict:
    dataset = load_dataset()
    rows = db.responses_for_run(run_id)
    out: dict = {}
    for r in rows:
        r["case"] = dataset["by_id"][r["case_id"]]
    for split in SPLITS + ("all",):
        split_rows = [r for r in rows if split == "all" or r["case"]["split"] == split]
        if not split_rows:
            continue
        out[split] = {}
        for approach in APPROACH_NAMES:
            ar = [r for r in split_rows if r["approach"] == approach]
            if ar:
                out[split][approach] = compute_metrics(ar)
    return out


def export_run(db: Database, run_id: str, export_dir: Path) -> Path:
    export_dir.mkdir(parents=True, exist_ok=True)
    run = db.get_run(run_id)
    rows = db.responses_for_run(run_id)
    path = export_dir / f"{run_id}.json"
    path.write_text(json.dumps({"run": run, "responses": rows}, indent=2, ensure_ascii=False))
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run an evaluation and save it as a new run.")
    parser.add_argument("--mode", choices=["live", "fixture"], default=None,
                        help="live needs a provider key; default is live when a key is set, otherwise fixture")
    parser.add_argument("--split", choices=["development", "held_out", "all"], default="all")
    parser.add_argument("--approach", action="append", choices=list(APPROACH_NAMES))
    parser.add_argument("--judge", choices=["model", "none"], default=None,
                        help="model judge for semantic correctness (default: model in live mode, none in fixture)")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--case", action="append", help="limit to specific case IDs (for debugging)")
    parser.add_argument("--label", default=None)
    args = parser.parse_args(argv)

    settings = load_settings()
    mode = args.mode or settings.mode
    if mode == "live" and not settings.live_available:
        print(f"No live evaluation possible: set {settings.api_key_env_var} (see .env.example).", file=sys.stderr)
        return 2
    splits = SPLITS if args.split == "all" else (args.split,)
    judge_mode = args.judge or ("model" if mode == "live" else "none")
    judge_llm = make_provider(settings, judge=True) if (judge_mode == "model" and mode == "live") else None
    db = Database(settings.db_path)
    print(f"Starting {mode} run on {', '.join(splits)} "
          f"(model={settings.model if mode == 'live' else 'fixture'}, judge={judge_llm.model if judge_llm else 'none'})",
          file=sys.stderr)
    run_id = run_evaluation(
        db, mode=mode, splits=splits, approaches=tuple(args.approach or APPROACH_NAMES), judge_llm=judge_llm,
        settings=settings, concurrency=args.concurrency, label=args.label, case_ids=args.case, progress=True,
    )
    print(run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
