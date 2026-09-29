"""SQLite persistence for runs, responses, reviews, ad-hoc questions and configuration snapshots."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    mode TEXT NOT NULL CHECK (mode IN ('live', 'fixture')),
    status TEXT NOT NULL,
    label TEXT,
    splits TEXT NOT NULL,
    judge_mode TEXT NOT NULL,
    corpus_version TEXT NOT NULL,
    dataset_version TEXT NOT NULL,
    prompt_versions TEXT NOT NULL,
    model_config TEXT NOT NULL,
    config_snapshot TEXT NOT NULL,
    summary TEXT
);
CREATE TABLE IF NOT EXISTS responses (
    response_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    case_id TEXT NOT NULL,
    approach TEXT NOT NULL,
    response TEXT NOT NULL,
    grade TEXT NOT NULL,
    judge TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (run_id, case_id, approach)
);
CREATE TABLE IF NOT EXISTS reviews (
    review_id TEXT PRIMARY KEY,
    response_id TEXT NOT NULL REFERENCES responses(response_id),
    verdict TEXT NOT NULL CHECK (verdict IN ('correct', 'partially_correct', 'incorrect')),
    note TEXT,
    reviewer TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ask_log (
    ask_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    question TEXT NOT NULL,
    role TEXT NOT NULL,
    mode TEXT NOT NULL,
    responses TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS configuration (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_responses_run ON responses(run_id);
CREATE INDEX IF NOT EXISTS idx_reviews_response ON reviews(response_id);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        with self.connect() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        with self._lock:
            # The in-process lock serialises this app's threads; busy_timeout and WAL let the CLI
            # runner and the API server share the same file without "database is locked" errors.
            conn = sqlite3.connect(self.path, timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

    # ---- runs -------------------------------------------------------------------------
    def create_run(self, run: dict) -> None:
        with self.connect() as c:
            c.execute(
                """INSERT INTO runs (run_id, created_at, mode, status, label, splits, judge_mode, corpus_version,
                   dataset_version, prompt_versions, model_config, config_snapshot)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    run["run_id"],
                    run["created_at"],
                    run["mode"],
                    run["status"],
                    run.get("label"),
                    json.dumps(run["splits"]),
                    run["judge_mode"],
                    run["corpus_version"],
                    run["dataset_version"],
                    json.dumps(run["prompt_versions"]),
                    json.dumps(run["model_config"]),
                    json.dumps(run["config_snapshot"], default=str),
                ),
            )

    def finish_run(self, run_id: str, status: str, summary: dict) -> None:
        with self.connect() as c:
            c.execute(
                "UPDATE runs SET status=?, completed_at=?, summary=? WHERE run_id=?",
                (status, now_iso(), json.dumps(summary), run_id),
            )

    def _run_row(self, r: sqlite3.Row) -> dict:
        d = dict(r)
        for k in ("splits", "prompt_versions", "model_config", "config_snapshot", "summary"):
            if d.get(k) is not None:
                d[k] = json.loads(d[k])
        # Stored in the snapshot (no schema change); runs saved before the flag existed count as full runs.
        d["partial"] = bool(((d.get("config_snapshot") or {}).get("run_scope") or {}).get("partial", False))
        return d

    def get_run(self, run_id: str) -> dict | None:
        with self.connect() as c:
            r = c.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return self._run_row(r) if r else None

    def list_runs(self) -> list[dict]:
        with self.connect() as c:
            rows = c.execute("SELECT * FROM runs ORDER BY created_at DESC, run_id DESC").fetchall()
            counts = dict(c.execute("SELECT run_id, COUNT(*) FROM responses GROUP BY run_id").fetchall())
        out = []
        for r in rows:
            d = self._run_row(r)
            d["n_responses"] = counts.get(d["run_id"], 0)
            d.pop("config_snapshot", None)
            out.append(d)
        return out

    # ---- responses --------------------------------------------------------------------
    def add_response(
        self, run_id: str, case_id: str, approach: str, response: dict, grade: dict, judge: dict | None
    ) -> str:
        rid = new_id("resp")
        with self.connect() as c:
            c.execute(
                "INSERT INTO responses VALUES (?,?,?,?,?,?,?,?)",
                (
                    rid,
                    run_id,
                    case_id,
                    approach,
                    json.dumps(response),
                    json.dumps(grade),
                    json.dumps(judge) if judge is not None else None,
                    now_iso(),
                ),
            )
        return rid

    def responses_for_run(self, run_id: str) -> list[dict]:
        return self._responses("r.run_id = ?", (run_id,))

    def get_response(self, response_id: str) -> dict | None:
        rows = self._responses("r.response_id = ?", (response_id,))
        return rows[0] if rows else None

    def _responses(self, where: str, params: tuple) -> list[dict]:
        """Responses matching `where`, each with its reviews (oldest first) and latest review."""
        with self.connect() as c:
            rows = c.execute(
                f"SELECT r.* FROM responses r WHERE {where} ORDER BY r.case_id, r.approach", params
            ).fetchall()
            reviews = c.execute(
                f"SELECT rv.* FROM reviews rv JOIN responses r ON r.response_id = rv.response_id "
                f"WHERE {where} ORDER BY rv.created_at, rv.rowid",
                params,
            ).fetchall()
        by_response: dict[str, list[dict]] = {}
        for rv in reviews:
            by_response.setdefault(rv["response_id"], []).append(dict(rv))
        out = []
        for r in rows:
            d = dict(r)
            d["response"] = json.loads(d["response"])
            d["grade"] = json.loads(d["grade"])
            d["judge"] = json.loads(d["judge"]) if d["judge"] else None
            d["reviews"] = by_response.get(d["response_id"], [])
            d["review"] = d["reviews"][-1] if d["reviews"] else None  # the latest review wins
            out.append(d)
        return out

    # ---- reviews ----------------------------------------------------------------------
    def add_review(self, response_id: str, verdict: str, note: str | None, reviewer: str | None) -> dict:
        rv = {
            "review_id": new_id("rev"),
            "response_id": response_id,
            "verdict": verdict,
            "note": note,
            "reviewer": reviewer,
            "created_at": now_iso(),
        }
        with self.connect() as c:
            c.execute("INSERT INTO reviews VALUES (:review_id,:response_id,:verdict,:note,:reviewer,:created_at)", rv)
        return rv

    # ---- ask log & configuration ------------------------------------------------------
    def log_ask(self, question: str, role: str, mode: str, responses: list[dict]) -> str:
        aid = new_id("ask")
        with self.connect() as c:
            c.execute(
                "INSERT INTO ask_log VALUES (?,?,?,?,?,?)",
                (aid, now_iso(), question, role, mode, json.dumps(responses)),
            )
        return aid

    def set_config(self, key: str, value: dict) -> None:
        with self.connect() as c:
            c.execute(
                "INSERT INTO configuration VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (key, json.dumps(value), now_iso()),
            )

    def get_config(self, key: str) -> dict | None:
        with self.connect() as c:
            r = c.execute("SELECT value FROM configuration WHERE key=?", (key,)).fetchone()
        return json.loads(r["value"]) if r else None
