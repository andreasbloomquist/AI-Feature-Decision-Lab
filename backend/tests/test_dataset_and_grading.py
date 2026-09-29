from collections import Counter

import pytest

from app.dataset import load_dataset, validate_cases
from app.grading import check_facts, final_label, find_disclosures, grade, normalize, phrase_present
from app.schemas import ApproachResponse, Citation


def test_dataset_composition():
    cases = load_dataset()["cases"]
    assert len(cases) == 60
    assert Counter(c["category"] for c in cases) == {
        "single_document": 24,
        "multi_document": 12,
        "outdated_policy": 8,
        "unanswerable": 8,
        "role_access": 8,
    }
    assert Counter(c["split"] for c in cases) == {"development": 15, "held_out": 45}
    assert len({c["case_id"] for c in cases}) == 60


def test_dataset_references_real_documents(corpus):
    for c in load_dataset()["cases"]:
        for d in c["acceptable_document_ids"] + c["forbidden_document_ids"]:
            assert corpus.get(d) is not None, (c["case_id"], d)
        if c["answerability"] == "answerable":
            assert c["required_facts"] and c["acceptable_document_ids"]
            assert all(corpus.get(d).is_active for d in c["acceptable_document_ids"])


def test_reference_answers_satisfy_their_own_facts():
    for c in load_dataset()["cases"]:
        assert all(f["found"] for f in check_facts(c, c["reference_answer"])), c["case_id"]


def test_access_denied_references_do_not_leak():
    for c in load_dataset()["cases"]:
        if c["answerability"] == "access_denied":
            assert c["forbidden_document_ids"] and c["forbidden_facts"]
            assert not any(phrase_present(f, normalize(c["reference_answer"])) for f in c["forbidden_facts"])


def test_fact_matching_is_word_bounded():
    assert phrase_present("no", normalize("No, it is not allowed."))
    assert not phrase_present("no", normalize("Northstar policy"))
    assert phrase_present("$2,000", normalize("over $2000 needs"))
    assert not phrase_present("$2,500", normalize("costs $25,000"))


def _resp(answer, citations=(), retrieved=(), status="answered"):
    return ApproachResponse("guarded_rag", answer, status, list(citations), list(retrieved), 1.0, 1, 1, 0.0)


def test_disclosure_detection(corpus):
    case = load_dataset()["by_id"]["R01"]
    leak = _resp("The band is $182,000 to $218,000.")
    types = {d["type"] for d in find_disclosures(case, leak, corpus)}
    assert "fact" in types
    cited = _resp("See policy.", [Citation("NS-HR-001", "NS-HR-001#2", None, False, "unauthorized")])
    assert any(d["type"] == "document_id" for d in find_disclosures(case, cited, corpus))
    verbatim = _resp("Offers above the top of a band need approval from the Chief People Officer.")
    assert any(d["type"] == "passage" for d in find_disclosures(case, verbatim, corpus))
    safe = _resp("I couldn't find this.", status="abstained")
    assert find_disclosures(case, safe, corpus) == []
    assert grade(case, safe, corpus)["outcome"] == "safe_decline"
    # The same text is not a disclosure for a role that may read the document.
    hr_case = load_dataset()["by_id"]["R02"]
    assert find_disclosures(hr_case, leak, corpus) == []


def test_grade_outcomes(corpus):
    ds = load_dataset()["by_id"]
    ok = _resp(
        "Your department head (VP) and your manager approve it [NS-TRV-2026#3].",
        [Citation("NS-TRV-2026", "NS-TRV-2026#3", "Travel Policy (2026)", True)],
        ["NS-TRV-2026"],
    )
    g = grade(ds["S02"], ok, corpus)
    assert g["outcome"] == "correct" and g["citation_check"]["structurally_valid"]
    invented = _resp("Yes, 3% match [NS-CARD-001#1].", [Citation("NS-CARD-001", "NS-CARD-001#1", "x", True)])
    g = grade(ds["U01"], invented, corpus)
    assert g["outcome"] == "invented_answer" and not g["citation_check"]["supports_deterministic"]


def test_disclosure_detection_is_case_insensitive_and_covers_warnings(corpus):
    case = load_dataset()["by_id"]["R01"]
    lower = _resp("Look at ns-hr-001 for bands.")
    assert any(d["type"] == "document_id" for d in find_disclosures(case, lower, corpus))
    warned = _resp("See policy.")
    warned.warnings.append("invalid citations: NS-HR-001 (unauthorized)")
    assert any(d["type"] == "document_id" for d in find_disclosures(case, warned, corpus))


@pytest.mark.parametrize(
    ("field", "value"),
    [("user_role", "ceo"), ("split", "test"), ("answerability", "maybe"), ("category", "other")],
)
def test_dataset_validation_rejects_unknown_values(field, value):
    case = dict(load_dataset()["cases"][0], **{field: value})
    with pytest.raises(ValueError, match=field):
        validate_cases([case])


def test_dataset_validation_rejects_duplicate_ids():
    case = load_dataset()["cases"][0]
    with pytest.raises(ValueError, match="duplicate"):
        validate_cases([case, dict(case)])


def test_correct_answer_with_restricted_fact_never_succeeds(corpus):
    from app.results import succeeded

    case = load_dataset()["by_id"]["S02"]
    leaky = _resp(
        "Your department head (VP) and your manager approve it [NS-TRV-2026#3]. A Level 5 band starts at $182,000.",
        [Citation("NS-TRV-2026", "NS-TRV-2026#3", "Travel Policy (2026)", True)],
        ["NS-TRV-2026"],
    )
    g = grade(case, leaky, corpus)
    assert g["deterministic_label"] == "correct" and g["disclosures"]
    row = {"grade": g, "final_label": final_label(g, None, None)[0]}
    assert row["final_label"] == "correct" and succeeded(row) is False
