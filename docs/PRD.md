# PRD: Northstar policy assistant (decision experiment)

**Status:** experiment · **Owner:** Product (internal tools) · **Decision maker:** Operations lead · **Last updated:** 2026-09-25

## Problem

Northstar has 180 employees in the US and UK and about 20 short policy documents. Employees ask the same questions again and again ("How much can I spend on a home office?", "Who approves travel over $2,000?") and either search the policy library, which returns whole documents, or message HR and Finance, which costs those teams time. Some policies have been superseded, US and UK rules differ in small ways, and a few documents are restricted to HR, Finance or administrators.

A generative assistant could answer these questions directly. It could also answer confidently from an outdated policy, invent a policy that does not exist, or leak restricted content. Before building one, the operations lead needs evidence on both sides.

## Target users

- **Primary user:** an employee who needs a trustworthy answer quickly and can open the cited policy to check it.
- **Buyer and decision maker:** the operations lead who decides whether the assistant is more useful than search and safe enough for a limited rollout.
- **Secondary:** policy owners in HR and Finance, who field the questions today and own the content.

## Product question

Does guarded RAG improve successful policy resolution enough to justify its extra latency and cost, while meeting minimum standards for citations, abstention and access control?

"Do not launch yet" is an acceptable answer.

## What we compare

| Approach | What it does | Why it is in the comparison |
|---|---|---|
| Search | Role-filtered BM25 over active policies; returns the best-matching sentence with a citation; abstains below a score threshold. | The cheap, fast, predictable baseline. An assistant must beat this to be worth building. |
| Basic RAG | Same retrieval; the top passages go to an LLM with a plain "answer and cite" instruction. | What a team would build first. Shows the risk of an unguarded model. |
| Guarded RAG | Same retrieval; strict answer contract; post-generation citation validation; abstains when evidence is weak; no second "fix-up" call. | The candidate for launch. |

All three receive the same question and role and return the same response object.

## Requirements

These are the fixed requirements the build had to meet. The [technical decisions](decisions.md) refer back to them.

| # | Requirement |
|---|---|
| R1 | Stack: React + TypeScript + Vite frontend, Python + FastAPI backend, SQLite storage, Markdown policies with structured metadata, BM25 (or equivalent) keyword retrieval, one real LLM provider through its official SDK, with provider and model set by environment variables. |
| R2 | Compare search, basic RAG and guarded RAG on the same documents and questions, with one common response object: `answer, status, citations, retrieved_document_ids, latency_ms, input_tokens, output_tokens, estimated_cost_usd, error`. |
| R3 | Enforce document access **before retrieval**, and apply it to search results, model context, citations and source previews. |
| R4 | Guarded RAG validates citations after generation and never makes a second, unrestricted call to "fix" an answer. Invalid citations are never shown as trusted sources. |
| R5 | Run without an API key in a clearly labelled fixture mode whose results are never presented as measurements. Show "No live evaluation yet" instead of invented scores. |
| R6 | Evaluate on a fixed 60-question set (15 development, 45 held-out). Do not tune against the held-out set. Show sample counts beside every percentage. |
| R7 | Never infer zero cost from missing token usage. Never compare fixture latency or cost with live measurements. |
| R8 | A failed case must not stop a run. Every run is a new record that stores its prompt, corpus, dataset and model versions and a timestamp. |
| R9 | Apply launch criteria fixed in advance, and allow the answer to be "do not launch yet". |
| R10 | No API keys in source control, logs, saved runs, screenshots or browser responses. |

## Success measure

The launch decision uses criteria written before any live evaluation was run, applied to the 45-case held-out set (`config/launch_criteria.yaml`). Each run stores a copy of the criteria and its hash, so editing the file afterwards cannot change an existing verdict:

| Criterion | Threshold | Why |
|---|---|---|
| Unauthorized disclosure | 0 | One leak of salary bands or audit thresholds ends the project. Non-negotiable. |
| Correct answers on answerable questions | ≥ 80% | Below this, employees stop trusting it and go back to asking HR. |
| Valid citations among answered questions | ≥ 95% | The product promise is "you can check the source". |
| Correct abstention on unanswerable questions | ≥ 90% | An invented policy is worse than no answer. |
| p95 latency | ≤ 6 s | Roughly the patience budget for an internal tool. |
| Average model cost per question | ≤ $0.02 | At an estimated 2,000 questions a month, about $40 a month; trivial next to HR time. |

The headline measure for "more useful than search" is the correctness lift over search on the same held-out cases, reported with counts.

Latency and cost are judged on the cases that were actually measured, provided at least 90% of cases were. A timeout with no token usage lowers that coverage instead of counting as free, and one transient error cannot block the verdict on its own.

## Scope

In scope: the three approaches, a synthetic corpus and fixed evaluation set, an evaluation runner with saved runs, automated grading plus optional model judge, human review, and a decision view that applies the criteria.

Excluded:

- Real authentication or SSO. The user picks a role; access control is enforced in the backend as if the role were authenticated.
- Multi-turn conversation and follow-up questions.
- Document ingestion from real systems (Confluence, Google Drive, an HRIS), or automatic freshness sync.
- Embedding or hybrid retrieval. BM25 keeps the comparison simple and local; hybrid retrieval is the first candidate next experiment if correctness fails because of retrieval.
- Answering in languages other than English, and non-US/UK jurisdictions.
- Taking actions (filing an expense, requesting leave).

## Key product trade-offs

1. **Abstain versus answer.** Guarded RAG will sometimes decline a question it could have answered. We accept a lower answer rate in exchange for fewer invented policies, and we measure both (correctness counts over-abstention as a miss).
2. **Not confirming restricted content.** When an employee asks about salary bands, the assistant says it cannot find this in the policies available to them. It does not say "that is in an HR-only document", because that confirms the document exists and hints at its content. The cost is a less helpful message; the benefit is no metadata leak.
3. **Access control before retrieval, not after.** Each role gets its own index built only from documents it may read. Restricted text never enters scoring, snippets or model context. Filtering after generation would be simpler but would rely on the model not repeating what it saw.
4. **Withhold instead of repair.** If guarded RAG cites a passage it was not given, the answer is withheld and the reason recorded. We do not make a second, less constrained call to "fix" it, because that hides the failure and doubles cost.
5. **Superseded policies are never current.** They are excluded from retrieval. Change questions are answered from the "changes from the previous version" section of the active policy. Superseded documents can still be opened in the source viewer, clearly labeled.
6. **Measured cost only.** Missing token usage is shown as "unavailable", never as zero, and fixture results never show latency or cost.
7. **Deterministic grading first.** A rules-based grader checks facts, citations and disclosures on every run. The model judge adds semantic grading but is labeled as model-judged, and human review overrides both while keeping the originals.

## Risks and open questions

- The evaluation set is small and synthetic. It supports a go/no-go on a *pilot*, not a general launch.
- Employees may not open citations. The usability test in "What we would test before a real rollout" checks this.
- Policy owners must own the answers. Without a process for reviewing abstained questions and wrong answers, quality will drift.
