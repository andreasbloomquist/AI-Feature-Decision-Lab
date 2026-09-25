import os


def test_health_reports_fixture_mode(client):
    h = client.get("/api/health").json()
    assert h["mode"] == "fixture" and h["live_available"] is False


def test_decision_without_live_run(client):
    d = client.get("/api/decision").json()
    assert d["live_available"] is False
    assert d["message"] == "No live evaluation yet"
    assert d["decision"]["run_mode"] == "fixture"
    assert d["decision"]["recommendation"]["verdict"] == "demonstration_only"
    guarded = {c["id"]: c for c in d["decision"]["approaches"]["guarded_rag"]["criteria"]}
    assert guarded["latency_p95"]["state"] == "insufficient"
    assert guarded["cost_per_question"]["state"] == "insufficient"


def test_ask_in_fixture_mode(client):
    r = client.post("/api/ask", json={"question": "Can I expense a client dinner without a receipt?", "role": "employee"})
    body = r.json()
    assert body["fixture"] is True
    by = {x["approach"]: x for x in body["responses"]}
    assert by["search"]["fixture"] is False and by["search"]["latency_ms"] is not None
    assert by["guarded_rag"]["fixture"] is True and by["guarded_rag"]["latency_ms"] is None
    assert by["guarded_rag"]["estimated_cost_usd"] is None
    assert "raw_output" not in by["guarded_rag"]


def test_ask_unknown_question_in_fixture_mode_is_explained(client):
    body = client.post("/api/ask", json={"question": "What's the wifi password?", "role": "employee",
                                          "approaches": ["guarded_rag", "basic_rag"]}).json()
    for r in body["responses"]:
        assert r["status"] in ("error", "abstained")
        if r["status"] == "error":
            assert r["error"].startswith("fixture_missing")


def test_review_preserves_automated_score(client):
    run_id = client.get("/api/runs").json()[0]["run_id"]
    cases = client.get(f"/api/runs/{run_id}/cases", params={"approach": "basic_rag", "category": "outdated_policy"}).json()
    target = next(c for c in cases if c["case_id"] == "O02")
    before = client.get(f"/api/runs/{run_id}/cases/O02").json()
    before_grade = next(r for r in before["responses"] if r["approach"] == "basic_rag")["grade"]

    r = client.post(f"/api/responses/{target['response_id']}/reviews",
                    json={"verdict": "incorrect", "note": "Says VP approval is needed; contradicts 2026 policy."})
    assert r.status_code == 200
    assert r.json()["automated_grade"] == before_grade

    after = client.get(f"/api/runs/{run_id}/cases/O02").json()
    row = next(x for x in after["responses"] if x["approach"] == "basic_rag")
    assert row["grade"] == before_grade
    assert row["final_label"] == "incorrect" and row["final_label_source"] == "human"
    assert row["reviews"][-1]["note"].startswith("Says VP")


def test_case_filters(client):
    run_id = client.get("/api/runs").json()[0]["run_id"]
    errs = client.get(f"/api/runs/{run_id}/cases", params={"error_type": "timeout"}).json()
    assert errs and all(c["status"] == "error" for c in errs)
    unans = client.get(f"/api/runs/{run_id}/cases", params={"category": "unanswerable", "approach": "search"}).json()
    assert len(unans) == 8


def test_no_secret_in_any_response(tmp_path, monkeypatch):
    secret = "sk-ant-test-DO-NOT-LEAK-123456"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
    monkeypatch.setenv("LAB_DB_PATH", str(tmp_path / "s.sqlite3"))
    monkeypatch.delenv("FIXTURE_MODE", raising=False)
    from fastapi.testclient import TestClient

    from app import main

    main.get_settings.cache_clear()
    main.get_db.cache_clear()
    try:
        with TestClient(main.app) as c:
            for path in ("/api/health", "/api/config", "/api/runs", "/api/decision"):
                r = c.get(path)
                assert secret not in r.text
                assert "sk-ant" not in r.text
            assert c.get("/api/health").json()["live_available"] is True
            run_id = c.get("/api/runs").json()[0]["run_id"]
            assert secret not in c.get(f"/api/runs/{run_id}").text
        raw = (tmp_path / "s.sqlite3").read_bytes()
        assert secret.encode() not in raw
    finally:
        main.get_settings.cache_clear()
        main.get_db.cache_clear()
        os.environ.pop("ANTHROPIC_API_KEY", None)
