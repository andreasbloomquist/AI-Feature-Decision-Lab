"""Acceptance 5 and 8: one timeout does not stop a run; saved runs reopen with configuration intact."""
from app.db import Database
from app.evaluation import run_evaluation, summarize_run
from app.llm import LLMError, ScriptedProvider

TIMEOUT_QUESTION = "Who approves travel over $2,000?"


def flaky_model(system, user):
    if TIMEOUT_QUESTION in user:
        raise LLMError("timeout", "model request timed out", latency_ms=20000.0)
    if "STATUS:" in system:
        return "STATUS: ABSTAINED\nANSWER: Not covered."
    return "The passages don't contain that."


def test_timeout_does_not_stop_remaining_cases(db):
    run_id = run_evaluation(
        db, mode="live", splits=("development",), llm=ScriptedProvider(flaky_model), concurrency=2, export_dir=None,
    )
    run = db.get_run(run_id)
    rows = db.responses_for_run(run_id)
    assert len(rows) == 15 * 3  # every case, every approach
    errors = [r for r in rows if r["response"]["status"] == "error"]
    assert {(r["case_id"], r["approach"]) for r in errors} == {("S02", "basic_rag"), ("S02", "guarded_rag")}
    assert all(r["grade"]["error_type"] == "timeout" for r in errors)
    assert run["status"] == "completed_with_errors"
    # Errors stay in the denominators and are counted visibly.
    m = summarize_run(db, run_id)["development"]["guarded_rag"]
    assert m["errors"]["count"] == 1 and m["errors"]["case_ids"] == ["S02"]
    assert m["correctness"]["denominator"] == 12


def test_unexpected_exception_is_recorded_not_raised(db):
    def boom(system, user):
        raise RuntimeError("provider SDK blew up")

    run_id = run_evaluation(db, mode="live", splits=("development",), approaches=("basic_rag",),
                            llm=ScriptedProvider(boom), export_dir=None)
    rows = db.responses_for_run(run_id)
    assert len(rows) == 15
    assert all(r["response"]["error"].startswith("internal_error") for r in rows)


def test_saved_run_reopens_with_configuration(tmp_path):
    path = tmp_path / "runs.sqlite3"
    db = Database(path)
    llm = ScriptedProvider(lambda s, u: "STATUS: ABSTAINED\nANSWER: no", model="claude-opus-5")
    run_id = run_evaluation(db, mode="live", splits=("development",), llm=llm, export_dir=tmp_path / "export")
    original = db.get_run(run_id)

    reopened = Database(path).get_run(run_id)  # a fresh connection, as after a restart
    assert reopened == original
    assert reopened["mode"] == "live"
    assert reopened["model_config"]["model"] == "claude-opus-5"
    assert reopened["prompt_versions"]["guarded_rag"]["prompt_version"] == "guarded-rag-v1"
    assert reopened["prompt_versions"]["basic_rag"]["prompt_version"] == "basic-rag-v1"
    assert reopened["corpus_version"].startswith("corpus-")
    assert reopened["dataset_version"].startswith("northstar-policy-qa@1.0.0")
    assert reopened["created_at"].endswith("Z")
    snap = reopened["config_snapshot"]
    assert snap["approaches"]["search"]["config"]["min_score"] == 5.0
    assert "Answer only from the policy passages" in snap["approaches"]["guarded_rag"]["prompt"]["system"]
    assert snap["launch_criteria"]["criteria"][1]["threshold"] == 0.80
    assert (tmp_path / "export" / f"{run_id}.json").exists()


def test_rerun_creates_new_run(db):
    llm = ScriptedProvider(lambda s, u: "STATUS: ABSTAINED\nANSWER: no")
    a = run_evaluation(db, mode="live", splits=("development",), approaches=("search",), llm=llm, export_dir=None)
    b = run_evaluation(db, mode="live", splits=("development",), approaches=("search",), llm=llm, export_dir=None)
    assert a != b
    assert len(db.list_runs()) == 2
    assert len(db.responses_for_run(a)) == len(db.responses_for_run(b)) == 15


def test_saved_run_reopens_through_api(client):
    runs = client.get("/api/runs").json()
    assert runs and runs[0]["mode"] == "fixture"
    run = client.get(f"/api/runs/{runs[0]['run_id']}").json()
    assert run["config_snapshot"]["approaches"]["guarded_rag"]["prompt"]["version"] == "guarded-rag-v1"
    assert run["metrics"]["held_out"]["guarded_rag"]["n_cases"] == 45
