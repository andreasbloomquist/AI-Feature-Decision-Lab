# Product review

This review is the reasoning behind the [roadmap](ROADMAP.md). The roadmap is the plan of record and is kept up to date; this page is a snapshot from 2026-09-29.

*An independent review from the point of view of a Director-level product manager who has shipped LLM features. It was written by a reviewer agent with no stake in the code, at commit `89d2924` on 2026-09-29. The reviewer read the docs, config, dataset and code, used the running app in fixture mode, and probed the API with a throwaway database.*

> **What changed after this review.** Several findings were fixed in the same pull request:
> - **Visible overrides.** Human overrides are now disclosed: the Decision view and the memo say how many of the target's correctness labels came from human review.
> - **Deliberate reviews.** A review needs an explicit verdict (no default) and a reviewer name.
> - **Configurable labels.** Recommendation text names the configured target and baseline instead of "Guarded RAG" and "search".
> - **Doc drift.** The broken `product_review.md` links and the "By category" claim are fixed.
>
> Everything else below is open, and the enhancement table is the roadmap.

## Verdict

As a **worked example and teaching artifact** this is one of the better ones I've seen. It does a thing most AI launch reviews skip: it writes the bar down before the results exist, compares against a cheap baseline, counts failures by type, and shows every rate with its n and a confidence interval. A PM on a **retrieval-style Q&A feature** (policy, support articles, internal docs) with an engineer to help could use it today for one decision: **"is this good enough for a limited pilot, and if not, what's the next experiment?"**. It is **not yet a tool a PM would adopt on their own feature**, for four reasons. The approaches, roles and much of the decision copy are hard-coded. There is no bring-your-own-data path that doesn't involve editing JSONL and Python. It can't diff two runs. And the pre-registration story, its core promise, has a hole: anyone can quietly change held-out labels after the fact. Fix integrity and portability first. Resist adding features.

## What's strong (keep; don't change)

1. **Pre-registered criteria, snapshotted and hashed per run** (`config/launch_criteria.yaml`, `decision.py:run_criteria`, the "Criteria changed since this run" banner in `DecisionView.tsx`). This is the most valuable idea in the repo. It turns "we moved the goalposts" from an argument into a visible event.
2. **"Insufficient evidence" is a first-class verdict.** It covers too few cases, less than 90% measured coverage, and a run dominated by errors (`max_error_rate`, `apply_validity_gate`). Most dashboards let missing data default to pass. This one refuses, and it treats a timeout with no tokens as unmeasured, not free. That is exactly the discipline a PM needs when a VP asks "so is it green?".
3. **n and CI next to every percentage**, plus the "CI crosses the threshold" note on the Decision view. "32/35, 78–97%" is the right way to talk to execs about small evals.
4. **Baseline-first framing.** Search is a real, measured competitor, and the headline is *lift over search* (`_comparison`). "Must beat the dumb thing" is the question PMs forget to ask.
5. **Failure taxonomy over accuracy.** Outcomes such as `invented_answer`, `unnecessary_abstention`, `answered_without_access` and `disclosure`, together with category filters and deep links from a failing criterion to example cases, let a PM tell the *story* ("it turns the internet stipend into a phone stipend", U02) rather than cite a number.
6. **Hard stop vs target.** A disclosure fails at any sample size and cannot be averaged away. This is the right asymmetry for risk owners.
7. **Explicit "the lab proposes, you decide" framing** (README "What it does not do", and the "What stays your job" table in `for_product_managers.md`). Keep this. It is also the correct adoption posture.
8. **The 45-minute decision-review agenda** in the PM guide. It is practical and reusable, and it's the part most PMs will actually copy.
9. **Honest fixture mode.** "Demo: pass" badges, cost and latency left unplotted rather than drawn at $0. That builds trust.

## What's weak or missing

### Decision integrity (the core promise has gaps)

