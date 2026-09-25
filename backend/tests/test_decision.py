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
