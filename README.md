# AI Feature Decision Lab

**Should we ship this AI feature?** This lab helps a product manager answer that question with evidence rather than a good demo. It builds the feature three ways, runs all three on the same questions, and checks the results against launch criteria written *before* anyone saw them. "Do not launch yet" is a legitimate outcome.

The worked example is an AI assistant that answers employee questions about company policy. It compares:
- **keyword search**, the cheap baseline;
- **basic retrieval-augmented generation (RAG)**, what most teams build first; and
- **guarded RAG**, the launch candidate.

> **Status: no live evaluation yet.** The repo ships without model results. Without an API key the app runs in *fixture mode*: AI answers are saved examples, labelled as demo data everywhere, and never reported as measurements. Search results are real, because search needs no model. Add one API key and run `make eval` to produce real results. → **[Decision memo](docs/decision_memo.md)**

![Ask view: three approaches answering the same question side by side, with citations](docs/screenshots/ask.png)

| Compare | Inspect | Decision |
|---|---|---|
| ![Compare](docs/screenshots/compare.png) | ![Inspect](docs/screenshots/inspect.png) | ![Decision](docs/screenshots/decision.png) |

*Screenshots show fixture mode, so the RAG numbers in them are demo data, not results.*

**Contents:** [Why this matters](#why-this-matters) · [What it helps a PM do](#what-it-helps-a-pm-do) · [What it does not do](#what-it-does-not-do) · [Run it locally](#run-it-locally) · [Run a real evaluation](#run-a-real-evaluation) · [Use it for your own feature](#use-it-for-your-own-feature) · [How it's measured](#how-its-measured) · [Engineering](#engineering-practices) · [Repository map](#repository-map)

## Why this matters

Most AI feature launches are decided from a demo that went well. A demo shows the best case, on questions the builder picked, with nobody counting failures. The questions a PM is accountable for go unanswered:
- **Is it better than what we have?** An LLM that is right 85% of the time can still lose to a search box that is right 80% of the time for a fraction of the cost and latency.
- **How does it fail, and how often?** An invented policy, a quote from a superseded document, or one leaked salary band can cost more than every correct answer earns.
- **What would it cost to run?** Latency and cost per question should be measured, not guessed.
- **Would we make the same call if the results were bad?** If the bar is set after the numbers come in, it tends to move to wherever the numbers landed.

AI features are also non-deterministic. The same question can get a different answer tomorrow, a prompt tweak can fix one case and break three others, and the vendor can change the model under you. Judgement alone doesn't scale to that. The lab gives a PM a repeatable, auditable way to make the call and to make it again when something changes.

## What it helps a PM do

| PM job | Without the lab | With the lab |
|---|---|---|
| **Frame the decision** | "Let's add AI to policy search" | A written product question, a baseline to beat, and an explicit "do not launch" option ([PRD](docs/PRD.md)) |
| **Set the bar** | Agreed informally, often after the demo | Six thresholds for safety, correctness, citations, abstention, latency and cost, written in [`config/launch_criteria.yaml`](config/launch_criteria.yaml) and stored with every run so they can't drift quietly |
| **Compare options** | One prototype, judged on its own | Three approaches on the same 45 held-out questions, with the lift over search and the extra cost |
| **Understand failure** | Anecdotes from the demo | Every failed case can be filtered by category, opened, and reviewed. Failures are grouped into types such as "invented answer" or "used a superseded policy" |
| **Talk about risk honestly** | "It's about 90% accurate" | "32 of 35, interval 78–97%, on synthetic questions": every rate shows its sample size and uncertainty |
| **Bring in judgement** | Engineers grade their own output | A PM or policy owner can override any grade in the Inspect view, with their name on it. The automated scores are kept alongside, and the Decision view says how many labels were overridden |
| **Communicate the decision** | A slide with a screenshot | A generated [decision memo](docs/decision_memo.md) with the proposed action, evidence, failure modes, limits and the next experiment |
| **Decide again later** | Start over | Change a prompt, model or setting, run `make eval`, and compare the new run with the old one |

In practice, a PM uses it in four steps:
1. **Before building,** write the criteria and the evaluation questions with the people who own the risk (here, HR, Finance and Security).
2. **While building,** engineers tune on the 15 development questions only, so the 45 held-out questions stay a fair test.
3. **At the decision point,** open the Decision view or the memo. It proposes *proceed to a limited pilot*, *do not launch yet*, *do not launch* or *insufficient evidence*, and says which criterion drove it.
4. **After the decision,** use the failing cases and the "what we would test before a real rollout" list to plan the next experiment or the pilot.

[docs/for_product_managers.md](docs/for_product_managers.md) is a longer guide: how to run a decision review with the lab, how to read each view, and how to write good criteria and evaluation questions.

## What it does not do

**The lab supports a PM's decision. It does not make the decision, and it does not replace the PM.**

- **It proposes; people decide.** The recommendation applies thresholds that people chose. Whether 80% correctness is good enough, whether a pilot is worth the operational load, and how to weigh a failure against a business deadline are product judgements. The memo is a starting point for that conversation.
- **The criteria come from people.** Someone has to decide what "safe enough" and "useful enough" mean for their users and write it down. The lab only makes sure the bar is written down in advance and applied consistently.
- **Humans get the last word on grading.** Automated grading is strict about figures and lenient about wording, and the model judge can be wrong. A human review overrides both, and both originals are kept.
- **It can't see what isn't in the dataset.** Sixty synthetic questions show how a decision gets made; they don't prove production reliability. Real user research, shadow testing and a pilot are still needed, and the memo lists them.
- **It doesn't know your context.** Strategy, competition, cost of delay, team capacity and stakeholder trust aren't in the numbers.

What the lab does is take the repetitive, error-prone work off the PM: building a comparison, counting failures, computing intervals, and keeping everyone honest about the bar. That leaves the PM's time for the judgement calls.

## The example: Northstar's policy assistant

Northstar is a fictional 180-person SaaS company with staff in the US and UK and about 20 short policy documents. Employees ask HR and Finance the same questions every week, such as "Who approves travel over $2,000?". An AI assistant could answer them instantly. It could also:
- confidently quote a superseded policy;
- invent a policy that doesn't exist; or
- leak an HR-only salary band to someone who shouldn't see it.

The operations lead needs to know whether the assistant is **more useful than search**, and **safe enough for a limited rollout**.

| | Search | Basic RAG | Guarded RAG |
|---|---|---|---|
| **How it answers** | Best-matching sentence from BM25 keyword search. No model | An LLM answers from the top 5 passages and cites them | An LLM under a strict contract: use only the passages, cite every claim, abstain otherwise |
| **Access control** | A search index per role, containing only the documents that role may read | Same index, so restricted text never reaches the model | Same, plus validation of every citation, and a withheld answer if it names a restricted document |
| **When a citation is wrong** | Always points at a real, authorized passage, but the sentence may come from the wrong policy | Shown as "unverified" and never as a source; the answer is still shown | The answer is withheld and the reason recorded; no second "repair" call |
| **Unanswerable questions** | Abstains below a score threshold, but a keyword match can look like an answer | No abstention contract, so the risk it is expected to show is answering from something nearby | Abstains before calling the model if retrieval is weak, or when the model finds no support |
| **Latency and cost** | Milliseconds, $0 | One model call | One model call, or none when it abstains early |

The expected behaviour in the last two rows is the hypothesis a live run tests. The Compare and Decision views show what actually happened.

## Run it locally

### Prerequisites

| Tool | Version | Check with |
|---|---|---|
| Python | 3.10 or newer | `python3 --version` |
| Node.js | 22.22 or newer (or Node 24) | `node --version` |
| make | any | `make --version` |
| An Anthropic API key | only for live evaluation | [console.anthropic.com](https://console.anthropic.com) |

It runs on macOS and Linux. On Windows, use WSL. No Docker and no database server are needed: storage is a local SQLite file.

### Quick start: fixture mode, no key needed (about 2 minutes)

```bash
git clone https://github.com/andreasbloomquist/ai-feature-decision-lab.git
cd ai-feature-decision-lab
make setup     # creates .venv, installs backend and frontend dependencies
make demo      # builds the UI and serves everything at http://localhost:8000
```

Open http://localhost:8000. The badge in the top right reads *Fixture mode · demo data*. If port 8000 is taken, run `make demo PORT=8010`.

### A five-minute walkthrough

1. **Ask.** Press *Ask* on the default question, *Can I expense a client dinner without a receipt?* Three answers appear side by side. Click a numbered citation to open the exact source passage with its owner, effective date and access group.
2. **Access control.** Click the sample *What is the salary range for a Level 5 engineer in the US?* As an *Employee*, all three approaches decline, and none says that an HR-only document exists. Switch the role to *HR* and ask *What is the base salary range for a Level 5 engineer in the US?*: it's answered.
3. **Compare.** The held-out table shows every approach against every criterion. Each percentage shows its count, for example 32/35.
4. **Inspect.** Set *Category = Unanswerable* and open **U02 · Basic RAG**. It shows an invented answer: the $50 internet stipend presented as a phone stipend. Add a human review and notice that the automated grade is kept.
5. **Decision.** The criteria, the "no live evaluation yet" state, and what to test before a rollout.

For a presenter's version, see the [three-minute demo script](docs/demo_script.md).

### Example: ask a question from the command line

The UI is a thin layer over a JSON API, so you can script against it. With `make demo` running:

```bash
curl -s http://localhost:8000/api/ask \
  -H 'content-type: application/json' \
  -d '{"question": "Can I expense a client dinner without a receipt?",
       "role": "employee",
       "approaches": ["search", "guarded_rag"]}'
```

Abridged response in fixture mode:

```json
{
  "mode": "fixture",
  "role": "employee",
  "responses": [
    {
      "approach": "search",
      "status": "answered",
      "answer": "Client entertainment without an itemized receipt is not reimbursed. [NS-ENT-001#3]",
      "citations": [{"passage_id": "NS-ENT-001#3", "title": "Client Entertainment and Gifts", "valid": true}],
      "latency_ms": 2.8,
      "estimated_cost_usd": 0.0,
      "fixture": false
    },
    {
      "approach": "guarded_rag",
      "status": "answered",
      "answer": "No [NS-ENT-001#3]. Client entertainment always needs an itemized receipt and an attendee list, whatever the amount [NS-ENT-001#3]. The Missing Receipt Declaration in the Expense Reimbursement Policy cannot be used for client entertainment [NS-ENT-001#3].",
      "citations": [{"passage_id": "NS-ENT-001#3", "title": "Client Entertainment and Gifts", "valid": true}],
      "latency_ms": null,
      "estimated_cost_usd": null,
      "model": "fixture (not a model)",
      "fixture": true
    }
  ]
}
```

A few things to notice:
- **Search is real even in fixture mode**, so it has a measured latency and a cost of $0.
- **The guarded RAG answer is a saved example.** It has `"fixture": true`, and its latency and cost are `null` ("not measured"), never 0.
- **Roles are `employee`, `hr`, `finance` and `admin`.** Try the salary question with `"role": "employee"`: every approach returns `"status": "abstained"`.
- **Fixture mode only has saved answers for the sample questions.** A different question still gets a real search answer, but the RAG approaches return a `fixture_missing` error.

Other useful endpoints: `GET /api/health` (mode and model settings), `GET /api/decision` (the current recommendation), `GET /api/runs` (saved evaluation runs). The interactive API docs are at http://localhost:8000/docs.

### Troubleshooting

| Symptom | Fix |
|---|---|
| `make setup` fails on `npm ci` with an engine error | Upgrade Node to 22.22+ or 24 (`nvm install 22`). |
| `make: .venv/bin/python: No such file or directory` | Run `make setup` first. |
| Port 8000 already in use | `make demo PORT=8010`, or stop the other process. |
| RAG cards show `fixture_missing` | Expected in fixture mode for questions without a saved answer. Add an API key for live answers. |
| `make eval` says "No live evaluation possible" | Set `ANTHROPIC_API_KEY` in `.env`. |
| Live answers show `timeout` errors | Raise `LLM_TIMEOUT_S` in `.env`. Timeouts are recorded and count against coverage, never as free. |
| The UI shows stale results after deleting runs | `make clean-db` removes the local database; the fixture run is re-seeded on the next start. |

## Run a real evaluation

```bash
cp .env.example .env          # then set ANTHROPIC_API_KEY=...
make eval-dev                 # 15 development cases: use this while tuning (cheap and fast)
make eval                     # all 60 cases × 3 approaches + model judge; saves a new run, regenerates docs
make demo                     # the app now runs in live mode
```

A full run makes up to about 240 model calls (two RAG approaches on 60 cases, plus the judge), which typically costs a few dollars at the default settings; `make eval-dev` is about a quarter of that. Prices come from [`config/pricing.yaml`](config/pricing.yaml), and the run records the real token counts.

- **The Decision view and [decision memo](docs/decision_memo.md) use the newest live run** that covers the held-out set.
- **Runs are stored twice and never overwritten.** Each run is a new SQLite record and a `results/runs/<run_id>.json` export, with the prompts, criteria, dataset and model settings it used.
- **`make clean-db` deletes the local database only.** The exported JSON files stay.
- **Tune on development data only.** The held-out set exists to be a fair test; tuning against it makes the verdict meaningless.

The evaluation CLI takes options for narrower runs:

```bash
cd backend
../.venv/bin/python -m app.evaluation --mode live --split development --approach guarded_rag
../.venv/bin/python -m app.evaluation --mode live --case S01 --case U02 --judge none --label "prompt v2 smoke test"
```

### Configuration

All settings live in `.env` (see [`.env.example`](.env.example)):

| Variable | Default | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` | *(empty)* | Enables live mode. Never logged, stored or sent to the browser |
| `LLM_MODEL` | `claude-opus-5-5` | Answer model for both RAG approaches |
| `LLM_EFFORT` | `low` | `low`, `medium` or `high`; blank to use the API default |
| `JUDGE_MODEL` | `claude-sonnet-5-5` | Model judge used during evaluation |
| `LLM_TIMEOUT_S` | `20` | Per-call timeout in seconds |
| `LLM_MAX_RETRIES` | `1` | SDK retries for connection errors, 429s and 5xx |
| `FIXTURE_MODE` | *(empty)* | `1` forces fixture mode even with a key |
| `LAB_DB_PATH` | `results/lab.sqlite3` | SQLite database location |

## Use it for your own feature

The Northstar example is mostly data and config. To evaluate a different retrieval-style assistant, such as support articles, internal docs or product help, replace these files. Only the roles need a small Python edit:

| What | Where | Notes |
|---|---|---|
| Your documents | `data/corpus/*.md` | Markdown with front matter: `document_id`, `title`, `owner`, `effective_date`, `status` (`active` or `superseded`), `access_groups`, `country`. One passage per `##` section |
| Roles | `backend/app/access.py` | Map each role to the access groups it can read |
| Evaluation questions | `data/eval/cases.jsonl` + `dataset.yaml` | Each case has a question, role, category, split, the facts a correct answer must contain, and the acceptable and forbidden sources. Keep a development and a held-out split |
| Launch criteria | `config/launch_criteria.yaml` | Thresholds, the target approach and the baseline. Write these **before** the first live run |
| Prompts | `config/prompts/*.md` | Versioned; bump the version when you change one |
| Prices | `config/pricing.yaml` | Needed for cost estimates |

Then run `make eval-dev` while tuning, and `make eval` once for the decision. [docs/for_product_managers.md](docs/for_product_managers.md) covers how to write the questions and criteria.

What's missing to make this easier (CSV import, plugging in your team's own system over HTTP, a run-to-run diff) is prioritized in the [product review and roadmap](docs/product_review.md).

## How it's measured

- **Correctness:** the share of answerable cases that contain every required fact with no material contradiction. Abstentions and errors count as misses.
- **Citation validity:** the share of answered cases whose citations exist, are authorized for the role, come from active policies, were in the model's context, and include an acceptable source.
- **Abstention quality:** the share of unanswerable cases that were declined.
- **Access safety:** the number of restricted document IDs, facts or verbatim passages shown to a role that can't read them. The target is 0, and any disclosure is a hard stop.
- **Latency** (median and p95) and **cost per question**, calculated from recorded token usage.
  - Missing usage is reported as *unavailable*, never $0.
  - Both measures need at least 90% of cases measured to count.
  - An answer cut off at the token limit is recorded as a `truncated` error, not graded as complete.

Grading happens in three layers:
- A deterministic grader always runs.
- An optional model judge adds a verdict with its rationale, labelled *model-judged*.
- A human reviewer can override the final label, and the automated scores are kept alongside.

**Sixty synthetic questions are enough to show how the decision gets made. They are not enough to prove production reliability.** The [evaluation report](docs/evaluation_report.md) lists the limits.

## Engineering practices

**Architecture.** A FastAPI backend handles authorization, retrieval, the three approaches, grading, the evaluation runner and the decision logic. Runs are stored in SQLite, and a React + TypeScript UI provides the four views. See the [architecture doc](docs/architecture.md) for the diagram and the request and evaluation paths. Every significant choice is recorded in [technical decisions](docs/decisions.md), with the alternatives considered and when to revisit it.

- **Correctness first.**
  - Every acceptance criterion has a named test.
  - Every defect found in the [engineering reviews](docs/engineering_review.md) has a regression test.
- **Security.**
  - Access control is enforced before retrieval and checked again at citations, previews and grading.
  - A restricted document gets the same 404 as a missing one.
  - API keys never leave the process. A test checks every endpoint, the database and the exported runs for the key.
- **Reproducible runs.** Each run stores the prompts, criteria, dataset and model configuration it used. Editing the criteria later cannot change a past verdict.
- **Quality gates.** `ruff` (lint + format), ESLint with strict TypeScript, backend tests on Python 3.10 and 3.12, frontend tests and a production build, all in CI. No lint suppressions.
- **Small, readable modules.** No LLM framework: the difference between basic and guarded RAG is two short files, and one read-side module (`results.py`) serves the API, the decision logic and the reports.

## Repository map

| Path | Contents |
|---|---|
| [`data/corpus/`](data/corpus) | 21 synthetic Markdown policies with front matter: two travel-policy versions, US and UK variants, approval thresholds, 4 restricted documents |
| [`data/eval/cases.jsonl`](data/eval/cases.jsonl) | 60 questions: 24 single-document, 12 multi-document, 8 outdated, 8 unanswerable, 8 role-based. Split 15 development / 45 held-out |
| [`config/`](config) | Versioned prompts, per-approach settings, pricing, launch criteria |
| [`backend/app/`](backend/app) | FastAPI server, retrieval, approaches, grading, evaluation runner, decision logic |
| [`frontend/src/`](frontend/src) | React + TypeScript UI: Ask, Compare, Inspect, Decision |
| [`docs/`](docs) | [For product managers](docs/for_product_managers.md) · [PRD](docs/PRD.md) · [Architecture](docs/architecture.md) · [Technical decisions](docs/decisions.md) · [Engineering review](docs/engineering_review.md) · [Evaluation report](docs/evaluation_report.md) · [Decision memo](docs/decision_memo.md) · [Demo script](docs/demo_script.md) · [Product review and roadmap](docs/product_review.md) |

## Development

```bash
make api      # backend with reload on :8000
make web      # Vite dev server on :5173 (proxies /api to :8000); use both together
make check    # everything CI runs: lint, format check, typecheck, backend and frontend tests
make reports  # regenerate the evaluation report and decision memo from saved runs
make fixtures # rebuild the saved example responses used in fixture mode
```

Secrets are read only from the environment or `.env`, which is git-ignored. The browser receives only the key's variable name and whether it is set.
