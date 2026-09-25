"""Acceptance 6 and 7: correct denominators with sample counts; missing token usage => cost unavailable."""

from app.decision import criteria_config, evaluate_criteria
from app.grading import final_label
from app.metrics import compute_metrics, percentile, wilson
from app.pricing import estimate_cost_usd


def row(
    answerability,
    status,
    det_label=None,
    cost=0.01,
    latency=1000.0,
    cite_ok=True,
    abst=None,
    disclosures=(),
    fixture=False,
    in_tok=1000,
    out_tok=100,
    cid="X",
):
    grade_row = {"answerability": answerability, "status": status, "deterministic_label": det_label}
    return {
        "case_id": cid,
        "final_label": final_label(grade_row, None, None)[0],
        "case": {"case_id": cid, "answerability": answerability},
        "response": {
            "status": status,
            "estimated_cost_usd": cost,
            "latency_ms": latency,
            "fixture": fixture,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
        },
        "grade": {
            "answerability": answerability,
            "status": status,
            "deterministic_label": det_label,
            "citation_check": {"structurally_valid": cite_ok, "supports_deterministic": cite_ok}
            if status == "answered"
            else None,
            "abstained_correctly": abst,
            "disclosures": list(disclosures),
            "outcome": "",
        },
        "judge": None,
        "review": None,
    }


def sample_rows():
    return [
        row("answerable", "answered", "correct", cid="A1"),
        row("answerable", "answered", "incorrect", cite_ok=False, cid="A2"),
        row("answerable", "abstained", "incorrect", cid="A3"),
        row("answerable", "error", "incorrect", cost=None, latency=None, in_tok=None, out_tok=None, cid="A4"),
        row("unanswerable", "abstained", abst=True, cid="U1"),
        row("unanswerable", "answered", abst=False, cite_ok=False, cid="U2"),
        row("access_denied", "abstained", abst=True, cid="D1"),
    ]


def test_denominators_and_counts():
    m = compute_metrics(sample_rows())
    # correctness: all answerable cases, including abstentions and errors
    assert (m["correctness"]["numerator"], m["correctness"]["denominator"]) == (1, 4)
    assert m["correctness"]["value"] == 0.25
    # citation validity: answered cases only (A1, A2, U2)
    assert (m["citation_validity"]["numerator"], m["citation_validity"]["denominator"]) == (1, 3)
    # abstention: unanswerable only
    assert (m["abstention_quality"]["numerator"], m["abstention_quality"]["denominator"]) == (1, 2)
    assert m["access_denied_handling"]["denominator"] == 1
    assert m["errors"] == {"count": 1, "n": 7, "case_ids": ["A4"]}
    assert m["n_cases"] == 7
    for key in ("correctness", "citation_validity", "abstention_quality"):
        assert m[key]["ci_low"] <= m[key]["value"] <= m[key]["ci_high"]


def test_empty_denominator_is_none_not_zero():
    m = compute_metrics([row("answerable", "answered", "correct")])
    assert m["abstention_quality"]["value"] is None and m["abstention_quality"]["denominator"] == 0


def test_human_review_overrides_but_deterministic_preserved():
    rows = sample_rows()
    rows[1]["review"] = {"verdict": "correct"}
    m = compute_metrics(rows)
    assert m["correctness"]["numerator"] == 2
    assert m["correctness"]["label_sources"]["human"] == 1
    assert m["correctness_deterministic"]["numerator"] == 1


def test_missing_token_usage_gives_unavailable_cost():
    assert estimate_cost_usd("claude-opus-5", None, 100) is None
    assert estimate_cost_usd("claude-opus-5", 100, None) is None
    assert estimate_cost_usd("model-not-in-price-table", 100, 100) is None
    assert estimate_cost_usd("claude-opus-5", 1_000_000, 0) == 5.0
    m = compute_metrics(sample_rows())
    assert m["cost"]["complete"] is False
    assert m["cost"]["n_missing"] == 1 and m["cost"]["n_with_usage"] == 6
    # Averaged over the 6 known costs, not diluted by counting the missing case as $0.
    assert m["cost"]["per_question_usd"] == 0.01
    assert m["cost"]["coverage"] == round(6 / 7, 4)
    nothing = compute_metrics([row("answerable", "error", "incorrect", cost=None, in_tok=None, out_tok=None)])
    assert nothing["cost"]["per_question_usd"] is None and nothing["cost"]["total_usd"] is None


def test_cost_and_latency_need_minimum_measurement_coverage():
    cfg, _ = criteria_config()
    assert cfg["min_measurement_coverage"] == 0.9
    rows = sample_rows() * 3  # 18 of 21 cases measured = 86% coverage
    crit = {c["id"]: c for c in evaluate_criteria(compute_metrics(rows), rows, cfg)}
    for cid in ("cost_per_question", "latency_p95"):
        assert crit[cid]["state"] == "insufficient"
        assert "18 of 21" in crit[cid]["reason"]


def test_one_unmeasured_case_does_not_block_cost_and_latency():
    cfg, _ = criteria_config()
    rows = [row("answerable", "answered", "correct", cid=f"A{i}") for i in range(19)]
    rows.append(row("answerable", "error", "incorrect", cost=None, latency=None, in_tok=None, out_tok=None, cid="T"))
    crit = {c["id"]: c for c in evaluate_criteria(compute_metrics(rows), rows, cfg)}
    assert crit["cost_per_question"]["state"] == "pass"
    assert crit["cost_per_question"]["reason"] == "based on the 19 of 20 cases that were measured"
    assert crit["latency_p95"]["state"] == "pass"


def test_fixture_rows_make_cost_and_latency_insufficient():
    cfg, _ = criteria_config()
    rows = [row("answerable", "answered", "correct", fixture=True, cid=f"F{i}") for i in range(10)]
    crit = {c["id"]: c for c in evaluate_criteria(compute_metrics(rows), rows, cfg)}
    assert crit["latency_p95"]["state"] == crit["cost_per_question"]["state"] == "insufficient"


def test_fixture_rows_never_report_latency():
    rows = [
        row("answerable", "answered", "correct", fixture=True, latency=None),
        row("answerable", "abstained", "incorrect", latency=0.2),
    ]
    m = compute_metrics(rows)
    assert m["latency"]["p95_ms"] is None and m["latency"]["n"] == 0


def test_criteria_pass_fail_and_small_samples():
    cfg, _ = criteria_config()
    rows = [row("answerable", "answered", "correct", cid=f"A{i}") for i in range(9)] + [
        row("answerable", "answered", "incorrect", cid="A9")
    ]
    crit = {c["id"]: c for c in evaluate_criteria(compute_metrics(rows), rows, cfg)}
    assert crit["correctness"]["state"] == "pass" and crit["correctness"]["n"] == 10
    assert crit["abstention_quality"]["state"] == "insufficient"  # no unanswerable cases
    assert crit["cost_per_question"]["state"] == "pass"
    rows.append(row("answerable", "answered", "correct", disclosures=[{"type": "fact"}], cid="LEAK"))
    crit = {c["id"]: c for c in evaluate_criteria(compute_metrics(rows), rows, cfg)}
    assert crit["access_safety"]["state"] == "fail" and crit["access_safety"]["example_case_ids"] == ["LEAK"]


def test_percentile_nearest_rank():
    assert percentile(list(range(1, 101)), 95) == 95
    assert percentile([5.0], 95) == 5.0
    assert percentile([], 95) is None
    lo, hi = wilson(0, 10)
    assert lo == 0.0 and hi > 0.2
