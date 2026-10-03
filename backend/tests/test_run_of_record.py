"""The decision run of record (roadmap R1.1) and the held-out usage counter (R1.2).

A PM names the run a decision rests on; from then on it is the decision run, and human reviews of its
held-out responses are locked. Every live evaluation of the held-out set is counted per dataset version,
so "we ran it until it passed" is visible.
"""

import sqlite3

import pytest

from app import main, results
from app.dataset import load_dataset
from app.db import Database, WriteRefused
from app.decision import build_decision
from app.evaluation import run_evaluation
from app.llm import LLMError, ScriptedProvider
from app.reports import decision_memo
from app.results import held_out_usage, latest_runs

ABSTAIN = ScriptedProvider(lambda s, u: "STATUS: ABSTAINED\nANSWER: Not covered.")
LOCKED = "reviews are locked: this response belongs to the decision run of record"


def bad_key(system, user):
    raise LLMError("auth", "provider rejected the API key", latency_ms=5.0)


def live_run(db, llm=ABSTAIN, **kwargs):
    kwargs.setdefault("splits", ("held_out",))
    return run_evaluation(db, mode="live", llm=llm, export_dir=None, **kwargs)


@pytest.fixture
def api(client, tmp_path, monkeypatch):
    """The API client plus its database; reviews of live runs export into a temporary directory."""
    monkeypatch.setattr(main, "RESULTS_DIR", tmp_path / "results")
    return client, main.get_db()


def backdate(db, run_id):
    """Make a run older than any other: runs created in the same second would otherwise tie."""
    with db.connect() as c:
        c.execute("UPDATE runs SET created_at = '2026-01-01T00:00:00Z' WHERE run_id = ?", (run_id,))
    return run_id


def designate(client, run_id, name="Dana (PM)", note=None):
    return client.post(f"/api/runs/{run_id}/designate", json={"designated_by": name, "note": note})


def response_id(client, run_id, split):
    rows = client.get(f"/api/runs/{run_id}/cases", params={"split": split, "approach": "guarded_rag"}).json()
    return rows[0]["response_id"]


def review(client, rid):
    return client.post(f"/api/responses/{rid}/reviews", json={"verdict": "incorrect", "reviewer": "pm"})


# ---- who may be designated --------------------------------------------------------------
def test_fixture_run_can_never_be_designated(api):
    client, db = api
    fixture = next(r for r in db.list_runs() if r["mode"] == "fixture")
    r = designate(client, fixture["run_id"])
    assert r.status_code == 409 and "Fixture runs" in r.json()["detail"]
    assert db.designations("held_out") == []


def test_partial_error_dominated_and_development_only_runs_are_rejected(api):
    client, db = api
    held_out_case = next(c["case_id"] for c in load_dataset()["cases"] if c["split"] == "held_out")
    partial = live_run(db, case_ids=[held_out_case])
    broken = live_run(db, llm=ScriptedProvider(bad_key))
    dev_only = live_run(db, splits=("development",))
    expected = {partial: "partial run", broken: "dominated by provider errors", dev_only: "does not cover the held-out"}
    for run_id, reason in expected.items():
        r = designate(client, run_id)
        assert r.status_code == 409, run_id
        assert reason in r.json()["detail"]
    assert db.designations("held_out") == []
    assert designate(client, "no-such-run").status_code == 404


@pytest.mark.parametrize("name", [None, "", "   "])
def test_designation_requires_a_name(api, name):
    client, db = api
    run_id = live_run(db)
    body = {} if name is None else {"designated_by": name}
    assert client.post(f"/api/runs/{run_id}/designate", json=body).status_code == 422
    assert (
        client.post(f"/api/runs/{run_id}/designate", json={"designated_by": "x", "note": "n" * 2001}).status_code == 422
    )
    assert db.designations("held_out") == []


