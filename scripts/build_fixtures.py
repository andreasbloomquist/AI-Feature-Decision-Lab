"""Build data/fixtures/llm_outputs.json: saved example outputs for fixture mode.

These outputs are NOT model responses. They are written by this script so a reviewer can explore
the interface without an API key. Most are derived from the reference answers, with passage
citations chosen from the real retrieval results; a small, listed set of cases deliberately shows
common failure modes (invented answers, a fabricated citation, a missing citation, a timeout,
over-abstention, citing a passage outside the context). The whole file is labeled as fixture data
and the app never reports its latency or cost.

Run: python scripts/build_fixtures.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.corpus import get_corpus  # noqa: E402
from app.dataset import load_dataset  # noqa: E402
from app.llm import fixture_key  # noqa: E402
from app.prompts import load_approach_config  # noqa: E402
from app.retrieval import Retriever, tokenize  # noqa: E402

# Illustrative failure modes, chosen by hand and listed here so nothing is hidden.
BASIC_INVENTS = {  # unanswerable questions where basic RAG answers anyway from a nearby passage
    "U02": "Fully remote employees receive a stipend of $50 per month for this, paid through payroll.",
    "U04": "Yes. Employees can take extended time off after five years; request it in the People portal with at least 2 weeks' notice.",
    "U06": "Relocation costs follow the Travel Policy: flights are booked in TripDesk and hotels are capped at $325 per night in New York.",
    "U07": "US employees have flexible paid time off, so jury duty can be taken as paid time off.",
}
BASIC_FABRICATED_CITATION = {"S09": "NS-DAT-002#1"}
BASIC_NO_CITATION = {"S13"}
BASIC_CONTRADICTION = {
    "O02": "A $1,800 trip needs approval from your manager and your department head (VP), because it is over $1,500.",
}
BASIC_TIMEOUT = {"S21"}
GUARDED_TIMEOUT = {"S19"}
GUARDED_OVER_ABSTAIN = {"M04"}
GUARDED_OUT_OF_CONTEXT = {"M10"}

SENT_RE = re.compile(r"(?<=[.!?])\s+")


def best_passage(sentence: str, candidates: list) -> str:
    toks = set(tokenize(sentence))
    return max(candidates, key=lambda p: (len(toks & set(tokenize(p.text))), -p.index)).passage_id


def main() -> None:
    corpus = get_corpus()
    retriever = Retriever(corpus)
    k = load_approach_config("guarded_rag")["retrieval"]["top_k"]
    outputs: dict[str, dict] = {}
    for case in load_dataset()["cases"]:
        q, role, cid = case["question"], case["user_role"], case["case_id"]
        hits = retriever.retrieve(q, role, k=k)
        acceptable = [h.passage for h in hits if h.passage.document_id in case["acceptable_document_ids"]]
        sentences = SENT_RE.split(case["reference_answer"])

        # ---- guarded RAG -------------------------------------------------------------
        gk = fixture_key("guarded_rag", q, role)
        if cid in GUARDED_TIMEOUT:
            outputs[gk] = {"error": "timeout", "message": "model request timed out (simulated in fixture)"}
        elif case["answerability"] != "answerable" or not acceptable or cid in GUARDED_OVER_ABSTAIN:
            outputs[gk] = {
                "text": "STATUS: ABSTAINED\nANSWER: The available policies do not clearly answer this question."
            }
        elif cid in GUARDED_OUT_OF_CONTEXT:
            ctx = {h.passage.passage_id for h in hits}
            outside = next(p for p in corpus.passages if p not in ctx and p.startswith("NS-SEC-001"))
            body = " ".join(f"{s} [{best_passage(s, acceptable)}]" for s in sentences)
            outputs[gk] = {"text": f"STATUS: ANSWERED\nANSWER: {body} Report problems to Security [{outside}]."}
        else:
            body = " ".join(f"{s.rstrip('.')} [{best_passage(s, acceptable)}]." for s in sentences)
            outputs[gk] = {"text": f"STATUS: ANSWERED\nANSWER: {body}"}

        # ---- basic RAG ---------------------------------------------------------------
        bk = fixture_key("basic_rag", q, role)
        top = hits[0].passage.passage_id if hits else None
        if cid in BASIC_TIMEOUT:
            outputs[bk] = {"error": "timeout", "message": "model request timed out (simulated in fixture)"}
        elif cid in BASIC_INVENTS and top:
            outputs[bk] = {"text": f"{BASIC_INVENTS[cid]} [{top}]"}
        elif cid in BASIC_CONTRADICTION:
            outputs[bk] = {"text": f"{BASIC_CONTRADICTION[cid]} [{acceptable[0].passage_id}]"}
        elif case["answerability"] != "answerable" or not acceptable:
            outputs[bk] = {"text": "The passages provided don't contain information that answers this question."}
        elif cid in BASIC_FABRICATED_CITATION:
            outputs[bk] = {"text": f"{case['reference_answer']} [{BASIC_FABRICATED_CITATION[cid]}]"}
        elif cid in BASIC_NO_CITATION:
            outputs[bk] = {"text": case["reference_answer"]}
        else:
            cites = "".join(f"[{p}]" for p in dict.fromkeys(best_passage(s, acceptable) for s in sentences))
            outputs[bk] = {"text": f"According to Northstar policy: {case['reference_answer']} {cites}"}

    data = {
        "notice": "Illustrative example outputs for fixture mode. Written by scripts/build_fixtures.py, "
        "not generated by a language model. Never report their latency, cost or quality as measurements.",
        "model_label": "fixture (not a model)",
        "illustrated_failures": {
            "basic_rag_invents_answer": sorted(BASIC_INVENTS),
            "basic_rag_fabricated_citation": sorted(BASIC_FABRICATED_CITATION),
            "basic_rag_missing_citation": sorted(BASIC_NO_CITATION),
            "basic_rag_contradiction": sorted(BASIC_CONTRADICTION),
            "basic_rag_timeout": sorted(BASIC_TIMEOUT),
            "guarded_rag_timeout": sorted(GUARDED_TIMEOUT),
            "guarded_rag_over_abstains": sorted(GUARDED_OVER_ABSTAIN),
            "guarded_rag_cites_outside_context": sorted(GUARDED_OUT_OF_CONTEXT),
        },
        "outputs": outputs,
    }
    path = ROOT / "data" / "fixtures" / "llm_outputs.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {len(outputs)} fixture outputs to {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
