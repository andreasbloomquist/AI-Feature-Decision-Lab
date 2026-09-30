# AGENTS.md

Instructions for AI coding agents working in this repository. Read this file, then [CONTRIBUTING.md](CONTRIBUTING.md), before changing anything. People are welcome to read it too; it's the most compact description of how the code fits together.

## What this project is

A lab for deciding whether to launch an AI feature, based on evidence. It runs three approaches (keyword `search`, `basic_rag`, `guarded_rag`) on a fixed evaluation set over a synthetic policy corpus. The sizes and splits are defined in `data/eval/dataset.yaml`. It grades the answers, and applies launch criteria written in advance to propose one of: *limited pilot*, *do not launch yet*, *do not launch*, *insufficient evidence* or *demonstration only*. The user of the lab is a product manager. The lab proposes; the PM decides.

## Commands

Run everything from the repository root.

| Task | Command |
|---|---|
| Install | `make setup` |
| Every check CI runs: lint, format, types, all tests and the production build. Run it before every push | `make check` |
| Backend tests only | `cd backend && ../.venv/bin/python -m pytest` |
| One backend test | `cd backend && ../.venv/bin/python -m pytest tests/test_decision.py -k disclosure` |
| Frontend tests only | `cd frontend && npx vitest run` |
| Format Python | `cd backend && ../.venv/bin/ruff format app tests ../scripts` |
| Serve the app on :8000 (fixture mode without a key) | `make demo` |
| Regenerate the generated docs | `make reports` |
| Live evaluation (needs `ANTHROPIC_API_KEY`, costs money) | `make eval-dev` (15 cases) or `make eval` (60) |

**Never run `make eval` or `make eval-dev` without explicit permission from the user.** Both call a paid API.

## Invariants: never break these

Each of these is enforced by tests. A change that needs to relax one is a product decision; stop and ask the user.

1. **Access control happens before retrieval.** Each role has its own BM25 index containing only the documents it may read (`backend/app/retrieval.py`, `backend/app/access.py`). Restricted text must never reach scoring, the model's context, citations, previews or public responses.
2. **No existence oracle.** A restricted document and a nonexistent one look identical in every public field (the same 404, the same `[restricted]` placeholder, the same `unavailable` reason). See `ApproachResponse.public_dict` in `backend/app/schemas.py`.
3. **Fixture data is never a measurement.** Fixture responses have `fixture: true` and `null` latency, tokens and cost. They are labelled "demo" in every view, and they never produce a pass or fail on latency or cost.
4. **Missing usage is never $0.** Unknown cost is `null` ("unavailable"). Search's $0 is real, because search makes no model call.
5. **Past verdicts are frozen.** Each run stores its launch criteria, their hash, the dataset cases, the prompts and the model settings (`config_snapshot`). Decisions use the stored copy, never the current files.
6. **Guarded RAG never repairs an answer.** If validation fails, the answer is withheld (status `error`, with a `guard_reason`). There is no second model call.
7. **A disclosure is a hard stop** at any sample size, and never counts as a success.
8. **Human reviews are visible.** A review needs a verdict and a reviewer name, and it keeps the automated grade. Reviews that change a label are disclosed on the Decision view and in the memo, for both the target and the baseline (`correctness.human_reviews`, `human_override_note`).
9. **API changes are additive.** Add fields; never rename or remove them. Update `frontend/src/types.ts` in the same change.
10. **Secrets stay in the environment.** Keys come only from the environment or `.env`. They never appear in responses, logs, the database, exported runs or the browser. `test_no_secret_in_any_response_database_or_export` checks this.

## Where things live

