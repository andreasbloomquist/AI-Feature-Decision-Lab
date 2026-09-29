"""Which runs count: error-dominated, partial and target-less runs never become the "latest" verdict,
and answers withheld by the guard are declines, not provider errors."""

from app.dataset import load_dataset
from app.decision import build_decision
from app.evaluation import run_evaluation
from app.grading import grade
from app.llm import LLMError, ScriptedProvider
from app.metrics import compute_metrics
from app.results import latest_runs, load_rows, run_validity
from app.schemas import ApproachResponse

ABSTAIN = ScriptedProvider(lambda s, u: "STATUS: ABSTAINED\nANSWER: Not covered.")


def bad_key(system, user):
    raise LLMError("auth", "provider rejected the API key", latency_ms=5.0)


def live_run(db, llm=ABSTAIN, **kwargs):
    kwargs.setdefault("splits", ("held_out",))
    return run_evaluation(db, mode="live", llm=llm, export_dir=None, **kwargs)


def withheld_response(approach="guarded_rag"):
    return ApproachResponse(
        approach,
        "This answer was withheld because it cited a source that failed validation.",
        "error",
        [],
        [],
        10.0,
        1000,
        100,
        0.01,
        error="citation_validation_failed: NS-ZZ-999 (unknown_document)",
        guard_reason="citation_validation_failed",
    )


# ---- run-validity gate (errors) ---------------------------------------------------------
def test_error_dominated_run_is_insufficient_evidence_not_a_quality_verdict(db):
    run_id = live_run(db, llm=ScriptedProvider(bad_key))
    d = build_decision(db, run_id)
    rec = d["recommendation"]
    assert rec["verdict"] == "insufficient_evidence"
    assert "dominated by errors" in rec["headline"]
    n = d["n_cases"]
    assert f"Run dominated by errors: {n} of {n} cases failed" in rec["summary"]
    assert d["run_validity"]["valid"] is False and d["run_validity"]["error_rate"] == 1.0
    guarded = d["approaches"]["guarded_rag"]["criteria"]
    assert {c["state"] for c in guarded} == {"insufficient"}  # no "fail" presented as a quality verdict
    assert all("provider or runtime errors" in c["reason"] for c in guarded)
    assert d["next_experiments"] == []
    # Search needs no model, so its criteria are still a real measurement.
    assert d["approaches"]["search"]["run_validity"]["valid"] is True


def test_error_dominated_run_does_not_hide_previous_good_run(db):
    good = live_run(db)
    live_run(db, llm=ScriptedProvider(bad_key))
    live, _ = latest_runs(db)
    assert live["run_id"] == good


def test_max_error_rate_defaults_to_0_2_for_runs_stored_without_it():
    def metrics(provider, n):
        return {"errors": {"count": provider, "n": n, "provider": provider, "withheld": 0}}

    assert run_validity(metrics(2, 10), {})["valid"] is True  # exactly 20% passes
    assert run_validity(metrics(3, 10), {})["valid"] is False
    assert run_validity(metrics(3, 10), {})["max_error_rate"] == 0.2
    assert run_validity(metrics(3, 10), {"max_error_rate": 0.5})["valid"] is True


def test_launch_criteria_file_declares_error_gate():
    from app.decision import criteria_config

    cfg, _ = criteria_config()
    assert cfg["version"] == "1.1.0" and cfg["max_error_rate"] == 0.2


def test_guard_withheld_answers_do_not_trip_the_error_gate(corpus):
    case = load_dataset()["by_id"]["U01"]
    rows = []
    for _ in range(10):
        resp = withheld_response()
        rows.append({"case": case, "response": resp.to_dict(), "grade": grade(case, resp, corpus), "judge": None})
    m = compute_metrics(rows)
    assert m["errors"]["count"] == 10 and m["errors"]["withheld"] == 10 and m["errors"]["provider"] == 0
    assert run_validity(m, {})["valid"] is True


