"""Generate docs/evaluation_report.md and docs/decision_memo.md from saved runs.

If a live run exists, both documents are generated from the latest one. Otherwise the report says
"No live evaluation yet" and the memo is a labeled template plus an example based only on fixture data.
"""

from __future__ import annotations

import argparse
import re
from collections import Counter

from .approaches.base import APPROACH_LABELS, APPROACH_NAMES
from .corpus import get_corpus
from .dataset import load_dataset
from .db import Database
from .decision import build_decision, criteria_config, limitations
from .evaluation import ensure_fixture_run
from .prompts import load_approach_config
from .results import latest_runs, load_rows, summarize_rows
from .retrieval import DEFAULT_B, DEFAULT_K1, Retriever
from .settings import ROOT, load_settings

DOCS = ROOT / "docs"
CATEGORY_LABELS = {
    "single_document": "Single document",
    "multi_document": "Multiple documents",
    "outdated_policy": "Outdated / changed policy",
    "unanswerable": "Unanswerable",
    "role_access": "Role-based access",
}


def pct(v: float | None) -> str:
    return "—" if v is None else f"{v * 100:.1f}%"


def rate(r: dict | None) -> str:
    if not r or r["denominator"] == 0:
        return "n = 0"
    return f"{pct(r['value'])} ({r['numerator']}/{r['denominator']}; 95% CI {pct(r['ci_low'])}–{pct(r['ci_high'])})"


def ms(v: float | None) -> str:
    if v is None:
        return "—"
    if v < 1:
        return "<1 ms"
    return f"{v / 1000:.2f} s" if v >= 1000 else f"{v:.0f} ms"


def usd(v: float | None) -> str:
    return "unavailable" if v is None else ("$0" if v == 0 else f"${v:.4f}")


def fmt_value(unit: str, v: float | None) -> str:
    """Format a criterion value or threshold by its unit."""
    return {"rate": pct, "ms": ms, "usd": usd}.get(unit, lambda x: "—" if x is None else str(x))(v)


def table_header(*columns: str) -> str:
    return "| " + " | ".join(columns) + " |\n|" + "---|" * len(columns) + "\n"


def metrics_table(metrics: dict) -> str:
    cols = [a for a in APPROACH_NAMES if a in metrics]
    head = table_header("Measure", *(APPROACH_LABELS[a] for a in cols))

    def row(label, fn):
        return f"| {label} | " + " | ".join(fn(metrics[a]) for a in cols) + " |\n"

    def lat(m):
        if not m["latency"]["n"]:
            return "not measured" + (" (fixture)" if m["fixture_rows"] else "")
        return f"{ms(m['latency']['p50_ms'])} / {ms(m['latency']['p95_ms'])} (n={m['latency']['n']})"

    def cost(m):
        c = m["cost"]
        if c["per_question_usd"] is None:
            return f"unavailable ({c['n_missing']} of {m['n_cases']} without token usage)"
        missing = f", {c['n_missing']} without usage" if c["n_missing"] else ""
        return (
            f"{usd(c['per_question_usd'])} per question; {usd(c['total_usd'])} total (n={c['n_with_usage']}{missing})"
        )

    return head + "".join(
        [
            row("Answer correctness (answerable)", lambda m: rate(m["correctness"])),
            row("Deterministic fact match", lambda m: rate(m["correctness_deterministic"])),
            row("Citation validity (answered)", lambda m: rate(m["citation_validity"])),
            row("Abstention quality (unanswerable)", lambda m: rate(m["abstention_quality"])),
            row("Access-denied handling", lambda m: rate(m["access_denied_handling"])),
            row(
                "Restricted disclosures",
                lambda m: f"{m['access_safety']['disclosures']} in {m['access_safety']['n_cases']} cases",
            ),
            row("Latency p50 / p95", lat),
            row("Model cost", cost),
            row("Errors", lambda m: f"{m['errors']['count']} of {m['errors']['n']}"),
        ]
    )


def category_table(rows: list[dict], split: str) -> str:
    out = table_header("Category", "n", *(APPROACH_LABELS[a] for a in APPROACH_NAMES))
    for c in CATEGORY_LABELS:
        sub = [r for r in rows if r["case"]["category"] == c and r["case"]["split"] == split]
        n = len({r["case_id"] for r in sub})
        cells = []
        for a in APPROACH_NAMES:
            ar = [r for r in sub if r["approach"] == a]
            good = sum(1 for r in ar if r["succeeded"])
            cells.append(f"{good}/{len(ar)}")
        out += f"| {CATEGORY_LABELS[c]} | {n} | " + " | ".join(cells) + " |\n"
    return out


