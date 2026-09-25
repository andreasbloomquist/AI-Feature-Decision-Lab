"""Optional model judge for semantic correctness. Verdicts are stored with their rationale and
always labeled as model-judged."""
from __future__ import annotations

import re

from .corpus import Corpus
from .llm import LLMError, LLMProvider
from .pricing import estimate_cost_usd
from .prompts import load_prompt
from .schemas import ApproachResponse

JUDGE_RE = re.compile(
    r"VERDICT:\s*(correct|partially_correct|incorrect)\s*\n+\s*CITATIONS_SUPPORT:\s*(yes|no|n/a)\s*\n+\s*RATIONALE:\s*(.*)",
    re.IGNORECASE | re.DOTALL,
)


def judge_response(llm: LLMProvider, case: dict, resp: ApproachResponse, corpus: Corpus) -> dict:
    prompt = load_prompt("prompts/judge.v1.md")
    cited = []
    for c in resp.citations:
        p = corpus.passage(c.passage_id) if c.passage_id and c.valid else None
        if p:
            cited.append(f"[{p.passage_id}] {p.text}")
    system, user = prompt.render(
        question=case["question"],
        reference_answer=case["reference_answer"],
        required_facts="\n".join(f"- {f['description']}" for f in case["required_facts"]) or "- (none)",
        answer=resp.answer,
        cited_passages="\n\n".join(cited) or "(no valid citations)",
    )
    base = {"judge_version": prompt.version, "model": llm.model, "label": "model-judged"}
    try:
        result = llm.generate(system, user, max_tokens=1500)
    except LLMError as e:
        return {**base, "verdict": None, "error": f"{e.kind}: {e.message}"}
    m = JUDGE_RE.search(result.text or "")
    usage = {
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "estimated_cost_usd": estimate_cost_usd(result.model, result.input_tokens, result.output_tokens),
    }
    if not m:
        return {**base, **usage, "verdict": None, "error": "unparseable judge output", "raw": result.text}
    support = m.group(2).lower()
    return {
        **base,
        **usage,
        "verdict": m.group(1).lower(),
        "citations_support": None if support == "n/a" else support == "yes",
        "rationale": m.group(3).strip(),
        "error": None,
    }
