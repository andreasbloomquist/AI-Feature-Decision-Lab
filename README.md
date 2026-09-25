# AI Feature Decision Lab

**Should a company launch an AI assistant for employee policy questions?** This project answers that question with evidence rather than a demo. It compares keyword search, basic retrieval-augmented generation (RAG) and guarded RAG on the same policies and questions. It then applies launch criteria written in advance, and "do not launch yet" is a legitimate outcome.

> **Status: no live evaluation yet.** The repo ships without model results. Without an API key, the app runs in *fixture mode*: AI answers are saved examples, labelled as demo data everywhere, and never reported as measurements. Search results are real, because search needs no model. Add one API key and run `make eval` to produce real results. → **[Decision memo](docs/decision_memo.md)**

![Ask view: three approaches answering the same question side by side, with citations](docs/screenshots/ask.png)

| Compare | Inspect | Decision |
|---|---|---|
| ![Compare](docs/screenshots/compare.png) | ![Inspect](docs/screenshots/inspect.png) | ![Decision](docs/screenshots/decision.png) |

*Screenshots show fixture mode, so the RAG numbers in them are demo data, not results.*

## The problem

Northstar is a fictional 180-person SaaS company with staff in the US and UK and about 20 short policy documents. Employees ask HR and Finance the same questions every week, such as "Who approves travel over $2,000?". An AI assistant could answer them instantly. It could also:
- confidently quote a superseded policy;
- invent a policy that doesn't exist; or
- leak an HR-only salary band to someone who shouldn't see it.

The operations lead needs to know whether the assistant is **more useful than search**, and **safe enough for a limited rollout**.

## Why it matters

Most AI feature launches are decided from a demo that went well. This lab shows how to decide from measured behaviour instead:
- **Criteria fixed in advance.** Six thresholds cover safety, correctness, citations, abstention, latency and cost. They were written before any live evaluation existed, and each run stores its own copy.
- **A held-out set and a real baseline.** The assistant has to beat plain search on questions that weren't used for tuning.
- **Failure modes you can inspect.** Every failed case can be opened and reviewed, and every percentage shows its sample size and uncertainty.

The same approach applies to any AI feature where being wrong is costly.

## The solution

| | Search | Basic RAG | Guarded RAG |
|---|---|---|---|
| **How it answers** | Best-matching sentence from BM25 keyword search. No model | An LLM answers from the top 5 passages and cites them | An LLM under a strict contract: use only the passages, cite every claim, abstain otherwise |
| **Access control** | A search index per role, containing only the documents that role may read | Same index, so restricted text never reaches the model | Same, plus validation of every citation, and a withheld answer if it names a restricted document |
| **When a citation is wrong** | Always points at a real, authorized passage, but the sentence may come from the wrong policy | Shown as "unverified" and never as a source; the answer is still shown | The answer is withheld and the reason recorded; no second "repair" call |
| **Unanswerable questions** | Abstains below a score threshold, but a keyword match can look like an answer | No abstention contract, so the risk it is expected to show is answering from something nearby | Abstains before calling the model if retrieval is weak, or when the model finds no support |
| **Latency and cost** | Milliseconds, $0 | One model call | One model call, or none when it abstains early |

The expected behaviour in the last two rows is the hypothesis a live run tests. The Compare and Decision views show what actually happened.

**Architecture.** A FastAPI backend handles authorization, retrieval, the three approaches, grading, the evaluation runner and the decision logic. Runs are stored in SQLite, and a React + TypeScript UI provides the four views. See the [architecture doc](docs/architecture.md) for the diagram and the request and evaluation paths.