def threshold_table() -> str:
    """Best BM25 score per development case, and what each threshold does with it."""
    retriever = Retriever(get_corpus())
    cfg = load_approach_config("search")
    g = load_approach_config("guarded_rag")
    k1, b = cfg["retrieval"].get("k1", DEFAULT_K1), cfg["retrieval"].get("b", DEFAULT_B)
    lines = table_header("Case", "Answerability", "Best BM25 score", "Search", "Guarded floor")
    for c in load_dataset()["cases"]:
        if c["split"] != "development":
            continue
        hits = retriever.retrieve(c["question"], c["user_role"], k=1, k1=k1, b=b)
        top = hits[0].score if hits else 0.0
        lines += (
            f"| {c['case_id']} | {c['answerability']} | {top:.2f} | "
            f"{'answer' if top >= cfg['min_score'] else 'abstain'} | {'call model' if top >= g['retrieval_floor'] else 'abstain'} |\n"
        )
    return lines


def evaluation_report(db: Database) -> str:
    live, fixture = latest_runs(db)
    run = live or fixture
    split = criteria_config()[0].get("evaluated_split", "held_out")
    s = []
    s.append("# Evaluation report\n")
    s.append(
        "> **Generated file.** Run `make reports` to regenerate from the saved runs in SQLite. Do not edit by hand.\n"
    )
    if live:
        s.append(
            f"**Status: live evaluation.** Run `{live['run_id']}` created {live['created_at']} with "
            f"`{live['model_config']['model']}` (judge: `{live['model_config'].get('judge_model') or 'none'}`).\n"
        )
    else:
        s.append(
            "**Status: No live evaluation yet.** Every number below comes from the fixture run. Search results are "
            "real, because search needs no model. Basic and Guarded RAG results are computed on saved example "
            "responses written to exercise the interface; they are not model measurements and must not be quoted "
            "as results. Run `make eval` with an API key to produce a live report.\n"
        )
    s.append("## Read this first: dataset size and limits\n")
    s.append("".join(f"- {line}\n" for line in limitations(split)))
    s.append(
        "- Cost is estimated from recorded tokens and the editable price table in `config/pricing.yaml`; "
        "missing usage is reported as unavailable, never as zero.\n"
    )
    s.append("## Run configuration\n")
    s.append(
        f"| Field | Value |\n|---|---|\n| Run | `{run['run_id']}` ({run['mode']}) |\n"
        f"| Created | {run['created_at']} |\n| Corpus | `{run['corpus_version']}` |\n"
        f"| Dataset | `{run['dataset_version']}` |\n"
        f"| Prompts | "
        + ", ".join(
            f"{k}: `{v.get('prompt_version') or v.get('approach_version')}`" for k, v in run["prompt_versions"].items()
        )
        + " |\n"
        f"| Model | `{run['model_config']['model']}` (effort: {run['model_config'].get('effort')}) |\n"
        f"| Judge | {run['judge_mode']} |\n"
    )
    rows = load_rows(db, run["run_id"])
    summary = summarize_rows(rows)
    for split, title in (
        ("held_out", "Held-out results (used for the decision)"),
        ("development", "Development results"),
    ):
        if split in summary:
            s.append(f"## {title}\n")
            s.append(metrics_table(summary[split]))
            s.append(
                "\n**By category** (correct answers for answerable cases; correct abstention or safe decline otherwise):\n"
            )
            s.append(category_table(rows, split))
    held = [r for r in rows if r["case"]["split"] == "held_out" and not r["succeeded"]]
    if held:
        s.append("## Held-out failures\n")
        s.append("| Case | Approach | Category | Outcome | Detail |\n|---|---|---|---|---|\n")
        for r in sorted(held, key=lambda r: (r["approach"], r["case_id"])):
            detail = (
                r["response"].get("error") or r["response"].get("guard_reason") or (r["response"]["answer"] or "")[:90]
            )
            detail = detail.replace("|", "/").replace("\n", " ")
            s.append(
                f"| {r['case_id']} | {APPROACH_LABELS[r['approach']]} | {CATEGORY_LABELS[r['case']['category']]} | "
                f"{r['grade']['outcome']} | {detail} |\n"
            )
    s.append("\n## Scoring rubric\n")
    s.append(
        "- **Deterministic grader** (always runs): response status; required facts present, matched by aliases on "
        "normalized text with word boundaries; citations exist, are authorized for the role, are active, were in the "
        "model's context, and include an acceptable source; restricted document IDs, restricted facts (from "
        "`data/eval/restricted_markers.yaml` and each case's `forbidden_facts`) and 8-word verbatim spans from "
        "restricted passages in any answer shown to an unauthorized role.\n"
        "- **Model judge** (optional, live runs): grades answered, answerable cases as correct, partially correct or "
        "incorrect against the reference answer and required facts, checks citation support, and stores a rationale. "
        "Its verdicts are labeled model-judged.\n"
        "- **Human review**: a reviewer can mark any answer correct, partially correct or incorrect with a note. The "
        "automated grade and judge verdict are kept. Final label priority: human > model judge > deterministic.\n"
        "- **Denominators**: correctness over all answerable cases (abstentions and errors count as not correct); "
        "citation validity over answered cases; abstention quality over unanswerable cases; disclosures counted over "
        "all cases.\n"
        "- **Latency**: nearest-rank median and 95th percentile of wall-clock time per question.\n"
    )
    s.append("\n## Search threshold and retrieval floor (development split only)\n")
    s.append(
        f"Search abstains when the best BM25 score is below **{load_approach_config('search')['min_score']}**; guarded RAG "
        f"skips the model when it is below **{load_approach_config('guarded_rag')['retrieval_floor']}**. Both values were "
        "chosen by looking at the development split only:\n\n"
    )
    s.append(threshold_table())
    s.append("\nThe held-out set was not used to choose either value.\n")
    return "".join(s)


