"""Acceptance 2: a superseded document cannot be cited as current policy."""

from app.citations import validate_citation
from app.grading import citation_check
from app.llm import ScriptedProvider

Q = "Who approves travel over $2,000?"


def test_superseded_documents_are_not_retrieved(retriever):
    for role in ("employee", "admin"):
        hits = retriever.retrieve("travel policy 2025 approval $1,500 per diem $65", role, k=100)
        ids = {h.passage.document_id for h in hits}
        assert "NS-TRV-2025" not in ids and "NS-HOM-2024" not in ids
        assert "NS-TRV-2026" in ids


def test_superseded_citation_is_invalid(corpus):
    c = validate_citation(corpus, "employee", "NS-TRV-2025", "NS-TRV-2025#3", {"NS-TRV-2025#3"})
    assert not c.valid and c.reason == "superseded"


def test_guarded_rag_rejects_answer_citing_superseded_policy(make_approaches):
    llm = ScriptedProvider(lambda s, u: "STATUS: ANSWERED\nANSWER: Trips over $1,500 need VP approval [NS-TRV-2025#3].")
    resp = make_approaches(llm)["guarded_rag"].run(Q, "employee")
    assert resp.status == "error"
    assert resp.error.startswith("citation_validation_failed")
    assert "superseded" in resp.error
    assert resp.citations == []


def test_basic_rag_flags_superseded_citation(make_approaches, corpus):
    llm = ScriptedProvider(lambda s, u: "Trips over $1,500 need VP approval [NS-TRV-2025#3].")
    resp = make_approaches(llm)["basic_rag"].run(Q, "employee")
    assert [c.reason for c in resp.citations] == ["superseded"]
    assert resp.warnings and "superseded" in resp.warnings[-1]
    case = {
        "user_role": "employee",
        "acceptable_document_ids": ["NS-TRV-2026"],
        "forbidden_document_ids": ["NS-TRV-2025"],
    }
    check = citation_check(case, resp, corpus)
    assert check["active"] is False and check["structurally_valid"] is False


def test_preview_of_superseded_document_is_labeled(client):
    doc = client.get("/api/documents/NS-TRV-2025", params={"role": "employee"}).json()
    assert doc["status"] == "superseded" and doc["superseded_by"] == "NS-TRV-2026"


def test_guarded_rag_may_name_an_accessible_superseded_policy_in_prose(make_approaches):
    answer = "The approval threshold rose from $1,500 under NS-TRV-2025 to $2,000 [NS-TRV-2026#7]."
    llm = ScriptedProvider(lambda s, u: f"STATUS: ANSWERED\nANSWER: {answer}")
    resp = make_approaches(llm)["guarded_rag"].run("What changed in the 2026 travel policy?", "employee")
    assert resp.status == "answered", resp.error
    assert [c.document_id for c in resp.citations] == ["NS-TRV-2026"]
