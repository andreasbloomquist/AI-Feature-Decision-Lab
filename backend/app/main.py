"""HTTP API for the lab. The Ask, Compare, Inspect and Decision views read from here.

Endpoints are thin: authorization lives in `access`, answering in `approaches`, scoring in
`grading`/`metrics`, run storage in `db`/`results`, and the launch decision in `decision`.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .access import ROLE_GROUPS, ROLE_LABELS, can_access, check_role
from .approaches import APPROACH_NAMES, Approach, ApproachContext, build_approaches
from .approaches.base import APPROACH_LABELS
from .corpus import get_corpus
from .dataset import load_dataset
from .db import Database
from .decision import build_decision, criteria_config
from .evaluation import config_snapshot, ensure_fixture_run, export_run
from .llm import LLMProvider, make_provider
from .results import latest_runs, load_rows, summarize_rows
from .retrieval import Retriever
from .schemas import ApproachResponse
from .settings import RESULTS_DIR, ROOT, Settings, load_settings, public_settings

FRONTEND_DIST = ROOT / "frontend" / "dist"
# One question per category (plus an authorized-role variant) that has saved fixture responses.
SAMPLE_CASE_IDS = ("M01", "S02", "M02", "O01", "U02", "R01", "O02", "R02")


# ---------------------------------------------------------------------------------------
# Dependencies (process-wide singletons; tests clear the caches to isolate state)
# ---------------------------------------------------------------------------------------
@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


@lru_cache(maxsize=1)
def get_db() -> Database:
    return Database(get_settings().db_path)


@lru_cache(maxsize=1)
def get_approaches() -> dict[str, Approach]:
    corpus = get_corpus()
    llm: LLMProvider = make_provider(get_settings())
    return build_approaches(ApproachContext(corpus=corpus, retriever=Retriever(corpus), llm=llm))


def get_role(role: Annotated[str, Query(description="Role the request is made as")]) -> str:
    try:
        return check_role(role)
    except ValueError as e:
        raise HTTPException(400, detail={"status": "error", "error": f"unknown role {role!r}"}) from e


SettingsDep = Annotated[Settings, Depends(get_settings)]
DbDep = Annotated[Database, Depends(get_db)]
RoleDep = Annotated[str, Depends(get_role)]


def reset_caches() -> None:
    """Drop cached singletons so the next request re-reads settings (used by tests)."""
    for cached in (get_settings, get_db, get_approaches):
        cached.cache_clear()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db = get_db()
    ensure_fixture_run(db, get_settings())
    db.set_config("active_settings", public_settings(get_settings()))
    yield


app = FastAPI(title="AI Feature Decision Lab", version="1.0.0", lifespan=lifespan)


# ---------------------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------------------
@app.get("/api/health")
def health(settings: SettingsDep) -> dict:
    return {"ok": True, **public_settings(settings)}


@app.get("/api/config")
def config(settings: SettingsDep) -> dict:
    ds = load_dataset()
    criteria, criteria_hash = criteria_config()
    snapshot = config_snapshot(settings)
    return {
        "settings": public_settings(settings),
        "roles": [{"id": r, "label": ROLE_LABELS[r], "groups": sorted(ROLE_GROUPS[r])} for r in ROLE_GROUPS],
        "approaches": [{"id": a, "label": APPROACH_LABELS[a], **snapshot["approaches"][a]} for a in APPROACH_NAMES],
        "pricing": snapshot["pricing"],
        "launch_criteria": {**criteria, "hash": criteria_hash},
        "corpus_version": get_corpus().version,
        "dataset_version": ds["version"],
        "dataset_meta": ds["meta"],
    }


@app.get("/api/sample-questions")
def sample_questions() -> list[dict]:
    """Questions that have saved fixture responses, for trying the app without a key."""
    cases = load_dataset()["by_id"]
    return [
        {
            "case_id": cid,
            "question": cases[cid]["question"],
            "role": cases[cid]["user_role"],
            "category": cases[cid]["category"],
        }
        for cid in SAMPLE_CASE_IDS
    ]


# ---------------------------------------------------------------------------------------
# Documents: the same role check as retrieval applies to previews
# ---------------------------------------------------------------------------------------
@app.get("/api/documents")
def list_documents(role: RoleDep) -> list[dict]:
    docs = [d.metadata() for d in get_corpus().documents.values() if can_access(role, d)]
    return sorted(docs, key=lambda d: (d["status"] != "active", d["title"]))


@app.get("/api/documents/{document_id}")
def get_document(document_id: str, role: RoleDep) -> dict:
    doc = get_corpus().get(document_id)
    if doc is None or not can_access(role, doc):
        # One response for "missing" and "restricted", so a user cannot probe for restricted IDs.
        raise HTTPException(
            404,
            detail={"status": "access_denied", "error": "This document does not exist or your role cannot view it."},
        )
    return {
        **doc.metadata(),
        "passages": [{"passage_id": p.passage_id, "heading": p.heading, "text": p.text} for p in doc.passages],
    }


# ---------------------------------------------------------------------------------------
# Ask
# ---------------------------------------------------------------------------------------
class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    role: str
    approaches: list[Literal["search", "basic_rag", "guarded_rag"]] = Field(
        default_factory=lambda: list(APPROACH_NAMES)
    )


@app.post("/api/ask")
def ask(req: AskRequest, settings: SettingsDep, db: DbDep) -> dict:
    role = get_role(req.role)
    approaches = get_approaches()
    question = req.question.strip()
    responses = []
    for name in dict.fromkeys(req.approaches):
        try:
            resp = approaches[name].run(question, role)
        except Exception as e:  # surface as an error card, never a 500
            resp = ApproachResponse.failed(name, f"internal_error: {type(e).__name__}")
        responses.append(resp.public_dict())
    db.log_ask(question, role, settings.mode, responses)
    return {"mode": settings.mode, "fixture": not settings.live_available, "role": role, "responses": responses}


# ---------------------------------------------------------------------------------------
# Runs, cases, reviews (evaluator views)
# ---------------------------------------------------------------------------------------
def _run_or_404(db: Database, run_id: str) -> dict:
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(404, detail="run not found")
    return run


@app.get("/api/runs")
def list_runs(db: DbDep) -> list[dict]:
    return db.list_runs()


@app.get("/api/runs/{run_id}")
def get_run(run_id: str, db: DbDep) -> dict:
    run = _run_or_404(db, run_id)
    run["metrics"] = summarize_rows(load_rows(db, run_id))  # recomputed so human reviews count
    run["metrics_at_completion"] = run.pop("summary")
    return run


@app.get("/api/runs/{run_id}/cases")
def list_cases(
    run_id: str,
    db: DbDep,
    category: str | None = None,
    approach: str | None = None,
    outcome: str | None = None,
    error_type: str | None = None,
    split: str | None = None,
) -> list[dict]:
    _run_or_404(db, run_id)
    wanted = {"category": category, "approach": approach, "outcome": outcome, "error_type": error_type, "split": split}
    out = []
    for r in load_rows(db, run_id):
        c, g = r["case"], r["grade"]
        row = {
            "response_id": r["response_id"],
            "case_id": r["case_id"],
            "approach": r["approach"],
            "question": c["question"],
            "role": c["user_role"],
            "category": c["category"],
            "split": c["split"],
            "answerability": c["answerability"],
            "status": r["response"]["status"],
            "outcome": g["outcome"],
            "error_type": g["error_type"],
            "final_label": r["final_label"],
            "final_label_source": r["final_label_source"],
            "deterministic_label": g["deterministic_label"],
            "judge_verdict": (r["judge"] or {}).get("verdict"),
            "reviewed": bool(r["reviews"]),
            "succeeded": r["succeeded"],
            "disclosures": len(g["disclosures"]),
            "latency_ms": r["response"].get("latency_ms"),
            "fixture": r["response"].get("fixture", False),
        }
        if all(value is None or row[key] == value for key, value in wanted.items()):
            out.append(row)
    return out


@app.get("/api/runs/{run_id}/cases/{case_id}")
def case_detail(run_id: str, case_id: str, db: DbDep) -> dict:
    _run_or_404(db, run_id)
    rows = [r for r in load_rows(db, run_id) if r["case_id"] == case_id]
    if not rows:
        raise HTTPException(404, detail="case not in run")
    corpus = get_corpus()
    for r in rows:
        r["retrieved_documents"] = [
            {"document_id": d, "title": doc.title if doc else None, "status": doc.status if doc else None}
            for d in r["response"]["retrieved_document_ids"]
            for doc in [corpus.get(d)]
        ]
    return {"case": rows[0]["case"], "responses": rows}


class ReviewRequest(BaseModel):
    verdict: Literal["correct", "partially_correct", "incorrect"]
    note: str | None = Field(default=None, max_length=2000)
    reviewer: str | None = Field(default=None, max_length=100)


@app.post("/api/responses/{response_id}/reviews")
def add_review(response_id: str, req: ReviewRequest, db: DbDep) -> dict:
    row = db.get_response(response_id)
    if not row:
        raise HTTPException(404, detail="response not found")
    review = db.add_review(response_id, req.verdict, req.note, req.reviewer)
    # The automated grade and judge verdict are never modified; the review is stored alongside.
    updated = db.get_response(response_id)
    if db.get_run(row["run_id"])["mode"] == "live":
        export_run(db, row["run_id"], RESULTS_DIR / "runs")  # keep the committed export in sync
    return {
        "review": review,
        "automated_grade": updated["grade"],
        "judge": updated["judge"],
        "reviews": updated["reviews"],
    }


# ---------------------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------------------
@app.get("/api/decision")
def decision(db: DbDep, run_id: str | None = None) -> dict:
    live, fixture = latest_runs(db)
    if run_id:
        _run_or_404(db, run_id)
        return {"live_available": live is not None, "decision": build_decision(db, run_id)}
    if live:
        return {"live_available": True, "decision": build_decision(db, live["run_id"])}
    return {
        "live_available": False,
        "message": "No live evaluation yet",
        "decision": build_decision(db, fixture["run_id"]) if fixture else None,
    }


# ---------------------------------------------------------------------------------------
# Static frontend (production build)
# ---------------------------------------------------------------------------------------
def static_file(root: Path, requested: str) -> Path | None:
    """Return the file under `root` that `requested` names, or None.

    The path is resolved first, so encoded traversal such as `..%2F..%2F.env` cannot escape `root`.
    """
    base = root.resolve()
    target = (base / requested).resolve()
    if target.is_relative_to(base) and target.is_file():
        return target
    return None


if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(404)
        return FileResponse(static_file(FRONTEND_DIST, path) or FRONTEND_DIST / "index.html")