def _criteria_table(decision: dict, approach: str) -> str:
    state_col = "State (demo only)" if decision["run_mode"] == "fixture" else "State"
    out = table_header("Criterion", "Threshold", "Measured", state_col)
    for c in decision["approaches"][approach]["criteria"]:
        unit = c["unit"]
        measured = "not measured" if c["value"] is None else fmt_value(unit, c["value"])
        if unit == "rate" and c.get("numerator") is not None:
            measured += f" ({c['numerator']}/{c['n']})"
        elif c["n"] is not None and c["value"] is not None:
            measured += f" (n={c['n']})"
        state = {"pass": "Pass", "fail": "**Fail**", "insufficient": "Insufficient evidence"}[c["state"]]
        if c.get("confidence") == "low":
            state += " (interval crosses threshold)"
        if c["reason"]:
            state += f" — {c['reason']}"
        if c["state"] == "fail" and c["example_case_ids"]:
            state += "; e.g. " + ", ".join(c["example_case_ids"][:5])
        out += f"| {c['label']} | {c['comparator']} {fmt_value(unit, c['threshold'])} | {measured} | {state} |\n"
    return out


def _failure_modes(db: Database, run_id: str, approach: str, split: str) -> str:
    rows = [r for r in load_rows(db, run_id) if r["approach"] == approach and r["case"]["split"] == split]
    counts = Counter(r["grade"]["outcome"] for r in rows if not r["succeeded"])
    if not counts:
        return f"No {split.replace('_', '-')} failures for {APPROACH_LABELS[approach]}.\n"
    names = {
        "incorrect": "Incorrect answer",
        "partial": "Partially correct answer",
        "unnecessary_abstention": "Abstained when the policy did answer",
        "invented_answer": "Answered an unanswerable question",
        "error": "Error (timeout, validation or provider)",
        "disclosure": "Disclosed restricted content",
        "answered_without_access": "Answered a restricted question",
    }
    out = ""
    for outcome, n in counts.most_common():
        ex = [r["case_id"] for r in rows if r["grade"]["outcome"] == outcome][:4]
        out += f"- **{names.get(outcome, outcome)}**: {n} case(s), e.g. {', '.join(ex)}\n"
    return out