def test_designation_strips_the_name_and_stores_the_note(api):
    client, db = api
    run_id = live_run(db)
    r = designate(client, run_id, name="  Dana (PM)  ", note="  Agreed in the launch review.  ")
    assert r.status_code == 200
    d = r.json()["designation"]
    assert d["run_id"] == run_id and d["designated_by"] == "Dana (PM)" and d["note"] == "Agreed in the launch review."
    assert d["split"] == "held_out" and d["designated_at"]


# ---- the designation is the decision run --------------------------------------------------
def test_designated_run_is_the_decision_run_even_when_a_newer_run_exists(api):
    client, db = api
    older = backdate(db, live_run(db))
    assert designate(client, older, note="Launch review 1").status_code == 200
    newer = live_run(db)
    assert latest_runs(db)[0]["run_id"] == older

    runs = {r["run_id"]: r for r in client.get("/api/runs").json()}
    assert runs[older]["latest"] and runs[older]["designated"]
    assert not runs[newer]["latest"] and not runs[newer]["designated"]
    assert all(r["designated"] is False for r in runs.values() if r["run_id"] != older)

    d = client.get("/api/decision").json()["decision"]
    assert d["run_id"] == older
    assert d["designation"]["designated_by"] == "Dana (PM)" and d["designation"]["note"] == "Launch review 1"
    # Looking at the newer run explicitly shows it is not the run of record.
    other = client.get("/api/decision", params={"run_id": newer}).json()["decision"]
    assert other["designation"] is None and other["designation_blocker"] is None


def test_without_a_designation_the_newest_usable_run_is_still_used(api):
    client, db = api
    backdate(db, live_run(db))
    newest = live_run(db)
    d = client.get("/api/decision").json()["decision"]
    assert d["run_id"] == newest and d["designation"] is None
    assert not any(r["designated"] for r in client.get("/api/runs").json())


def test_designation_history_is_kept_and_the_newest_one_is_current(api):
    client, db = api
    first, second = live_run(db), live_run(db)
    designate(client, second, name="Ana")
    designate(client, first, name="Ben")
    history = db.designations("held_out")
    assert [(h["run_id"], h["designated_by"]) for h in history] == [(first, "Ben"), (second, "Ana")]
    assert db.current_designation("held_out")["run_id"] == first
    assert latest_runs(db)[0]["run_id"] == first
    assert designate(client, second, name="Cy").json()["history"][0]["designated_by"] == "Cy"
    assert len(db.designations("held_out")) == 3


def test_fixture_decision_reports_why_it_cannot_be_designated(api):
    client, _ = api
    d = client.get("/api/decision").json()["decision"]
    assert d["run_mode"] == "fixture" and d["designation"] is None
    assert "Fixture runs" in d["designation_blocker"]


def test_existing_database_files_gain_the_designation_table(tmp_path):
    path = tmp_path / "old.sqlite3"
    Database(path)
    with sqlite3.connect(path) as c:  # a database created before designations existed
        c.execute("DROP TABLE run_designations")
    db = Database(path)
    assert db.current_designation("held_out") is None


# ---- review lock ----------------------------------------------------------------------------
def test_reviews_are_locked_only_on_held_out_responses_of_the_designated_run(api):
    client, db = api
    record = live_run(db, splits=("development", "held_out"))
    other = live_run(db, splits=("development", "held_out"))
    held_out, development = response_id(client, record, "held_out"), response_id(client, record, "development")

    assert review(client, held_out).status_code == 200  # open before the designation
    designate(client, record)
    locked = review(client, held_out)
    assert locked.status_code == 409 and locked.json()["detail"] == LOCKED
    assert len(db.get_response(held_out)["reviews"]) == 1  # nothing was stored
    assert review(client, development).status_code == 200  # development reviews stay open
    assert review(client, response_id(client, other, "held_out")).status_code == 200

    # Moving the designation unlocks the old run and locks the new one.
    designate(client, other)
    assert review(client, held_out).status_code == 200
    assert review(client, response_id(client, other, "held_out")).status_code == 409


