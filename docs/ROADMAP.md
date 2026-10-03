# Roadmap

This is the plan of record for the AI Feature Decision Lab: what gets built next, in what order, and how we'll know each stage is finished. The reasoning behind the priorities is in the [product review](product_review.md). This page is the list.

**How to use this page**
- Every roadmap item has an ID such as `R1.2`. Put the ID in the PR title or description of the work that delivers it, for example `feat: run-to-run diff view (R2.3)`.
- When a PR merges, update the item's status here in the same PR. Statuses are `Done`, `In progress (#PR)`, `Next` and `Planned`.
- To add or reorder items, open a PR that edits this file and explains why. The order is a product decision, so it needs the same review as code.

**Last updated:** 2026-09-30

## Where the project is today

The lab can run a complete, pre-registered launch decision for **one retrieval-style Q&A feature**: the Northstar policy assistant. It compares three approaches and applies six launch criteria, a data-quality gate and a human-review layer. It has been reviewed twice by a principal engineer and once by a product manager ([engineering review](engineering_review.md), [product review](product_review.md)).

**What it can't do yet:**
- It can't be pointed at your own system or your own questions without editing code.
- It can't compare two runs.
- It can't show that the held-out set was used only once.

The milestones below close those gaps in order.

## Milestones

| Milestone | Outcome | Exit test | Status |
|---|---|---|---|
| **M0: Trustworthy baseline** | The Northstar decision can't be skewed by broken runs, debug runs, silent human overrides or leaks hidden by small samples | A review by a principal engineer and a PM finds no path to a wrong recommendation | Done ([#1](https://github.com/andreasbloomquist/AI-Feature-Decision-Lab/pull/1)) |
| **M1: A verdict a skeptic accepts** | Anyone can see whether labels were changed, how often the held-out set was used, and whether a pass is statistically meaningful | A skeptical Security lead reads one screen and can answer all three questions | In progress (#4 merged, #5 open) |
| **M2: Works on your feature** | A PM on another team evaluates their own Q&A system with their own questions, without touching Python | That PM plugs in their team's endpoint and 150 real support tickets, runs two iterations, and compares them | Planned |
| **M3: A team process** | Risk owners sign off on criteria, reviewers share the grading load, and the decision is shared outside the app | A full decision review runs from the exported report, with signed criteria and a sampled review queue | Planned |
| **M4: Beyond Q&A** | The lab can evaluate summarization, classification and extraction features | One non-RAG feature goes through a full decision | Planned |

## Items

Effort: **S** is up to about 2 days, **M** is about a week, **L** is more than a week.

### M0: Trustworthy baseline (done)

| ID | Item | Status |
|---|---|---|
| R0.1 | A disclosure is a hard stop at any sample size | Done (#1) |
| R0.2 | Data-quality gate: a run dominated by errors gets no quality verdict and never replaces a good run | Done (#1) |
| R0.3 | Partial and debug runs are never the decision run | Done (#1) |
| R0.4 | Human overrides are disclosed on the Decision view and in the memo; a review needs a verdict and a name | Done (#1) |
| R0.5 | No existence oracle through citations | Done (#1) |
| R0.6 | README, PM guide, contributor and agent guides, this roadmap | Done (#1, #2) |

### M1: A verdict a skeptic accepts

| ID | Item | Problem it solves | Effort | Status |
|---|---|---|---|---|
| R1.1 | **Designated decision run.** Mark one run as the decision of record. Lock human reviews on its held-out responses | "Which run is the decision based on, and can it still change?" | S | In progress (#5) |
| R1.2 | **Held-out usage counter.** Count evaluations of the held-out split per dataset version, and warn when it's more than one | "Did they keep re-running until it passed?" | S | In progress (#5) |
| R1.3 | **Confidence-aware criteria.** Per criterion, choose whether the point estimate or the lower bound of the 95% interval must clear the threshold. Set a minimum n per criterion (for example, at least 30 access-denied cases for the zero-leak check) | Passing on 4 cases, or at 28/35 | S | Done (#4) |
| R1.4 | **Sample-size planner.** Given an expected rate and a threshold, say how many cases are needed | "How many questions do I need?" | S | Planned |
| R1.5 | **Paired lift with an interval.** Target versus baseline on the same cases: wins, losses and ties, with a confidence interval | "Is it really better than search?" | S | Planned |
| R1.6 | **Decision record.** The PM's final call, rationale, approvers and date, linked to the run and the criteria hash | "Why did we launch?" six months later | S | Planned |

### M2: Works on your feature

| ID | Item | Problem it solves | Effort | Status |
|---|---|---|---|---|
| R2.1 | **Pluggable approaches.** Register an approach in YAML, as a prompt plus model, or as an HTTP endpoint that returns the common response object | Evaluating your team's system, not the lab's | M | Planned |
| R2.2 | **Roles and access groups in YAML** instead of `backend/app/access.py` | Adapting without Python | S | Planned |
| R2.3 | **Run-to-run diff view.** Per-criterion change, the cases fixed and broken, and the config differences | "Did my change help, and what did it break?" | M | Planned |
| R2.4 | **Dataset import** from CSV or a spreadsheet, with validation and automatic splitting | Real questions without hand-editing JSONL | M | Planned |
| R2.5 | **"Add to eval set"** from the Ask and Inspect views, as a draft development case | Turning anecdotes into evidence | S | Planned |
| R2.6 | **Segments in the UI.** Results by category, role, country and custom tags, with n per cell | "Where does it fail?" | S | Planned |
| R2.7 | **Cost projection at volume.** Monthly cost range, with evaluation cost shown separately | Finance's first question | S | Planned |
| R2.8 | **Per-project decision copy.** Rollout tests, next experiments and limitations in YAML | A memo that fits your feature | S | Planned |

### M3: A team process

| ID | Item | Problem it solves | Effort | Status |
|---|---|---|---|---|
| R3.1 | **Criteria authoring with owners and sign-off.** Locked at the first live run; any change creates a new version | Risk owners owning the bar | M | Planned |
| R3.2 | **Review workflow.** Sampled queue, reviewer assignment, blind review, double review with agreement reported, and judge-versus-human agreement | Trusting the grader and sharing the load | M | Planned |
| R3.3 | **Shareable report export.** One HTML or PDF per run, with a one-page summary for executives | Decisions happen in documents and meetings | M | Planned |
| R3.4 | **Repeat runs.** Run each case k times and report flaky cases | Non-determinism | S–M | Planned |
| R3.5 | **Regression gate in CI.** Run the development split on PRs that change prompts or models | Keeping quality after launch | S | Planned |
| R3.6 | **Held-out refresh.** Version and rotate held-out sets, and mark a set "used" once its failures have been studied | Keeping successive decisions honest | M | Planned |

### M4: Beyond Q&A

| ID | Item | Problem it solves | Effort | Status |
|---|---|---|---|---|
| R4.1 | **Generic case schema and graders.** Rubric cases graded by a judge, exact match and classification, and extraction field checks | Using the lab for non-RAG features | L | Planned |
| R4.2 | **Shadow-mode log import.** Real production questions for sampling, labelling and conversion into cases | Evidence from real traffic before a pilot | M | Planned |
| R4.3 | **Severity-weighted failures** (optional per case) | Not all misses cost the same | S | Planned |

## Engineering follow-ups

These aren't product features, but they keep the codebase healthy. They are tracked in [engineering review → known limitations](engineering_review.md#known-limitations-and-next-steps).

| ID | Item | Effort | Status |
|---|---|---|---|
| E1 | Static type checking for the backend (mypy or pyright) in CI | S | Planned |
| E2 | A small Playwright suite in CI covering the four views | S | Planned |
| E3 | Run the first live evaluation and publish its memo | S (needs an API key) | Planned |

## Deliberately not on the roadmap

Each of these was considered and rejected; the reasons are in the [product review](product_review.md#whats-not-important-do-not-build-or-de-emphasize). Reopening one needs a PR that explains what changed.

- Better retrieval (embeddings, hybrid search, rerankers) inside the lab. The lab judges approaches; it doesn't compete with them.
- A multi-provider LLM framework. The HTTP approach adapter (R2.1) covers other providers.
- Model or prompt sweep grids. They invite tuning on the held-out set.
- Real authentication, SSO or multi-tenancy. A reviewer name is enough.
- More charts and dashboards.
- Production monitoring. That's a different product; shadow-log import (R4.2) covers the need.
- Generating evaluation questions with an LLM as a headline feature.
