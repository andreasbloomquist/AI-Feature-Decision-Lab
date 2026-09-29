import pytest
from fastapi.testclient import TestClient

from app import main
from app.db import Database
from app.evaluation import run_evaluation
from app.llm import ScriptedProvider


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
    r = client.post(
        "/api/ask", json={"question": "Can I expense a client dinner without a receipt?", "role": "employee"}
    )
    body = r.json()
    assert body["fixture"] is True
    by = {x["approach"]: x for x in body["responses"]}
    assert by["search"]["fixture"] is False and by["search"]["latency_ms"] is not None
    assert by["guarded_rag"]["fixture"] is True and by["guarded_rag"]["latency_ms"] is None
    assert by["guarded_rag"]["estimated_cost_usd"] is None
    assert "raw_output" not in by["guarded_rag"]


def test_ask_unknown_question_in_fixture_mode_is_explained(client):
    body = client.post(
        "/api/ask",
        json={"question": "What's the wifi password?", "role": "employee", "approaches": ["guarded_rag", "basic_rag"]},
    ).json()
    for r in body["responses"]:
        assert r["status"] in ("error", "abstained")
        if r["status"] == "error":
            assert r["error"].startswith("fixture_missing")


def test_review_preserves_automated_score(client):
    run_id = client.get("/api/runs").json()[0]["run_id"]
    cases = client.get(
        f"/api/runs/{run_id}/cases", params={"approach": "basic_rag", "category": "outdated_policy"}
    ).json()
    target = next(c for c in cases if c["case_id"] == "O02")
    before = client.get(f"/api/runs/{run_id}/cases/O02").json()
    before_grade = next(r for r in before["responses"] if r["approach"] == "basic_rag")["grade"]

    r = client.post(
        f"/api/responses/{target['response_id']}/reviews",
        json={"verdict": "incorrect", "note": "Says VP approval is needed; contradicts 2026 policy.", "reviewer": "pm"},
    )
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


def test_no_secret_in_any_response_database_or_export(tmp_path, monkeypatch):
    secret = "sk-ant-test-DO-NOT-LEAK-123456"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://127.0.0.1:9")  # closed port: model calls fail fast
    monkeypatch.setenv("LLM_MAX_RETRIES", "0")
    monkeypatch.setenv("LAB_DB_PATH", str(tmp_path / "s.sqlite3"))
    monkeypatch.delenv("FIXTURE_MODE", raising=False)
    main.reset_caches()
    try:
        with TestClient(main.app) as c:
            assert c.get("/api/health").json()["live_available"] is True
            asked = c.post("/api/ask", json={"question": "Who approves travel over $2,000?", "role": "employee"})
            assert {r["status"] for r in asked.json()["responses"]} >= {"error"}  # live call failed, visibly
            run_id = c.get("/api/runs").json()[0]["run_id"]
            texts = [asked.text] + [
                c.get(path).text
                for path in (
                    "/api/health",
                    "/api/config",
                    "/api/runs",
                    "/api/decision",
                    f"/api/runs/{run_id}",
                    f"/api/runs/{run_id}/cases",
                    f"/api/runs/{run_id}/cases/S02",
                )
            ]
        db = Database(tmp_path / "s.sqlite3")
        live_run = run_evaluation(
            db,
            mode="live",
            splits=("development",),
            approaches=("search",),
            llm=ScriptedProvider(str),
            export_dir=tmp_path / "export",
        )
        texts.append((tmp_path / "export" / f"{live_run}.json").read_text())
        texts.append((tmp_path / "s.sqlite3").read_bytes().decode("latin-1"))
        for text in texts:
            assert secret not in text and "sk-ant" not in text
    finally:
        main.reset_caches()


@pytest.mark.parametrize("question", ["   ", "  hi  ", "\n\t \n"])
def test_whitespace_only_question_is_rejected(client, question):
    assert client.post("/api/ask", json={"question": question, "role": "employee"}).status_code == 422


def test_review_does_not_export_a_running_run(client, tmp_path, monkeypatch):
    monkeypatch.setattr(main, "RESULTS_DIR", tmp_path / "results")
    db = main.get_db()
    fixture_run = db.get_run(client.get("/api/runs").json()[0]["run_id"])
    run_id = "live-still-running"
    db.create_run({**fixture_run, "run_id": run_id, "mode": "live", "status": "running"})
    response_id = db.add_response(run_id, "S02", "search", {"status": "answered"}, {}, None)
    r = client.post(f"/api/responses/{response_id}/reviews", json={"verdict": "correct", "reviewer": "pm"})
    assert r.status_code == 200
    assert not (tmp_path / "results" / "runs" / f"{run_id}.json").exists()
    db.finish_run(run_id, "completed", {})
    client.post(f"/api/responses/{response_id}/reviews", json={"verdict": "incorrect", "reviewer": "pm"})
    assert (tmp_path / "results" / "runs" / f"{run_id}.json").exists()


def test_runs_endpoint_marks_only_the_decision_run_as_latest(client):
    runs = client.get("/api/runs").json()
    assert all("latest" in r for r in runs)
    # Only fixture runs exist in the test database, so no run is the live decision run.
    assert not any(r["latest"] for r in runs if r["mode"] == "fixture")


@pytest.mark.parametrize("reviewer", [None, "", "   "])
def test_review_requires_a_reviewer(client, reviewer):
    run_id = client.get("/api/runs").json()[0]["run_id"]
    response_id = client.get(f"/api/runs/{run_id}/cases").json()[0]["response_id"]
    body = {"verdict": "correct"} if reviewer is None else {"verdict": "correct", "reviewer": reviewer}
    assert client.post(f"/api/responses/{response_id}/reviews", json=body).status_code == 422


def test_decision_and_memo_disclose_human_overrides(client):
    from app.decision import human_override_note

    before = client.get("/api/decision").json()["decision"]
    assert human_override_note(before) is None
    run_id = before["run_id"]

    def answerable_row(approach):
        rows = client.get(f"/api/runs/{run_id}/cases", params={"approach": approach, "split": "held_out"}).json()
        return next(r for r in rows if r["answerability"] == "answerable" and r["final_label"] == "correct")

    def review(row, verdict):
        client.post(f"/api/responses/{row['response_id']}/reviews", json={"verdict": verdict, "reviewer": "pm"})
        return client.get("/api/decision").json()["decision"]

    # Agreeing with the automated label is a confirmation, not an override.
    target_row = answerable_row("guarded_rag")
    confirmed = review(target_row, "correct")
    assert confirmed["approaches"]["guarded_rag"]["human_reviews"] == {"reviewed": 1, "changed": 0}
    assert human_override_note(confirmed) is None

    # Reviews that flip the baseline's labels move the lift, so they are disclosed too.
    flipped = review(answerable_row("search"), "incorrect")
    note = human_override_note(flipped)
    assert "1 of 35 for Search" in note and "1 more review(s) confirmed" in note
    assert "Guarded RAG" not in note

    changed = review(target_row, "incorrect")
    assert "1 of 35 for Guarded RAG" in human_override_note(changed)
