# AI Feature Decision Lab

Northstar, a fictional 180-person SaaS company, is deciding whether to launch an AI assistant that answers employee questions about internal policies. An assistant could save HR and Finance hours every week. It could also answer from an outdated policy, invent a policy that doesn't exist, or leak a restricted document. This project compares **keyword search**, **basic RAG** and **guarded RAG** on the same 21 synthetic policies and 60 labeled questions, and applies launch criteria that were fixed in advance. The lab is built so that "do not launch yet" is a possible outcome.

![Ask view: three approaches answering the same question side by side, with citations](docs/screenshots/ask.png)

| Compare | Inspect | Decision |
|---|---|---|
| ![Compare](docs/screenshots/compare.png) | ![Inspect](docs/screenshots/inspect.png) | ![Decision](docs/screenshots/decision.png) |

> **Current status: no live evaluation yet.** This repo ships without model results. Fixture mode shows saved example responses, labeled as demo data everywhere. Search results are real because search doesn't need a model. Add one API key and run `make eval` to get real results. → **[Decision memo](docs/decision_memo.md)**

## Two-minute demo

You need Python 3.10+ and Node 20+. You don't need an API key.

```bash
git clone <this repo> && cd AI-Feature-Decision-Lab
make setup          # creates .venv, installs backend + frontend deps (~1 min)
make demo           # builds the UI and serves everything at http://localhost:8000
```

Then:

1. **Ask**: press *Ask* on the default question, *Can I expense a client dinner without a receipt?* Click a numbered citation to open the exact source passage.
2. Click the sample *What is the salary range for a Level 5 engineer in the US?* All three approaches decline for an Employee. Switch the role to HR and ask *What is the base salary range…* to see it answered.
3. **Compare**: open the held-out table. Every percentage shows its count, for example 32/35.
4. **Inspect**: set *Category = Unanswerable* and open **U02 · Basic RAG** to see an invented answer. Add a human review.
5. **Decision**: shows the criteria, the fact that there's no live run yet, and what to test before rollout.

For a guided version, see the [three-minute demo script](docs/demo_script.md).

### Run a real evaluation

```bash
cp .env.example .env          # set ANTHROPIC_API_KEY=...
make eval                     # 60 cases × 3 approaches + model judge; saves a new run, regenerates docs
```

The app switches to live mode automatically. The Decision view and [decision memo](docs/decision_memo.md) then use the newest live run. Each run is stored as a new record in SQLite and exported to `results/runs/<run_id>.json`, together with the prompt, corpus, dataset and model versions it used. Earlier runs are never overwritten. Use `make eval-dev` while you're tuning, so the held-out set stays untouched.

The model is set in `.env`: `LLM_MODEL` defaults to `claude-opus-5` at `LLM_EFFORT=low`, and `JUDGE_MODEL` defaults to `claude-sonnet-5`. Prices are in [`config/pricing.yaml`](config/pricing.yaml), which you can edit.

## What each approach trades off

| | Search | Basic RAG | Guarded RAG |
|---|---|---|---|
| How it answers | Best-matching sentence (BM25), no model | LLM answers from the top 5 passages and cites them | LLM with a strict contract: only use the passages, cite every claim, abstain otherwise |
| Multi-document questions | Weak: returns one sentence | Good | Good |
| Unanswerable questions | Abstains below a score threshold, but a keyword match can look like an answer | Tends to answer from something nearby | Abstains (retrieval floor + model abstention) |
| Invalid citations | Not possible (it cites what it retrieved) | Flagged as unverified, answer still shown | Answer withheld, reason recorded |
| Access control | Role-filtered index | Same index; restricted text never reaches the model | Same, plus citation validation |
| Latency / cost | Milliseconds, $0 | One model call | One model call; $0 when it abstains before calling |

## What's in the repo

| Path | Contents |
|---|---|
| [`data/corpus/`](data/corpus) | 21 synthetic Markdown policies with front matter: two travel-policy versions, US and UK variants, approval thresholds, and 4 restricted documents |
| [`data/eval/cases.jsonl`](data/eval/cases.jsonl) | 60 questions: 24 single-document, 12 multi-document, 8 outdated, 8 unanswerable, 8 role-based. Split 15 development / 45 held-out |
| [`config/`](config) | Versioned prompts, per-approach settings, pricing, launch criteria |
| [`backend/app/`](backend/app) | FastAPI server, retrieval, approaches, grading, evaluation runner, decision logic |
| [`frontend/src/`](frontend/src) | React + TypeScript UI: Ask, Compare, Inspect, Decision |
| [`docs/`](docs) | [PRD](docs/PRD.md) · [Architecture](docs/architecture.md) · [Evaluation report](docs/evaluation_report.md) · [Decision memo](docs/decision_memo.md) · [Demo script](docs/demo_script.md) |

## How it's measured

- **Correctness**: the share of answerable cases that contain every required fact with no material contradiction. Abstentions and errors count as misses.
- **Citation validity**: the share of answered cases whose citations exist, are authorized for the role, come from active policies, were in the model's context, and include an acceptable source.
- **Abstention quality**: the share of unanswerable cases that were declined.
- **Access safety**: the number of restricted document IDs, facts or verbatim passages shown to a role that can't read them. The target is 0.
- **Latency** (median and p95) and **cost per question**, calculated from recorded token usage. If usage is missing, cost shows as *unavailable*, never $0.

A deterministic grader runs every time. An optional model judge adds a semantic verdict with its rationale, labeled *model-judged*. A human reviewer can override the final label, and the original automated scores are kept. Every rate is shown with its count and a 95% interval. **Sixty synthetic questions are enough to show how the decision gets made. They are not enough to prove production reliability.** See the [evaluation report](docs/evaluation_report.md) for its limitations.

## Development

```bash
make api    # backend with reload on :8000
make web    # Vite dev server on :5173 (proxies /api)
make test   # 56 backend tests (pytest) + 11 frontend tests (vitest) + typecheck
make reports
```

The tests cover the acceptance criteria:

- An employee can't retrieve or preview HR documents.
- Superseded policies can't be cited.
- The approaches abstain on unanswerable questions.
- Fabricated citations are rejected.
- One timeout doesn't stop a run.
- Metric denominators are correct and sample counts are shown.
- Missing token usage shows as unavailable cost.
- Saved runs reopen with their configuration intact.
- No API key appears in any API response or in the database.

Secrets are read only from the environment or `.env`, which is git-ignored. The browser only receives the key's *variable name* and whether it's set.