# ---- held-out usage counter -------------------------------------------------------------------
def test_held_out_usage_counts_live_runs_per_dataset_version(db):
    version = load_dataset()["version"]
    run_evaluation(db, mode="fixture", export_dir=None)  # fixture runs never count
    live_run(db, splits=("development",))  # never looked at the held-out set
    full = live_run(db)
    held_out_case = next(c["case_id"] for c in load_dataset()["cases"] if c["split"] == "held_out")
    partial = live_run(db, case_ids=[held_out_case])  # partial runs still expose held-out answers
    broken = live_run(db, llm=ScriptedProvider(bad_key))  # so do error-dominated ones
    older_version = live_run(db)
    with db.connect() as c:
        c.execute("UPDATE runs SET dataset_version = 'v0-old' WHERE run_id = ?", (older_version,))

    usage = held_out_usage(db, version)
    assert usage["dataset_version"] == version and usage["evaluations"] == 3
    assert sorted(usage["run_ids"]) == sorted([full, partial, broken])
    assert usage["in_progress_run_ids"] == []
    assert held_out_usage(db, "v0-old")["run_ids"] == [older_version]
    assert build_decision(db, full)["held_out_usage"] == usage


def test_fixture_only_database_has_no_held_out_usage(db):
    fixture = run_evaluation(db, mode="fixture", export_dir=None)
    assert build_decision(db, fixture)["held_out_usage"]["evaluations"] == 0


def test_memo_names_the_run_of_record_and_warns_about_repeated_held_out_use(db):
    first = live_run(db)
    memo = decision_memo(db)
    assert "**Decision run of record:** none designated" in memo
    assert "evaluated the held-out set of dataset" in memo and "1 time(s)" in memo
    assert "Warning: repeated held-out evaluation" not in memo

    live_run(db)
    db.add_designation(first, "held_out", "Dana (PM)", "Agreed in the\nlaunch review")
    memo = decision_memo(db)
    assert f"live run `{first}`" in memo
    assert "designated by Dana (PM) on" in memo and "Note: Agreed in the launch review" in memo
    assert "Warning: repeated held-out evaluation" in memo
    assert "the held-out set has been evaluated 2 times; the verdict may reflect tuning against it" in memo.lower()


# ---- review of PR #5 --------------------------------------------------------------------------
def test_a_run_reviewed_while_released_cannot_be_designated_again(api):
    """Finding 55: designate A, move to B (unlocks A), change A's held-out labels, designate A again."""
    client, db = api
    a = live_run(db, splits=("development", "held_out"))
    b = live_run(db)
    assert designate(client, a, name="Ana").status_code == 200
    assert designate(client, b, name="Ben").status_code == 200
    # Development reviews are never locked, so they don't block a return to A.
    assert review(client, response_id(client, a, "development")).status_code == 200
    assert designate(client, a, name="Cy").status_code == 200
    assert designate(client, b, name="Ben").status_code == 200

    assert review(client, response_id(client, a, "held_out")).status_code == 200  # A is released
    refused = designate(client, a, name="Ana")
    assert refused.status_code == 409
    assert "review(s) of its held-out responses were made after it was first designated" in refused.json()["detail"]
    assert db.current_designation("held_out")["run_id"] == b
    # The whole history is visible on the decision, newest first.
    history = client.get("/api/decision").json()["decision"]["designation_history"]
    assert [(h["run_id"], h["designated_by"]) for h in history] == [(b, "Ben"), (a, "Cy"), (b, "Ben"), (a, "Ana")]


def test_reviews_made_before_the_first_designation_do_not_block_it(api):
    client, db = api
    a, b = live_run(db), live_run(db)
    rid = response_id(client, a, "held_out")
    assert review(client, rid).status_code == 200
    with db.connect() as c:  # the review was clearly made before the designation
        c.execute("UPDATE reviews SET created_at = '2026-01-01T00:00:00Z' WHERE response_id = ?", (rid,))
    assert designate(client, a).status_code == 200
    assert designate(client, b).status_code == 200
    assert designate(client, a).status_code == 200


