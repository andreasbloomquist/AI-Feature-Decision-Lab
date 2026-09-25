"""Acceptance 1: an employee cannot retrieve or preview an HR-only document."""
from app.access import can_access
from app.citations import validate_citation
from app.llm import ScriptedProvider

HR_DOC = "NS-HR-001"
HR_QUESTION = "What is the salary range for a Level 5 engineer in the US?"


def test_hr_document_is_restricted(corpus):
    doc = corpus.get(HR_DOC)
    assert doc.access_groups == ["HR"]
    assert not can_access("employee", doc)
    assert can_access("hr", doc)
    assert not can_access("finance", doc)


def test_employee_retrieval_never_returns_hr_passages(retriever):
    hits = retriever.retrieve(HR_QUESTION, "employee", k=50)
    assert all(h.passage.document_id != HR_DOC for h in hits)
    # The employee index is built without restricted documents, so they cannot affect scoring either.
    index = retriever.index_for("employee")
    assert not any(p.document_id.startswith("NS-HR-") for p in index.passages)
    assert "$182000" not in index.idf and "182000" not in index.idf


def test_hr_role_can_retrieve_hr_document(retriever):
    hits = retriever.retrieve(HR_QUESTION, "hr", k=3)
    assert hits[0].passage.document_id == HR_DOC


def test_restricted_text_never_enters_model_context(make_approaches):
    prompts = []

    def script(system, user):
        prompts.append(user)
        return "STATUS: ABSTAINED\nANSWER: Not covered."

    approaches = make_approaches(ScriptedProvider(script))
    for name in ("basic_rag", "guarded_rag"):
        approaches[name].run(HR_QUESTION, "employee")
    assert prompts, "model should have been called"
    for p in prompts:
        assert "182,000" not in p and HR_DOC not in p and "Compensation Bands" not in p


def test_citing_restricted_document_is_invalid_and_hidden(corpus):
    c = validate_citation(corpus, "employee", HR_DOC, f"{HR_DOC}#2", {f"{HR_DOC}#2"})
    assert not c.valid and c.reason == "unauthorized"
    assert c.title is None  # title is not revealed


def test_guarded_rag_withholds_answer_citing_restricted_doc(make_approaches):
    llm = ScriptedProvider(lambda s, u: "STATUS: ANSWERED\nANSWER: Level 5 is $182,000 to $218,000 [NS-HR-001#2].")
    resp = make_approaches(llm)["guarded_rag"].run(HR_QUESTION, "employee")
    assert resp.status == "error"
    assert "182,000" not in resp.answer and "NS-HR-001" not in resp.answer
    assert resp.citations == []
    assert "NS-HR-001" not in (resp.error or "")


def test_basic_rag_redacts_restricted_citation_marker(make_approaches):
    llm = ScriptedProvider(lambda s, u: "I think it is in the bands [NS-HR-001#2].")
    resp = make_approaches(llm)["basic_rag"].run(HR_QUESTION, "employee")
    assert "NS-HR-001" not in resp.answer
    assert all(not c.valid for c in resp.citations if c.document_id == "NS-HR-001")


def test_preview_endpoint_enforces_role(client):
    r = client.get("/api/documents/NS-HR-001", params={"role": "employee"})
    assert r.status_code == 403
    body = r.json()
    assert "Compensation" not in r.text and "182,000" not in r.text
    assert body["detail"]["status"] == "access_denied"
    ok = client.get("/api/documents/NS-HR-001", params={"role": "hr"})
    assert ok.status_code == 200 and "182,000" in ok.text


def test_document_list_hides_restricted_titles(client):
    docs = client.get("/api/documents", params={"role": "employee"}).json()
    ids = {d["document_id"] for d in docs}
    assert not ids & {"NS-HR-001", "NS-HR-002", "NS-FIN-001", "NS-ADM-001"}
    admin_ids = {d["document_id"] for d in client.get("/api/documents", params={"role": "admin"}).json()}
    assert {"NS-HR-001", "NS-FIN-001", "NS-ADM-001"} <= admin_ids


def test_unknown_role_rejected(client):
    assert client.get("/api/documents", params={"role": "ceo"}).status_code == 400
