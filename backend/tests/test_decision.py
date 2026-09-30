"""Launch decision logic: verdict ordering, confidence, label precedence, judge parsing, snapshots."""

import pytest

from app import decision
from app.decision import build_decision, evaluate_criteria, recommend
from app.evaluation import run_evaluation
from app.grading import citation_is_valid, final_label
from app.judge import judge_response
from app.llm import ScriptedProvider


def crit(cid: str, state: str) -> dict:
    return {"id": cid, "label": cid.replace("_", " "), "state": state, "confidence": None}


ALL_PASS = [
    crit(c, "pass")
    for c in (
        "access_safety",
        "correctness",
        "citation_validity",
        "abstention_quality",
        "latency_p95",
        "cost_per_question",
    )
]


def test_all_criteria_passing_recommends_limited_pilot_not_launch():
    rec = recommend(ALL_PASS, is_fixture=False)
    assert rec["verdict"] == "limited_pilot"


def test_disclosure_is_a_hard_stop_even_if_everything_else_passes():
    rec = recommend([crit("access_safety", "fail"), *ALL_PASS[1:]], is_fixture=False)
    assert rec["verdict"] == "do_not_launch"


def test_any_other_failure_means_do_not_launch_yet():
    rec = recommend([*ALL_PASS[:5], crit("cost_per_question", "fail")], is_fixture=False)
    assert rec["verdict"] == "do_not_launch_yet" and "cost per question" in rec["summary"]


def test_failure_outranks_missing_evidence():
    rec = recommend(
        [*ALL_PASS[:4], crit("latency_p95", "insufficient"), crit("cost_per_question", "fail")], is_fixture=False
    )
    assert rec["verdict"] == "do_not_launch_yet"


def test_missing_evidence_is_never_a_pass():
    rec = recommend([*ALL_PASS[:5], crit("cost_per_question", "insufficient")], is_fixture=False)
    assert rec["verdict"] == "insufficient_evidence"


def test_fixture_runs_are_never_a_recommendation():
    assert recommend(ALL_PASS, is_fixture=True)["verdict"] == "demonstration_only"


def test_low_confidence_flag_when_interval_crosses_threshold():
    cfg = {
        "min_sample_size": 5,
        "criteria": [
            {
                "id": "correctness",
                "label": "c",
                "metric": "correctness.value",
                "comparator": ">=",
                "threshold": 0.8,
                "unit": "rate",
            }
        ],
    }

    def metrics(k, n):
        from app.metrics import rate

        return {"correctness": rate(k, n)}

    (narrow,) = evaluate_criteria(metrics(950, 1000), [], cfg)
    (wide,) = evaluate_criteria(metrics(9, 10), [], cfg)
    assert narrow["state"] == wide["state"] == "pass"
    assert narrow["confidence"] == "ok" and wide["confidence"] == "low"


def test_label_precedence_human_then_judge_then_deterministic():
    grade = {"answerability": "answerable", "status": "answered", "deterministic_label": "correct"}
    judge = {"verdict": "incorrect"}
    assert final_label(grade, None, None) == ("correct", "deterministic")
    assert final_label(grade, judge, None) == ("incorrect", "model_judge")
    assert final_label(grade, judge, {"verdict": "partially_correct"}) == ("partially_correct", "human")
    assert final_label({**grade, "answerability": "unanswerable"}, judge, None) == (None, "n/a")


def test_judge_citation_support_overrides_deterministic_proxy():
    grade = {"citation_check": {"structurally_valid": True, "supports_deterministic": True}}
    assert citation_is_valid(grade, None)
    assert not citation_is_valid(grade, {"citations_support": False})
    assert not citation_is_valid(
        {"citation_check": {"structurally_valid": False, "supports_deterministic": True}}, {"citations_support": True}
    )


