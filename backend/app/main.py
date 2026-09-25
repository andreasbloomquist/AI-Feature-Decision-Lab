"""FastAPI server: the Ask, Compare, Inspect and Decision views read from here."""
from __future__ import annotations

from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .access import ROLE_GROUPS, ROLE_LABELS, can_access, check_role
from .approaches import APPROACH_NAMES, ApproachContext, build_approaches
from .approaches.base import APPROACH_LABELS
from .corpus import get_corpus
from .dataset import load_dataset
from .db import Database
from .decision import build_decision, criteria_config
from .evaluation import config_snapshot, export_run, run_evaluation, summarize_run
from .grading import final_label
from .llm import FixtureProvider, make_provider
from .retrieval import Retriever
from .settings import ROOT, Settings, load_settings, public_settings

FRONTEND_DIST = ROOT / "frontend" / "dist"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


@lru_cache(maxsize=1)
def get_db() -> Database:
    return Database(get_settings().db_path)


@lru_cache(maxsize=1)
def get_retriever() -> Retriever:
    return Retriever(get_corpus())


def ensure_fixture_run(db: Database) -> None:
    """Seed one fixture run so the UI has something to show without a key. Idempotent."""
    if any(r["mode"] == "fixture" for r in db.list_runs()):
        return
    run_evaluation(db, mode="fixture", llm=FixtureProvider(), settings=get_settings(),
                   label="Fixture demonstration (saved example responses)", export_dir=None)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db = get_db()
    ensure_fixture_run(db)
    db.set_config("active_settings", public_settings(get_settings()))
    yield


app = FastAPI(title="AI Feature Decision Lab", version="1.0.0", lifespan=lifespan)


# ---------------------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------------------
@app.get("/api/health")
def health(settings: Settings = Depends(get_settings)):
    return {"ok": True, **public_settings(settings)}


@app.get("/api/config")
def config(settings: Settings = Depends(get_settings)):
    corpus = get_corpus()
    ds = load_dataset()
    cfg, cfg_hash = criteria_config()
    snap = config_snapshot(settings)
    return {
        "settings": public_settings(settings),
        "roles": [{"id": r, "label": ROLE_LABELS[r], "groups": sorted(ROLE_GROUPS[r])} for r in ROLE_GROUPS],
        "approaches": [{"id": a, "label": APPROACH_LABELS[a], **snap["approaches"][a]} for a in APPROACH_NAMES],
        "pricing": snap["pricing"],
        "launch_criteria": {**cfg, "hash": cfg_hash},
        "corpus_version": corpus.version,
        "dataset_version": ds["version"],
        "dataset_meta": ds["meta"],
    }


@app.get("/api/sample-questions")
def sample_questions():
    """Questions with saved fixture responses, for trying the app without a key."""
    fx = FixtureProvider()
    wanted = ["M01", "S02", "M02", "O01", "U02", "R01", "O02", "R02"]
    ds = load_dataset()["by_id"]
    out = []
    for cid in wanted:
        c = ds[cid]
        out.append({"case_id": cid, "question": c["question"], "role": c["user_role"], "category": c["category"],
                    "has_fixture": any(k.endswith(" ".join(c["question"].lower().split())) for k in fx.outputs)})
    return out


# ---------------------------------------------------------------------------------------
# Documents (authorization applies to previews too)
# ---------------------------------------------------------------------------------------
def _role(role: str) -> str:
    try:
        return check_role(role)
    except ValueError:
        raise HTTPException(400, detail={"status": "error", "error": f"unknown role {role!r}"})


@app.get("/api/documents")
def list_documents(role: str = Query(...)):
    role = _role(role)
    docs = [d.metadata() for d in get_corpus().documents.values() if can_access(role, d)]
    return sorted(docs, key=lambda d: (d["status"] != "active", d["title"]))


@app.get("/api/documents/{document_id}")
def get_document(document_id: str, role: str = Query(...)):
    role = _role(role)
    doc = get_corpus().get(document_id)
    # Same response for "missing" and "restricted" would hide existence; we return 403 with no
    # metadata so the UI can explain access, and never include title or text.
    if doc is None:
        raise HTTPException(404, detail={"status": "error", "error": "document not found"})
    if not can_access(role, doc):
        raise HTTPException(403, detail={"status": "access_denied", "error": "Your role cannot view this document."})
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
    approaches: list[Literal["search", "basic_rag", "guarded_rag"]] = list(APPROACH_NAMES)


@app.post("/api/ask")
def ask(req: AskRequest, settings: Settings = Depends(get_settings), db: Database = Depends(get_db)):
    role = _role(req.role)
    llm = make_provider(settings)
    ctx = ApproachContext(corpus=get_corpus(), retriever=get_retriever(), llm=llm)
    impls = build_approaches(ctx)
    results = []
    for name in dict.fromkeys(req.approaches):
        try:
            resp = impls[name].run(req.question.strip(), role)
            results.append(resp.public_dict())
        except Exception as e:  # noqa: BLE001 - surface as an error card, never a 500
            results.append({"approach": name, "status": "error", "answer": "", "citations": [],
                            "retrieved_document_ids": [], "latency_ms": None, "input_tokens": None,
                            "output_tokens": None, "estimated_cost_usd": None,
                            "error": f"internal_error: {type(e).__name__}"})
    db.log_ask(req.question, role, settings.mode, results)
    return {"mode": settings.mode, "fixture": llm.is_fixture, "role": role, "responses": results}