- **Human review can silently flip a held-out verdict.** I tested this with a scratch database. An anonymous reviewer marked Guarded RAG's M04 (an *abstention*) and S19 (a *timeout*) as "Correct". Held-out correctness went from 32/35 to 34/35, and the correctness criterion's "CI crosses threshold" warning disappeared. The Decision view, Compare view and memo show **no indication** that labels came from human overrides. `label_sources` is computed in `metrics.py` but never rendered. The review form also **defaults to "Correct"** (`useState("correct")` in `InspectView.tsx`), the reviewer name is optional, and there's no reason code, no second reviewer and no lock. The thresholds are pre-registered but the labels aren't protected. This is the #1 fix.
- **Nothing stops "run shopping" on the held-out set.** `make eval` runs all 60 cases every time, the Decision view uses "the newest live run", and the Inspect view shows held-out answers freely. The docs say "don't tune on held-out", but the tool doesn't count how many times held-out has been evaluated, and it has no notion of a designated "decision run". A PM can't prove the verdict wasn't the fifth try.
- **The verdict rule uses point estimates.** 28/35 (80%, CI 64–90%) is "Proceed to a limited pilot" with a footnote. For the hard stop, "0 disclosures in 45 cases" rests on **4 held-out access-denied cases** (2 non-employee roles in the whole dataset; 56 of 60 cases are asked as `employee`). 0/4 has an upper bound near 49%. The UI presents it as a clean pass.
- **The lift over search has no interval or paired test**, although both approaches ran on the same cases, so a paired comparison is cheap and much more powerful.
- **Each case runs once.** LLM non-determinism is called out in the README but not measured. There's no repeat-n or per-case flakiness.

### PM workflow gaps

- **No run-to-run diff.** The PM guide says "compare the new run with the old one", but `RunPicker` selects a single run. After a prompt change, a PM needs "these 4 cases got fixed, these 2 regressed". That's the most common question in iteration, and it is currently unanswerable without a spreadsheet.
- **No path from exploration to evidence.** In Ask, a PM finds a bad answer and can't turn it into an eval case. Cases can only be added by editing `data/eval/cases.jsonl` by hand, including `match_any` alias lists.
- **Criteria authoring and sign-off happen in YAML plus a PRD sentence** ("put their names in the PRD"). Nothing records who approved which threshold, or when.
- **Cost is shown per question, never per month.** The PRD's "$40/month at 2,000 questions" is exactly what finance asks for, and it isn't computed. There's no sensitivity to volume or to answer-length growth.
- **The docs promise a "By category" table in Compare** (`for_product_managers.md` §4). It exists only in the generated report, not the UI. Segment views such as category, role and US/UK are where PMs find the real story.
- **Broken links:** README and the PM guide both link `docs/product_review.md`, which doesn't exist.

### Stakeholder communication

- The memo is a Markdown file regenerated by `make reports` into `docs/`. It is not a shareable, versioned artifact tied to a run, and it has no field for the **PM's actual decision and rationale** ("we're overriding the proposal because…"). The guide says to "record your call", but the tool gives you nowhere to do it.
- The Decision view is dense for an exec audience. It needs a one-screen summary with the decision, top 3 risks, lift, monthly cost and what we're doing next.

### Generalizability

- The **approaches are hard-coded** in `APPROACH_NAMES` (`approaches/base.py`), the `/api/ask` schema (`main.py`), and the frontend `APPROACHES`. **Roles are Python** (`access.py`), although README tells PMs to "map each role" there. `recommend()` hard-codes the string "Guarded RAG" in its summaries, even if `target_approach` changes. `ROLLOUT_TESTS` and `NEXT_EXPERIMENTS` are Northstar-specific constants. `limitations()` always says "synthetic questions… written by the same author as the documents", even if you import real tickets. The claim "the example is data and config, not code" is only partly true.
- **The grading model assumes RAG Q&A**, with required facts, acceptable documents and answerability. Summarization, classification, extraction or agentic features would need a different case schema and grader. The README is honest about this.

## What's not important (do not build, or de-emphasize)