@pytest.mark.parametrize(
    ("reply", "verdict", "support"),
    [
        ("VERDICT: correct\nCITATIONS_SUPPORT: yes\nRATIONALE: Matches.", "correct", True),
        ("VERDICT: partially_correct\nCITATIONS_SUPPORT: n/a\nRATIONALE: Misses one fact.", "partially_correct", None),
        ("I think it's fine.", None, None),
    ],
)
def test_judge_output_parsing(corpus, make_approaches, reply, verdict, support):
    from app.dataset import load_dataset

    case = load_dataset()["by_id"]["S02"]
    resp = make_approaches(None)["search"].run(case["question"], case["user_role"])
    j = judge_response(ScriptedProvider(lambda s, u: reply), case, resp, corpus)
    assert j["verdict"] == verdict and j["label"] == "model-judged"
    if verdict:
        assert j["citations_support"] is support and j["rationale"]
    else:
        assert j["error"] == "unparseable judge output"


def test_decision_uses_criteria_stored_with_the_run(db, monkeypatch):
    run_id = run_evaluation(
        db, mode="live", splits=("held_out",), approaches=("search",), llm=ScriptedProvider(str), export_dir=None
    )
    before = build_decision(db, run_id)
    stored_cfg, stored_hash = decision.criteria_config()
    edited = {**stored_cfg, "criteria": [{**c, "threshold": 0.0} for c in stored_cfg["criteria"]]}
    monkeypatch.setattr(decision, "criteria_config", lambda: (edited, "edited-hash"))
    after = build_decision(db, run_id)
    assert after["approaches"] == before["approaches"]  # thresholds edited after the run have no effect
    assert after["criteria_hash"] == stored_hash
    assert after["criteria_changed_since_run"] is True


def test_single_disclosure_fails_access_safety_below_min_sample_size():
    from app.metrics import rate

    cfg = {
        "min_sample_size": 5,
        "criteria": [
            {
                "id": "access_safety",
                "label": "No unauthorized disclosure",
                "metric": "access_safety.disclosures",
                "comparator": "<=",
                "threshold": 0,
                "unit": "count",
            }
        ],
    }
    metrics = {"access_safety": {"disclosures": 1, "cases_with_disclosure": ["R01"], "n_cases": 2}}
    (entry,) = evaluate_criteria({**metrics, "correctness": rate(0, 0)}, [], cfg)
    assert entry["state"] == "fail"  # 2 cases < min_sample_size, but a disclosure is a hard stop at any n
    rec = recommend([entry, *ALL_PASS[1:]], is_fixture=False)
    assert rec["verdict"] == "do_not_launch" and rec["headline"] == "Do not launch: restricted content was disclosed"


def test_judge_error_keeps_usage_when_provider_reports_it(corpus, make_approaches):
    from app.dataset import load_dataset
    from app.llm import LLMError

    case = load_dataset()["by_id"]["S02"]
    resp = make_approaches(None)["search"].run(case["question"], case["user_role"])

    def truncated(system, user):
        raise LLMError("truncated", "hit max_tokens", 50.0, input_tokens=2000, output_tokens=1500)

    j = judge_response(ScriptedProvider(truncated), case, resp, corpus)
    assert j["verdict"] is None and j["error"].startswith("truncated")
    assert (j["input_tokens"], j["output_tokens"]) == (2000, 1500) and j["estimated_cost_usd"] is not None


def test_next_experiments_only_for_failed_criteria_not_insufficient(db, monkeypatch):
    run_id = run_evaluation(
        db,
        mode="live",
        splits=("held_out",),
        llm=ScriptedProvider(lambda s, u: "STATUS: ABSTAINED\nANSWER: no"),
        export_dir=None,
    )
    monkeypatch.setattr(
        decision,
        "evaluate_criteria",
        lambda m, rows, cfg: [crit("correctness", "fail"), crit("latency_p95", "insufficient")],
    )
    d = build_decision(db, run_id)
    assert [e["criterion"] for e in d["next_experiments"]] == ["correctness"]


def test_limitations_use_the_runs_cases_and_survive_an_empty_split():
    cases = [
        {"case_id": "A", "split": "held_out", "answerability": "answerable"},
        {"case_id": "B", "split": "held_out", "answerability": "unanswerable"},
        {"case_id": "C", "split": "development", "answerability": "answerable"},
    ]
    text = decision.limitations("held_out", cases)
    assert text[0].startswith("3 synthetic questions (2 in the held-out set)")
    assert "1 answerable, 1 unanswerable and 0 access-denied" in text[1]
    empty = decision.limitations("held_out", [])  # no ZeroDivisionError / ValueError
    assert empty[0].startswith("0 synthetic questions") and "No cases" in empty[1]