def test_memo_lists_the_designation_history_when_the_run_of_record_moved(db):
    a, b = live_run(db), live_run(db)
    db.add_designation(a, "held_out", "Ana", None)
    assert "Designation history" not in decision_memo(db)
    db.add_designation(b, "held_out", "Ben", "moved after re-run")
    memo = decision_memo(db)
    assert "**Designation history** (newest first)" in memo
    assert f"`{b}` by Ben: moved after re-run" in memo and f"`{a}` by Ana" in memo


def test_held_out_usage_counts_a_run_left_running_with_held_out_answers(db):
    """Finding 56: a killed runner leaves status `running` forever while its answers are visible."""
    version = load_dataset()["version"]
    finished = live_run(db)
    killed = live_run(db)
    template = db.get_run(finished)
    db.create_run({**template, "run_id": "live-just-started", "status": "running"})
    with db.connect() as c:
        c.execute("UPDATE runs SET status = 'running' WHERE run_id = ?", (killed,))
    usage = held_out_usage(db, version)
    assert usage["evaluations"] == 2  # the run with no answers yet has exposed nothing
    assert sorted(usage["run_ids"]) == sorted([finished, killed])
    assert usage["in_progress_run_ids"] == [killed]
    d = build_decision(db, finished)
    assert d["held_out_usage"]["in_progress_run_ids"] == [killed]
    memo = decision_memo(db)
    assert "1 of them still in progress" in memo and f"{killed} (in progress)" in memo


def test_designated_by_and_note_are_collapsed_to_one_line(api):
    client, db = api
    run_id = live_run(db)
    r = designate(client, run_id, name="Dana\n# Launch approved", note="line one\n\n## line two\t end")
    assert r.status_code == 200
    d = r.json()["designation"]
    assert d["designated_by"] == "Dana # Launch approved" and d["note"] == "line one ## line two end"
    assert designate(client, run_id, name="\n\t ").status_code == 422
    # Even text stored some other way can't start a line of the memo.
    db.add_designation(run_id, "held_out", "Eve\n# Approved", "x\n> quoted")
    memo = decision_memo(db)
    assert not any(line.startswith(("# Approved", "> quoted")) for line in memo.splitlines())
    assert "designated by Eve # Approved on" in memo


def test_review_lock_is_checked_in_the_same_transaction_as_the_insert(db):
    run_id = live_run(db)
    rid = db.responses_for_run(run_id)[0]["response_id"]
    db.add_designation(run_id, "held_out", "Dana", None)
    with pytest.raises(WriteRefused, match="reviews are locked"):
        db.add_review(rid, "incorrect", None, "pm", lock_split="held_out")
    assert db.get_response(rid)["reviews"] == []
    db.add_review(rid, "incorrect", None, "pm")  # no lock requested: a development response, say


def test_a_run_whose_criteria_evaluate_another_split_cannot_be_designated(api):
    client, db = api
    run_id = live_run(db, splits=("development", "held_out"))
    with db.connect() as c:
        c.execute(
            "UPDATE runs SET config_snapshot = json_set(config_snapshot, '$.launch_criteria.evaluated_split', "
            "'development') WHERE run_id = ?",
            (run_id,),
        )
    r = designate(client, run_id)
    assert r.status_code == 409 and "criteria evaluate the development split" in r.json()["detail"]


def test_an_unusable_run_of_record_is_disclosed_not_silently_replaced(api, monkeypatch):
    client, db = api
    record = backdate(db, live_run(db))
    newest = live_run(db)
    designate(client, record)
    original = results.designation_blocker
    monkeypatch.setattr(
        results,
        "designation_blocker",
        lambda db, run, split="held_out": (
            "its stored results are unreadable." if run["run_id"] == record else original(db, run, split)
        ),
    )
    d = client.get("/api/decision").json()["decision"]
    assert d["run_id"] == newest and d["designation"] is None
    assert d["run_of_record_warning"] == (
        f"The decision run of record {record} is no longer usable: its stored results are unreadable. "
        "The newest usable live run is used instead."
    )
    assert "Warning: run of record not used." in decision_memo(db)