def decision_memo(db: Database) -> str:
    live, fixture = latest_runs(db)
    s = [
        "# Decision memo: AI policy assistant\n\n",
        "> **Generated file.** Run `make reports` to regenerate. Criteria: `config/launch_criteria.yaml`.\n\n",
    ]
    if live:
        d = build_decision(db, live["run_id"])
        s.append(
            f"**To:** Operations lead · **Re:** limited rollout of guarded RAG · **Evidence:** live run "
            f"`{live['run_id']}` ({live['created_at']}, `{live['model_config']['model']}`), held-out set of {d['n_cases']} cases\n\n"
        )
        s += _memo_body(db, d, live["run_id"], example=False)
        return "".join(s)
    s.append(
        "## Status: no live evaluation yet\n\n"
        "There are no measured model results, so this memo makes **no launch recommendation**. Below is (1) the "
        "template the live memo follows and (2) an example filled in from fixture data only.\n\n"
    )
    s.append(
        "## 1. Template\n\n"
        "- **Proposed action:** one of *proceed to a limited pilot*, *do not launch yet*, *do not launch*, or "
        "*insufficient evidence*, as computed from the launch criteria stored with the run.\n"
        "- **Evidence:** held-out criteria table with counts and intervals; lift over search; latency and cost.\n"
        "- **Major failure modes:** held-out failures for guarded RAG grouped by type, with case IDs.\n"
        "- **Limits of the experiment:** dataset size, synthetic questions, judge reliability, single-machine latency.\n"
        "- **Next test:** the experiment that addresses the first failing criterion, run on development data, "
        "then confirmed on a fresh held-out set.\n\n"
    )
    if fixture:
        d = build_decision(db, fixture["run_id"])
        s.append(
            "## 2. Example based only on fixture data\n\n"
            "> **Demonstration only.** Guarded and basic RAG responses here are saved examples written to exercise "
            "the interface, not model outputs. Nothing in this section is evidence about any model.\n\n"
        )
        s += _memo_body(db, d, fixture["run_id"], example=True)
    return "".join(s)


def _memo_body(db: Database, d: dict, run_id: str, example: bool) -> list[str]:
    s = []
    rec = d["recommendation"]
    s.append(f"### Proposed action: {rec['headline']}\n\n{rec['summary']}\n\n")
    if not example and d["comparison"]:
        c = d["comparison"]
        lift = c["correctness_lift_pp"]
        s.append(
            f"Against the search baseline, guarded RAG answered {c['target_correct']} answerable held-out questions "
            f"correctly versus {c['baseline_correct']} for search"
            + (f" ({'+' if lift > 0 else ''}{lift} points)" if lift is not None else "")
            + f", at a p95 latency of {ms(c['target_p95_ms'])} versus {ms(c['baseline_p95_ms'])} and a model cost of "
            f"{usd(c['target_cost_per_question'])} per question versus {usd(c['baseline_cost_per_question'])}.\n\n"
        )
    s.append("### Evidence (held-out set)\n\n")
    s.append(_criteria_table(d, d["target_approach"]))
    s.append("\nAll approaches on the same criteria:\n\n")
    s.append(table_header("Criterion", *(v["label"] for v in d["approaches"].values())))
    for i, c in enumerate(d["approaches"][d["target_approach"]]["criteria"]):
        cells = []
        for v in d["approaches"].values():
            cc = v["criteria"][i]
            cells.append({"pass": "Pass", "fail": "Fail", "insufficient": "Insufficient"}[cc["state"]])
        s.append(f"| {c['label']} | " + " | ".join(cells) + " |\n")
    target_label = APPROACH_LABELS[d["target_approach"]]
    s.append(f"\n### Major failure modes ({target_label}, {d['evaluated_split'].replace('_', '-')})\n\n")
    s.append(_failure_modes(db, run_id, d["target_approach"], d["evaluated_split"]))
    s.append("\n### Limits of this experiment\n\n" + "".join(f"- {t}\n" for t in d["limitations"]))
    if d["next_experiments"]:
        s.append("\n### Next test\n\n" + "".join(f"- {e['text']}\n" for e in d["next_experiments"]))
    s.append(
        "\n### What we would test before a real rollout\n\n"
        + "".join(f"{i}. {t}\n" for i, t in enumerate(d["rollout_tests"], 1))
    )
    return s


def tidy(md: str) -> str:
    """Insert the blank lines Markdown needs around headings, tables, quotes and paragraphs."""

    def kind(line: str) -> str:
        if not line.strip():
            return "blank"
        for prefix, k in (("#", "heading"), ("|", "table"), (">", "quote"), ("- ", "list"), ("  ", "list")):
            if line.startswith(prefix):
                return k
        return "list" if re.match(r"^\d+\. ", line) else "text"

    out: list[str] = []
    for line in md.splitlines():
        k = kind(line)
        if out and k != "blank":
            pk = kind(out[-1])
            if pk != "blank" and (k == "heading" or pk == "heading" or k != pk or k == "text"):
                out.append("")
        out.append(line)
    return "\n".join(out).strip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Regenerate docs/evaluation_report.md and docs/decision_memo.md")
    parser.parse_args(argv)
    settings = load_settings()
    db = Database(settings.db_path)
    ensure_fixture_run(db, settings)
    DOCS.mkdir(exist_ok=True)
    (DOCS / "evaluation_report.md").write_text(tidy(evaluation_report(db)))
    (DOCS / "decision_memo.md").write_text(tidy(decision_memo(db)))
    print("wrote docs/evaluation_report.md and docs/decision_memo.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