# ---------------------------------------------------------------------------------------
# Runs, cases, reviews
# ---------------------------------------------------------------------------------------
def _run_or_404(db: Database, run_id: str) -> dict:
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(404, detail="run not found")
    return run


@app.get("/api/runs")
def list_runs(db: Database = Depends(get_db)):
    return db.list_runs()


@app.get("/api/runs/{run_id}")
def get_run(run_id: str, db: Database = Depends(get_db)):
    run = _run_or_404(db, run_id)
    run["metrics"] = summarize_run(db, run_id)  # recomputed so human reviews are reflected
    run["metrics_at_completion"] = run.pop("summary")
    return run


def _case_rows(db: Database, run_id: str) -> list[dict]:
    ds = load_dataset()["by_id"]
    rows = db.responses_for_run(run_id)
    for r in rows:
        c = ds[r["case_id"]]
        r["case"] = c
        lab, src = final_label(r["grade"], r["judge"], r["review"])
        r["final_label"], r["final_label_source"] = lab, src
    return rows


@app.get("/api/runs/{run_id}/cases")
def list_cases(
    run_id: str,
    db: Database = Depends(get_db),
    category: str | None = None,
    approach: str | None = None,
    outcome: str | None = None,
    error_type: str | None = None,
    split: str | None = None,
):
    _run_or_404(db, run_id)
    out = []
    for r in _case_rows(db, run_id):
        c, g = r["case"], r["grade"]
        if category and c["category"] != category:
            continue
        if approach and r["approach"] != approach:
            continue
        if split and c["split"] != split:
            continue
        if outcome and g["outcome"] != outcome:
            continue
        if error_type and g["error_type"] != error_type:
            continue
        out.append({
            "response_id": r["response_id"], "case_id": r["case_id"], "approach": r["approach"],
            "question": c["question"], "role": c["user_role"], "category": c["category"], "split": c["split"],
            "answerability": c["answerability"], "status": r["response"]["status"], "outcome": g["outcome"],
            "error_type": g["error_type"], "final_label": r["final_label"], "final_label_source": r["final_label_source"],
            "deterministic_label": g["deterministic_label"], "judge_verdict": (r["judge"] or {}).get("verdict"),
            "reviewed": bool(r["reviews"]), "disclosures": len(g["disclosures"]),
            "latency_ms": r["response"].get("latency_ms"), "fixture": r["response"].get("fixture", False),
        })
    return out


@app.get("/api/runs/{run_id}/cases/{case_id}")
def case_detail(run_id: str, case_id: str, db: Database = Depends(get_db)):
    _run_or_404(db, run_id)
    rows = [r for r in _case_rows(db, run_id) if r["case_id"] == case_id]
    if not rows:
        raise HTTPException(404, detail="case not in run")
    corpus = get_corpus()
    for r in rows:
        r["retrieved_documents"] = [
            {"document_id": d, "title": corpus.get(d).title if corpus.get(d) else None,
             "status": corpus.get(d).status if corpus.get(d) else None}
            for d in r["response"]["retrieved_document_ids"]
        ]
    return {"case": rows[0]["case"], "responses": rows}


class ReviewRequest(BaseModel):
    verdict: Literal["correct", "partially_correct", "incorrect"]
    note: str | None = Field(default=None, max_length=2000)
    reviewer: str | None = Field(default=None, max_length=100)


@app.post("/api/responses/{response_id}/reviews")
def add_review(response_id: str, req: ReviewRequest, db: Database = Depends(get_db)):
    row = db.get_response(response_id)
    if not row:
        raise HTTPException(404, detail="response not found")
    review = db.add_review(response_id, req.verdict, req.note, req.reviewer)
    # The automated grade and judge verdict are left untouched; the review is stored alongside.
    updated = db.get_response(response_id)
    run = db.get_run(row["run_id"])
    if run and run["mode"] == "live":
        export_run(db, row["run_id"], ROOT / "results" / "runs")
    return {"review": review, "automated_grade": updated["grade"], "judge": updated["judge"],
            "reviews": updated["reviews"]}


# ---------------------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------------------
@app.get("/api/decision")
def decision(run_id: str | None = None, db: Database = Depends(get_db)):
    runs = db.list_runs()
    live = [r for r in runs if r["mode"] == "live" and r["status"].startswith("completed")]
    fixture = [r for r in runs if r["mode"] == "fixture"]
    if run_id:
        _run_or_404(db, run_id)
        return {"live_available": bool(live), "decision": build_decision(db, run_id)}
    if live:
        return {"live_available": True, "decision": build_decision(db, live[0]["run_id"])}
    return {
        "live_available": False,
        "message": "No live evaluation yet",
        "decision": build_decision(db, fixture[0]["run_id"]) if fixture else None,
    }


# ---------------------------------------------------------------------------------------
# Static frontend (production build)
# ---------------------------------------------------------------------------------------
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        target = FRONTEND_DIST / path
        if path and target.is_file():
            return FileResponse(target)
        return FileResponse(FRONTEND_DIST / "index.html")