| Path | What it does |
|---|---|
| `config/launch_criteria.yaml` | The launch criteria: thresholds, target and baseline approach, `min_sample_size`, `min_measurement_coverage`, `max_error_rate`. **Changing a threshold is a product decision: ask first.** |
| `config/approaches/*.yaml`, `config/prompts/*.md` | Per-approach settings and versioned prompts. Changing a prompt means changing its version too |
| `config/pricing.yaml` | Price per million tokens, per model |
| `data/corpus/*.md` | Policy documents with front matter. One passage per `##` section |
| `data/eval/cases.jsonl` | Evaluation cases. The `held_out` split must never be used for tuning |
| `backend/app/approaches/` | `search.py`, `basic_rag.py`, `guarded_rag.py`, and the shared `base.py` (`Approach.generate`) |
| `backend/app/citations.py` | Parsing, validation and redaction of citation markers |
| `backend/app/grading.py`, `judge.py` | Deterministic grader; optional model judge |
| `backend/app/metrics.py` | Rates with Wilson intervals, nearest-rank percentiles, cost, error split |
| `backend/app/results.py` | Read side: rows joined to cases, `succeeded`, `run_validity`, `latest_runs` |
| `backend/app/decision.py` | Applies the criteria and builds the recommendation |
| `backend/app/evaluation.py` | Evaluation runner and CLI (`python -m app.evaluation --help`) |
| `backend/app/reports.py` | Writes `docs/evaluation_report.md` and `docs/decision_memo.md` |
| `backend/app/main.py` | FastAPI routes; also serves the built UI |
| `frontend/src/views/` | Ask, Compare, Inspect, Decision |
| `frontend/src/useAsync.ts` | The only data-loading hook. It never returns data for a stale key |

## How to make common changes

- **Add a metric or criterion.** Compute it in `metrics.py`, then add it to `config/launch_criteria.yaml` (and bump `version`). Handle it in `decision.evaluate_criteria`, show it in `DecisionView.tsx`, and add a test in `backend/tests/test_decision.py`.
- **Change a prompt.** Copy it to a new version file (for example `guarded_rag.v2.md`), point the approach YAML at the new file, and test on the development split only. The judge prompt is chosen by `JUDGE_PROMPT` in `backend/app/judge.py`, not by YAML.
- **Add an API field.** Add it in the backend, then add it as optional in `frontend/src/types.ts` and use it in the view. Test both sides.
- **Change what a report says.** Edit `reports.py`, then run `make reports`. Never edit the generated Markdown by hand.

## Rules for agents

- **Workflow.** Work on a branch and open PRs against `main`, following [CONTRIBUTING.md](CONTRIBUTING.md). Never push to `main`, and never force-push a shared branch.
- **Review.** Before you open a PR that changes code, configuration, prompts, the dataset or the launch criteria, get an independent principal-engineer review of the diff: a separate agent with no context from you, reviewing against the checklist in CONTRIBUTING.md. Verify each finding, fix it with a regression test, and record Medium-or-higher findings in `docs/engineering_review.md`.
- **Verify before claiming.** Run `make check` and report the actual result. Say plainly what you did not verify, for example "not tested against a live model".
- **Docs move with code.** Update the README, `docs/`, this file and `docs/ROADMAP.md` in the same PR when behaviour, commands or plans change.
- **Ask before:**
  - changing launch criteria thresholds or the dataset;
  - spending API credits;
  - deleting runs in `results/`;
  - changing anything that relaxes an invariant above.

## Documentation map

| Reader | Start with |
|---|---|
| A product manager using the lab | [README](README.md) → [docs/for_product_managers.md](docs/for_product_managers.md) |
| A contributor | [CONTRIBUTING.md](CONTRIBUTING.md) → [docs/architecture.md](docs/architecture.md) |
| Someone asking "why is it built this way?" | [docs/decisions.md](docs/decisions.md) |
| Someone asking "what's next?" | [docs/ROADMAP.md](docs/ROADMAP.md), with the reasoning in [docs/product_review.md](docs/product_review.md) |
| Someone asking "what was found and fixed?" | [docs/engineering_review.md](docs/engineering_review.md) |
| Someone looking for the requirements | [docs/PRD.md](docs/PRD.md) (R1–R10) |
| Someone looking for results | [docs/decision_memo.md](docs/decision_memo.md) and [docs/evaluation_report.md](docs/evaluation_report.md) (both generated) |