- **More retrieval sophistication** (embeddings, hybrid, rerankers) *inside the lab*. The lab judges approaches; it shouldn't compete with the team's stack. Make approaches pluggable (e.g. "call this endpoint") instead.
- **A generic multi-provider LLM abstraction or LangChain-style framework.** The HTTP adapter below covers other providers for free.
- **Model/prompt sweep grids.** They tempt people to run shopping on held-out data. Allow sweeps on the dev split only, and even that is P2 at best.
- **Real auth/SSO, multi-tenant SaaS, RBAC admin.** A reviewer identity is enough (a name/email, required for held-out reviews). Don't build an identity system.
- **Fancier charts and dashboards.** The one quality-versus-cost chart is enough. Every extra chart is another thing to misread at n=35.
- **Online/production monitoring.** That's a different product (observability). An "import shadow-mode logs as a dataset" path gets 80% of the value.
- **LLM-generated eval questions** as a headline feature. They make the "too clean" problem worse. At most, offer them as a labelled *seed* for near-miss unanswerables.
- **More fixture polish, demo scripts and hiring-manager narration** (`docs/demo_script.md`). Useful for the portfolio, irrelevant to adoption.
- **Deep engineering docs** (the 500-line `decisions.md`). Fine to keep, but PMs won't read them. Don't grow them.

## Enhancement list

| Pri | Enhancement | PM problem it solves | Why it matters | Effort |
|---|---|---|---|---|
| P0 | **Label-integrity guardrails** *(partly done: label sources disclosed on Decision and in the memo; required reviewer; no default verdict)*: show label sources (e.g. "3 of 35 labels human-overridden") on Decision, Compare and memo; show before/after verdict if overrides changed it; required reviewer and reason; no default verdict; reviews on held-out locked once a run is designated the decision run | "Can I trust this verdict wasn't massaged?" | Pre-registering thresholds is pointless if labels are unprotected. This is the tool's core credibility claim | S |
| P0 | **Designated decision run + held-out access log**: mark one run as "decision of record"; count held-out evaluations per dataset version; warn at >1 | Run shopping / held-out leakage | Makes "we didn't tune on the test" provable, not asserted | S–M |
| P0 | **Run-to-run diff view**: per-criterion delta, cases fixed/regressed per approach, prompt/model/config diff | "Did my change help, and what did it break?" | The most frequent PM question during iteration; enables regression gating | M |
| P0 | **Bring-your-own dataset import**: CSV/Sheet (question, role, reference answer, required facts, sources, category, split) with validation and auto-split; import from ticket/Slack/search-log exports | Getting real questions in without editing JSONL | Synthetic questions are the #1 stated limitation; adoption dies at the data step | M |
| P0 | **Pluggable approaches via config**: register an approach as a YAML entry (prompt+model) or an **HTTP endpoint** that returns the common response object; roles and access groups in YAML; remove hard-coded "Guarded RAG" copy | Evaluating *my team's* system, not the lab's | Without this it only evaluates its own toy implementations | M |
| P0 | **Confidence-aware decision rules**: per criterion, pre-register "point estimate" vs "CI lower bound must clear"; minimum n per criterion (e.g. ≥30 access-denied cases for a hard stop) | Passing on 4 cases, or at 28/35 | Prevents false confidence; makes "insufficient evidence" meaningful | S |
| P0 | **Sample-size planner**: "to show ≥80% with 95% confidence at an expected 90%, you need ~100 answerable cases; for disclosure rate <1%, ~300 adversarial cases" | "How many cases do I need?" | The first question every PM asks when writing criteria; today n is arbitrary | S |
| P1 | **Decision record**: PM's final call (accept/override proposal), rationale, approvers, date, linked to the run and criteria hash; exportable | Audit trail; "why did we launch?" six months later | The guide says to record the call but there's nowhere to do it | S |
| P1 | **Shareable report export** (single HTML/PDF per run, exec one-pager on top: decision, lift, monthly cost, top 3 failure stories, next step) | Communicating to execs/legal without a live app | Decisions happen in docs and meetings, not in localhost | M |
| P1 | **Criteria authoring UI with owners and sign-off**: each criterion has owner, rationale, signed-off-by/at; lock on first live run; changes create a new version | Getting risk owners (Security, Legal, HR) to own the bar | Makes the pre-registration social, not just technical | M |
| P1 | **Segment analysis in the UI**: by category, role, locale, and any custom case tag, with n per cell; flag segments below threshold even when the aggregate passes | "Where does it fail?" / fairness across groups | Aggregate passes hide segment failures (e.g. UK users); promised in docs already | S |
| P1 | **Paired lift with CI** (target vs baseline on the same cases; win/loss/tie counts) | "Is it really better than search?" | The product question is a comparison; give it an honest interval | S |
| P1 | **Cost and latency projection at volume**: monthly questions × cost/q with range, plus a budget line; include judge/eval cost separately | Finance's first question | Turns $0.014/question into a budget decision | S |
| P1 | **Human review workflow**: stratified sample queue (all failures + x% of passes), reviewer assignment, blind review (grade hidden), double-review a subset with agreement (κ) reported; judge-vs-human agreement shown | Trusting the grader, spreading review load to policy owners | Judge reliability is currently asserted, not measured | M |
| P1 | **"Add to eval set" from Ask and Inspect**: capture question + role + observed answer as a draft case (dev split by default) | Turning anecdotes into evidence | Closes the loop from demo to eval; builds the dataset organically | S |
| P1 | **Generic case schema / non-RAG graders**: rubric-based cases (criteria + judge), exact-match/classification, extraction field checks; answerability optional | Using it for summarization, classification, extraction features | Broadens the audience from "RAG Q&A PMs" to most AI-feature PMs | L |
| P1 | **Repeat runs / variance**: run each case k times; report flaky cases and pass@k/consistency | Non-determinism | A 1-of-3 failure rate is a different launch risk than 0-of-3 | S–M |
| P2 | **Configurable decision copy**: rollout tests, next-experiment playbook and limitations become per-project YAML (limitations auto-derived from dataset provenance tags) | Memo that's accurate for my feature | Currently asserts "synthetic, same author" even for real data | S |
| P2 | **Shadow-mode log import**: ingest production questions and answers (no references) for sampling, labelling and conversion to cases | Evidence from real traffic before the pilot | Bridges the lab to the pilot phase without building monitoring | M |
| P2 | **CI regression gate**: `make eval-dev` in CI with thresholds on the dev split; fail PRs that regress | Keeping quality after launch as prompts and models change | Cheap, and the diff view makes it actionable | S |
| P2 | **Held-out refresh workflow**: version and rotate held-out sets; mark a set "inspected/burned" once its failures have been studied | "Re-test on a fresh held-out set" is advised but unsupported | Keeps successive decisions honest | M |
| P2 | **Weighted/severity-scored failures**: e.g. an invented approval rule costs more than a missed nuance; optional severity per case | Not all misses are equal | Aligns the metric with user harm; keep optional to avoid false precision | S |
| P2 | ~~**Fix doc drift**: broken `product_review.md` links, the "By category in Compare" claim~~ *(done)* | Trust in the docs | Small, but PMs notice broken promises first | S |