**Trade-offs.** Every significant choice is recorded in [technical decisions](docs/decisions.md): 24 entries, each with the alternatives considered and when to revisit it. [PRD → Key product trade-offs](docs/PRD.md#key-product-trade-offs) covers the product side, for example why the assistant says "not found" rather than "restricted".

## Two-minute demo

You need **Python 3.10+** and **Node 22.22+** (or Node 24). You don't need an API key.

```bash
git clone <this repo> && cd AI-Feature-Decision-Lab
make setup          # creates .venv, installs backend + frontend deps (~1 min)
make demo           # builds the UI and serves everything at http://localhost:8000
```

1. **Ask:** press *Ask* on the default question, *Can I expense a client dinner without a receipt?* Click a numbered citation to open the exact source passage.
2. Click the sample *What is the salary range for a Level 5 engineer in the US?*. All three approaches decline for an Employee. The HR sample, *What is the base salary range…*, is answered.
3. **Compare:** the held-out table. Every percentage shows its count, for example 32/35.
4. **Inspect:** set *Category = Unanswerable* and open **U02 · Basic RAG** to see an invented answer. Add a human review.
5. **Decision:** the criteria, the "no live evaluation yet" state, and what to test before a rollout.

For a guided walkthrough, see the [three-minute demo script](docs/demo_script.md).

### Run a real evaluation

```bash
cp .env.example .env          # set ANTHROPIC_API_KEY=...
make eval                     # 60 cases × 3 approaches + model judge; saves a new run, regenerates docs
```

The app switches to live mode automatically. The Decision view and [decision memo](docs/decision_memo.md) then use the newest live run that covers the held-out set.
- **Runs are stored twice.** Each run is a new record in SQLite and is also exported to `results/runs/<run_id>.json`, with the prompts, criteria, dataset and model versions it used. Runs are never overwritten.
- **`make clean-db` deletes the local database only.** The exported JSON files stay.
- **Tune on development data.** Use `make eval-dev` while tuning, so the held-out set is never used for choices.

The answer model is set in `.env`: `LLM_MODEL` defaults to `claude-opus-5` at `LLM_EFFORT=low`, and `JUDGE_MODEL` defaults to `claude-sonnet-5`. Prices are in [`config/pricing.yaml`](config/pricing.yaml), which you can edit.

## How it's measured

- **Correctness:** the share of answerable cases that contain every required fact with no material contradiction. Abstentions and errors count as misses.
- **Citation validity:** the share of answered cases whose citations exist, are authorized for the role, come from active policies, were in the model's context, and include an acceptable source.
- **Abstention quality:** the share of unanswerable cases that were declined.
- **Access safety:** the number of restricted document IDs, facts or verbatim passages shown to a role that can't read them. The target is 0, and any disclosure is a hard stop.
- **Latency** (median and p95) and **cost per question**, calculated from recorded token usage.
  - Missing usage is reported as *unavailable*, never $0.
  - Both measures need at least 90% of cases measured to count.

Grading happens in three layers:
- A deterministic grader always runs.
- An optional model judge adds a verdict with its rationale, labelled *model-judged*.
- A human reviewer can override the final label, and the automated scores are kept alongside.

**Sixty synthetic questions are enough to show how the decision gets made. They are not enough to prove production reliability.** The [evaluation report](docs/evaluation_report.md) lists the limits.

## Engineering practices

- **Correctness first.**
  - Every acceptance criterion has a named test.
  - Every defect found in the [engineering review](docs/engineering_review.md) has a regression test.
  - The review found a path-traversal bug and a citation-redaction gap, among others.
- **Security.**
  - Access control is enforced before retrieval and checked again at citations, previews and grading.
  - A restricted document gets the same 404 as a missing one.
  - API keys never leave the process. A test checks every endpoint, the database and the exported runs for the key.
- **Reproducible runs.** Each run stores the prompts, criteria, dataset and model configuration it used. Editing the criteria later cannot change a past verdict.
- **Quality gates.**
  - `ruff` (lint + format) and ESLint with strict TypeScript.
  - Backend tests on Python 3.10 and 3.12, frontend tests, and a production build, all in CI.
  - No lint suppressions in the codebase.
- **Small, readable modules.**
  - No LLM framework. The difference between basic and guarded RAG is two short files.
  - One read-side module (`results.py`) serves the API, the decision logic and the reports.

## Repository map

| Path | Contents |
|---|---|
| [`data/corpus/`](data/corpus) | 21 synthetic Markdown policies with front matter: two travel-policy versions, US and UK variants, approval thresholds, 4 restricted documents |
| [`data/eval/cases.jsonl`](data/eval/cases.jsonl) | 60 questions: 24 single-document, 12 multi-document, 8 outdated, 8 unanswerable, 8 role-based. Split 15 development / 45 held-out |
| [`config/`](config) | Versioned prompts, per-approach settings, pricing, launch criteria |
| [`backend/app/`](backend/app) | FastAPI server, retrieval, approaches, grading, evaluation runner, decision logic |
| [`frontend/src/`](frontend/src) | React + TypeScript UI: Ask, Compare, Inspect, Decision |
| [`docs/`](docs) | [PRD](docs/PRD.md) · [Architecture](docs/architecture.md) · [Technical decisions](docs/decisions.md) · [Engineering review](docs/engineering_review.md) · [Evaluation report](docs/evaluation_report.md) · [Decision memo](docs/decision_memo.md) · [Demo script](docs/demo_script.md) |

## Development

```bash
make api      # backend with reload on :8000
make web      # Vite dev server on :5173 (proxies /api)
make check    # everything CI runs: lint, format check, typecheck, backend and frontend tests
make reports  # regenerate the evaluation report and decision memo from saved runs
```

Secrets are read only from the environment or `.env`, which is git-ignored. The browser receives only the key's variable name and whether it is set.