# ---- partial and target-less runs --------------------------------------------------------
def test_case_limited_run_stores_covered_splits_and_partial_flag(db):
    case = load_dataset()["by_id"]["M01"]
    run_id = run_evaluation(db, mode="live", llm=ABSTAIN, case_ids=["M01"], export_dir=None)
    run = db.get_run(run_id)
    assert run["splits"] == [case["split"]]  # not both requested splits
    assert run["partial"] is True
    assert run["config_snapshot"]["run_scope"]["requested_splits"] == ["development", "held_out"]
    assert next(r for r in db.list_runs() if r["run_id"] == run_id)["partial"] is True
    full = live_run(db)
    assert db.get_run(full)["partial"] is False and db.get_run(full)["splits"] == ["held_out"]


def test_latest_runs_skips_partial_runs(db):
    full = live_run(db)
    held_out_case = next(c["case_id"] for c in load_dataset()["cases"] if c["split"] == "held_out")
    live_run(db, case_ids=[held_out_case])  # a `--case` debug run
    live_run(db, approaches=("search", "basic_rag"))  # narrowed approach list
    assert latest_runs(db)[0]["run_id"] == full


def test_latest_runs_skips_runs_without_target_approach_even_without_partial_flag(db):
    full = live_run(db)
    old_style = live_run(db, approaches=("search",))
    with db.connect() as c:  # simulate a run stored before the partial flag existed
        c.execute(
            "UPDATE runs SET config_snapshot = json_remove(config_snapshot, '$.run_scope') WHERE run_id = ?",
            (old_style,),
        )
    assert db.get_run(old_style)["partial"] is False
    assert latest_runs(db)[0]["run_id"] == full


# ---- guard-withheld answers ----------------------------------------------------------------
def test_withheld_answer_is_a_decline_on_unanswerable_and_access_denied_cases(corpus):
    ds = load_dataset()["by_id"]
    unans = grade(ds["U01"], withheld_response(), corpus)
    assert unans["outcome"] == "correct_abstention" and unans["abstained_correctly"] is True
    assert unans["withheld"] is True and unans["error_type"] == "citation_validation_failed"
    denied = grade(ds["R01"], withheld_response(), corpus)
    assert denied["outcome"] == "safe_decline" and denied["abstained_correctly"] is True


def test_withheld_answer_stays_a_miss_on_answerable_cases(corpus):
    g = grade(load_dataset()["by_id"]["S02"], withheld_response(), corpus)
    assert g["outcome"] == "error" and g["deterministic_label"] == "incorrect"


def test_provider_error_is_not_a_decline_on_unanswerable_cases(corpus):
    resp = ApproachResponse.failed("guarded_rag", "timeout: model request timed out")
    g = grade(load_dataset()["by_id"]["U01"], resp, corpus)
    assert g["outcome"] == "error" and g["abstained_correctly"] is False and g["withheld"] is False


def test_withheld_answers_do_not_mark_run_completed_with_errors(db):
    # Every answer cites a nonexistent passage, so the guard withholds it (status "error", kind kept).
    fabricated = ScriptedProvider(lambda s, u: "STATUS: ANSWERED\nANSWER: See the policy [NS-ZZ-999#1].")
    run_id = live_run(db, llm=fabricated, splits=("development",), approaches=("guarded_rag",))
    rows = load_rows(db, run_id)
    withheld = [r for r in rows if r["response"]["guard_reason"] == "citation_validation_failed"]
    assert withheld and all(r["response"]["status"] == "error" for r in withheld)
    assert db.get_run(run_id)["status"] == "completed"
    m = compute_metrics(rows)
    assert m["errors"]["withheld"] == len(withheld) and m["errors"]["provider"] == 0


def test_provider_errors_still_mark_run_completed_with_errors(db):
    run_id = live_run(db, llm=ScriptedProvider(bad_key), splits=("development",), approaches=("guarded_rag",))
    assert db.get_run(run_id)["status"] == "completed_with_errors"


def test_run_usability_is_computed_once_per_completed_run(db, monkeypatch):
    good = live_run(db)
    for _ in range(3):
        live_run(db, llm=ScriptedProvider(bad_key))
    assert latest_runs(db)[0]["run_id"] == good

    calls = []
    original = db.responses_for_run
    monkeypatch.setattr(db, "responses_for_run", lambda run_id: calls.append(run_id) or original(run_id))
    for _ in range(5):
        assert latest_runs(db)[0]["run_id"] == good
    assert calls == []  # /api/runs and /api/decision no longer re-grade skipped runs on every request
