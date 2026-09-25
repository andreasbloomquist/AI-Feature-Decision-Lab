"""Acceptance 3 and 4: abstention on unanswerable questions; fabricated citations are rejected."""
from app.approaches.base import ABSTAIN_MESSAGE
from app.citations import parse_citation_markers, validate_citation
from app.llm import ScriptedProvider

UNANSWERABLE = "Does Northstar match 401(k) contributions?"


def _fail(*_):
    raise AssertionError("model must not be called")


def test_guarded_rag_abstains_below_retrieval_floor_without_model_call(make_approaches):
    resp = make_approaches(ScriptedProvider(_fail))["guarded_rag"].run(UNANSWERABLE, "employee")
    assert resp.status == "abstained"
    assert resp.guard_reason.startswith("retrieval_below_floor")
    assert resp.estimated_cost_usd == 0.0 and resp.answer == ABSTAIN_MESSAGE


def test_guarded_rag_passes_through_model_abstention(make_approaches):
    llm = ScriptedProvider(lambda s, u: "STATUS: ABSTAINED\nANSWER: The policies do not mention a phone stipend.")
    resp = make_approaches(llm)["guarded_rag"].run("How much is the monthly mobile phone stipend?", "employee")
    assert resp.status == "abstained" and resp.guard_reason == "model_abstained"


def test_search_abstains_below_threshold(make_approaches):
    resp = make_approaches(None)["search"].run(UNANSWERABLE, "employee")
    assert resp.status == "abstained"
    assert resp.estimated_cost_usd == 0.0


def test_guarded_rag_requires_citations(make_approaches):
    llm = ScriptedProvider(lambda s, u: "STATUS: ANSWERED\nANSWER: Your VP approves it.")
    resp = make_approaches(llm)["guarded_rag"].run("Who approves travel over $2,000?", "employee")
    assert resp.status == "abstained" and resp.guard_reason.startswith("no_citations")


def test_fabricated_citation_rejected_by_guarded_rag(make_approaches):
    llm = ScriptedProvider(lambda s, u: "STATUS: ANSWERED\nANSWER: Your VP approves trips over $2,000 [NS-TRV-2027#9].")
    resp = make_approaches(llm)["guarded_rag"].run("Who approves travel over $2,000?", "employee")
    assert resp.status == "error"
    assert "unknown_document" in resp.error
    assert resp.citations == [] and "NS-TRV-2027" not in resp.answer


def test_citation_to_real_passage_outside_context_rejected(make_approaches):
    llm = ScriptedProvider(lambda s, u: "STATUS: ANSWERED\nANSWER: Your VP approves it [NS-DAT-001#2].")
    resp = make_approaches(llm)["guarded_rag"].run("Who approves travel over $2,000?", "employee")
    assert resp.status == "error" and "not_in_context" in resp.error


def test_fabricated_citation_never_marked_valid_in_basic_rag(make_approaches):
    llm = ScriptedProvider(lambda s, u: "Your VP approves trips over $2,000 [NS-TRV-2026#3][NS-FAKE-001#1].")
    resp = make_approaches(llm)["basic_rag"].run("Who approves travel over $2,000?", "employee")
    by_id = {c.document_id: c for c in resp.citations}
    assert by_id["NS-TRV-2026"].valid
    assert not by_id["NS-FAKE-001"].valid and by_id["NS-FAKE-001"].reason == "unknown_document"


def test_valid_guarded_answer(make_approaches):
    llm = ScriptedProvider(
        lambda s, u: "STATUS: ANSWERED\nANSWER: Trips over $2,000 need your department head (VP) and your manager to approve [NS-TRV-2026#3]."
    )
    resp = make_approaches(llm)["guarded_rag"].run("Who approves travel over $2,000?", "employee")
    assert resp.status == "answered"
    assert [c.passage_id for c in resp.citations] == ["NS-TRV-2026#3"] and resp.citations[0].valid
    assert resp.input_tokens == 1000 and resp.estimated_cost_usd is not None


def test_unparseable_guarded_output_is_error(make_approaches):
    resp = make_approaches(ScriptedProvider(lambda s, u: "Sure! Your VP."))["guarded_rag"].run(
        "Who approves travel over $2,000?", "employee")
    assert resp.status == "error" and resp.error.startswith("unparseable_output")


def test_marker_parsing():
    assert parse_citation_markers("a [NS-TRV-2026#3] b [NS-EXP-001, NS-ENT-001#2] [note]") == [
        ("NS-TRV-2026", "NS-TRV-2026#3"), ("NS-EXP-001", None), ("NS-ENT-001", "NS-ENT-001#2")]


def test_document_level_citation_maps_to_context_passage(corpus):
    c = validate_citation(corpus, "employee", "NS-TRV-2026", None, {"NS-TRV-2026#3", "NS-TRV-2026#5"})
    assert c.valid and c.passage_id == "NS-TRV-2026#3"