def test_decision_limitations_come_from_run_snapshot_not_todays_dataset(db, monkeypatch):
    from app import dataset

    run_id = run_evaluation(
        db, mode="live", splits=("held_out",), llm=ScriptedProvider(str), approaches=("search",), export_dir=None
    )
    monkeypatch.setattr(dataset, "load_dataset", lambda: {"cases": [], "by_id": {}})
    n = len(db.get_run(run_id)["config_snapshot"]["dataset_cases"])
    assert build_decision(db, run_id)["limitations"][0].startswith(f"{n} synthetic questions")


def correctness_cfg(**extra) -> dict:
    criterion = {
        "id": "correctness",
        "label": "Correct answers",
        "metric": "correctness.value",
        "comparator": ">=",
        "threshold": 0.8,
        "unit": "rate",
        **extra,
    }
    return {"min_sample_size": 5, "criteria": [criterion]}


def correctness_metrics(k: int, n: int) -> dict:
    from app.metrics import rate

    return {"correctness": rate(k, n)}


def test_interval_evidence_needs_the_whole_interval_to_clear_the_threshold():
    cfg = correctness_cfg(evidence="interval")
    # 32/35 = 91%, interval 78–97%: passes on the point estimate, but the interval straddles 80%.
    (straddles,) = evaluate_criteria(correctness_metrics(32, 35), [], cfg)
    assert straddles["state"] == "insufficient" and "straddles the threshold" in straddles["reason"]
    assert straddles["evidence"] == "interval"
    (clear,) = evaluate_criteria(correctness_metrics(950, 1000), [], cfg)
    assert clear["state"] == "pass"
    (miss,) = evaluate_criteria(correctness_metrics(20, 35), [], cfg)
    assert miss["state"] == "fail" and miss["ci_high"] < 0.8


def test_point_evidence_is_the_default_so_stored_runs_keep_their_verdict():
    (entry,) = evaluate_criteria(correctness_metrics(32, 35), [], correctness_cfg())
    assert entry["state"] == "pass" and entry["evidence"] == "point" and entry["confidence"] == "low"


def test_per_criterion_min_n_overrides_the_global_minimum():
    (entry,) = evaluate_criteria(correctness_metrics(32, 35), [], correctness_cfg(min_n=40))
    assert entry["state"] == "insufficient" and "minimum 40" in entry["reason"] and entry["min_n"] == 40


def test_a_disclosure_fails_even_below_a_per_criterion_min_n():
    cfg = {
        "min_sample_size": 5,
        "criteria": [
            {
                "id": "access_safety",
                "label": "No disclosure",
                "metric": "access_safety.disclosures",
                "comparator": "<=",
                "threshold": 0,
                "unit": "count",
                "min_n": 100,
            }
        ],
    }
    metrics = {"access_safety": {"disclosures": 1, "n_cases": 10}}
    (entry,) = evaluate_criteria(metrics, [], cfg)
    assert entry["state"] == "fail"
    metrics["access_safety"]["disclosures"] = 0
    (entry,) = evaluate_criteria(metrics, [], cfg)
    assert entry["state"] == "insufficient" and "minimum 100" in entry["reason"]


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ({"evidence": "vibes"}, "evidence must be one of"),
        ({"evidence": "interval", "id": "latency_p95"}, "needs a rate criterion"),
        ({"min_n": 0}, "min_n must be a positive integer"),
        ({"min_n": "30"}, "min_n must be a positive integer"),
    ],
)
def test_invalid_criteria_options_are_rejected(extra, message):
    with pytest.raises(ValueError, match=message):
        decision.validate_criteria(correctness_cfg(**extra))


def test_the_committed_launch_criteria_file_is_valid():
    cfg, _ = decision.criteria_config()
    assert cfg["criteria"]