## 30/60/90-day roadmap

**Days 0–30: make the verdict trustworthy.** Label-integrity guardrails; designated decision run and held-out counter; confidence-aware decision rules; sample-size planner; paired lift with CI; decision record; fix doc drift. *Exit test:* a skeptical Security lead can read one screen and see whether any human changed a label, how many times held-out was touched, and whether each pass is statistically meaningful.

**Days 31–60: make it usable on a real feature.** Pluggable approaches (YAML + HTTP endpoint adapter) and roles in YAML; CSV/Sheet dataset import with validation; "add to eval set" from Ask/Inspect; run-to-run diff; segment analysis in UI; cost projection. *Exit test:* a PM on a different team plugs in their team's existing Q&A endpoint and 150 real support-ticket questions without touching Python, and runs two iterations with a diff.

**Days 61–90: make it a team process.** Criteria authoring with owners/sign-off; human review workflow (sampling, assignment, blind double-review, κ, judge agreement); shareable exec report export; repeat-run variance; begin the generic case schema (rubric-judge cases first). *Exit test:* a full decision review runs from the exported report, with policy owners having reviewed a sampled queue and signed their criteria.

## Positioning

Describe it as **"a pre-registered launch review for AI features"**: it turns "the demo looked great" into "here is how often it's right, how it fails, whether it beats what users have today, what it will cost, and whether that clears the bar we agreed before we looked". Its value to a PM is leverage and credibility. It does the tedious, error-prone parts: running every option on the same questions, counting failures, computing intervals, and holding everyone to the agreed bar. That frees the PM for what only they can do. That work is choosing the questions that matter, setting the bar with the people who own the risk, reading the failures, and weighing what the numbers can't see (strategy, timing, trust, operational load). The lab's output is a *proposal and an evidence pack*, never a decision. The PM decides, records why, and owns the outcome. When the evidence and the PM's judgement disagree, the tool's job is to make that disagreement explicit and documented, not to settle it.
