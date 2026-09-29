# Using the lab as a product manager

This guide is for the person who has to decide whether an AI feature ships. It covers what the lab does for you, how to use it through a launch decision, how to read each view, and how to write the two inputs only you can write: the launch criteria and the evaluation questions.

It assumes the app is running (`make setup && make demo`; see the [README](../README.md#run-it-locally)).

## The idea in one paragraph

A demo tells you an AI feature *can* work. A launch decision needs to know how often it works, how it fails, whether it beats what users have today, and what it costs, measured on questions nobody tuned against and judged against a bar set in advance. The lab builds that evidence and applies your bar. You stay responsible for the bar, for the questions, for reviewing the grading, and for the decision.

## What stays your job

The lab is a tool for making a better decision faster. It doesn't make the decision.

| The lab does | You do |
|---|---|
| Runs every approach on every question and records the results | Decide which questions matter and what "correct" means for each |
| Applies the thresholds consistently and stores them with each run | Set the thresholds, with the people who own the risk |
| Grades automatically, with an optional model judge | Review the grades that matter, and override them when they're wrong |
| Proposes an action: pilot, do not launch yet, do not launch, insufficient evidence | Make the call, weighing what the numbers can't show: strategy, timing, user trust, operational load |
| Lists the next experiment for a failing criterion | Decide whether that experiment is worth running |
| Writes a decision memo | Own the recommendation you take to stakeholders |

If the lab says "proceed to a limited pilot" and your judgement says no, your judgement wins. Write down why: that reasoning is part of the decision record too.

## Using it through a decision

### 1. Frame the decision (before anything is built)

Write the product question as something the evidence can answer yes or no. Northstar's is in the [PRD](PRD.md#product-question):

> Does guarded RAG improve successful policy resolution enough to justify its extra latency and cost, while meeting minimum standards for citations, abstention and access control?

Three things make a question like this useful:
- **A baseline.** "Better than what?" Here it is keyword search, which is cheap, fast and predictable. An AI feature that can't beat the baseline isn't worth its cost.
- **Both sides of the trade-off.** Usefulness (correctness, lift over search) *and* cost (latency, dollars, risk).
- **A legitimate "no".** Say out loud, before the results, that "do not launch yet" is an acceptable outcome.

### 2. Set the bar with the people who own the risk

Edit [`config/launch_criteria.yaml`](../config/launch_criteria.yaml) *before* the first live run. Each criterion is a metric, a comparator and a threshold:

```yaml
- id: correctness
  label: Correct answers on answerable cases
  metric: correctness.value
  comparator: ">="
  threshold: 0.80
  unit: rate
```

How to choose the thresholds:
- **Tie each one to a user or business consequence.** "Below 80% correct, employees stop trusting it and go back to asking HR." The PRD's [success measure](PRD.md#success-measure) table gives a reason for every threshold. If you can't write the reason, you don't need the criterion yet.
- **Separate hard stops from targets.** Access safety has a threshold of zero, and any disclosure means "do not launch". Correctness at 80% is a target that a later version could reach.
- **Include cost and latency.** They're easy to forget until the bill arrives. Estimate the monthly volume and work backwards: 2,000 questions a month at $0.02 is $40.
- **Set the minimum sample size.** Below `min_sample_size`, a criterion is "insufficient evidence", never a pass.
- **Get sign-off.** For Northstar, HR and Security own the access-safety threshold. Put their names in the PRD.

Every run stores a copy of the criteria and their hash. If someone edits the file after the results are in, the Decision view flags that the current criteria differ from the ones the run was judged against.

### 3. Write the evaluation questions

The questions are where your product knowledge matters most. Each line in [`data/eval/cases.jsonl`](../data/eval/cases.jsonl) is one case:

```json
{"case_id": "S02", "question": "Who approves travel over $2,000?", "user_role": "employee",
 "category": "single_document", "split": "development", "answerability": "answerable",
 "reference_answer": "Trips over $2,000 need your department head (VP) to approve in addition to your manager.",
 "required_facts": [{"description": "Department head / VP approval required", "match_any": ["department head", "vp", "vice president"]}],
 "acceptable_document_ids": ["NS-TRV-2026"], "forbidden_document_ids": ["NS-TRV-2025"]}
```

Good sets share a few traits:
- **Cover the failure modes you're worried about, not just the happy path.** Northstar's 60 cases are 24 single-document, 12 multi-document, 8 about outdated or changed policies, 8 unanswerable and 8 role-restricted. The last three categories exist because they're where an AI assistant does damage.
- **Include near-miss unanswerable questions.** "What is the phone stipend?" when only an *internet* stipend exists. These catch invented answers better than obviously off-topic questions.
- **Use real questions when you can.** Support tickets, Slack threads and search logs beat questions written by the person who wrote the documents. Synthetic questions tend to be too clean.
- **Keep a held-out split and don't look at it while tuning.** Northstar uses 15 development and 45 held-out cases. Engineers tune prompts and thresholds with `make eval-dev`; only the final run touches the held-out set. If you tune on the test, the verdict means nothing.
- **Write required facts as the minimum a correct answer must contain.** Use aliases (`"$1,000"`, `"$1000"`) for figures. The deterministic grader is strict about figures and lenient about wording; the model judge and your review cover the rest.

### 4. Read the results

Run `make eval` (or have an engineer run it) and open the app.

**Ask** shows how each approach answers one question for one role. Use it to build intuition and to demo the product to stakeholders. It's anecdotal: never decide from it.

**Compare** is the scorecard for the held-out set. Read it like this:
- Every percentage has its count, for example 32/35. With 6 unanswerable questions, one case moves the rate by 17 points, so the count matters more than the percentage.
- Hover over a rate for its 95% interval. If the interval crosses a threshold, you don't know which side you're on yet.
- The *By category* table shows *where* an approach is weak. Search typically fails multi-document questions; basic RAG tends to invent answers to unanswerable ones.
- The quality-versus-cost chart shows the trade-off at a glance. An approach without measured cost isn't plotted, rather than being plotted at $0.

**Inspect** is where you spend the most time. Filter by category, approach and outcome, open a case, and read the question, the reference answer, each approach's answer, the grading, and the raw model output. Use it to:
- **Check the grader.** Open a sample of passes as well as failures. Case O02 shows why: a wrong answer that mentions "manager" passes the deterministic fact check.
- **Add a human review.** Mark a response correct, partially correct or incorrect with a note. Your verdict overrides the automated ones everywhere, and they're kept alongside.
- **Find the story.** "It invents a phone stipend from the internet stipend" is more persuasive in a review than "abstention quality 50%".

**Decision** applies the criteria stored with the run and proposes an action:

| Proposed action | Meaning |
|---|---|
| Proceed to a limited pilot | Every criterion passes on the held-out set |
| Do not launch yet | A fixable criterion fails; the next experiment is listed |
| Do not launch | A hard stop failed, such as a restricted-content disclosure |
| Insufficient evidence | Too few cases or measurements to judge, or the run was dominated by errors |
| Demonstration only | The run is fixture data, so there is nothing to decide on yet |

A pass whose interval crosses the threshold is labelled as such: it passed, but narrowly enough that more data could change it. Failing rows link to example cases in Inspect.

### 5. Make and communicate the decision

The [decision memo](decision_memo.md) is generated from the run (`make reports`). It holds the proposed action, the evidence table, the main failure modes with case IDs, the limits of the experiment, and what to test before a real rollout. Treat it as a first draft:
- **Add what the numbers can't show:** strategic fit, cost of delay, support load, how users will react to abstentions.
- **Be explicit about the limits.** Sixty synthetic questions justify a *pilot* decision at most, not a general launch.
- **Record your call and your reasoning,** especially when you depart from the proposed action.

### 6. Decide again when something changes

AI features drift. The model version changes, a prompt gets edited, documents are updated. Each change is a new run: `make eval` creates it without overwriting anything, and the run picker in Compare and Decision lets you compare it with the old one. Re-run the evaluation before any change ships, and treat a new failure like a failing test.

## Running a decision review

A 45-minute agenda that works well with the lab open on a shared screen:

1. **The question and the bar** (5 min): read the product question and the criteria aloud. Confirm nobody wants to change them now; if they do, that's a new run, not an edit.
2. **The scorecard** (10 min): Compare view, held-out split. Correctness lift over the baseline, then each criterion with its count and interval.
3. **Failures** (15 min): Inspect view, filtered to failures of the target approach. Walk through two or three cases in each failure category. Ask the policy owners whether the grades are right.
4. **The proposal** (10 min): Decision view. Does the group agree with the proposed action? If not, what evidence would change their mind?
5. **Next step** (5 min): the pilot plan, or the next experiment and who runs it.

## Common questions

**Why does it say "insufficient evidence" instead of pass?** A criterion needs at least `min_sample_size` cases, and latency and cost need at least 90% of cases measured. Rather than pass by default, the lab says it can't tell.

**Why is fixture mode there?** So anyone can try the workflow without an API key. AI answers in fixture mode are hand-written examples, labelled "demo" everywhere, and never presented as measurements. Search results are always real.

**Can I trust the model judge?** Partly. It is a different model from the one being graded and it records its reasoning, but it can be wrong. That's why human review exists and takes precedence.

**Is 45 held-out questions enough?** Enough to decide whether to run a pilot, not to launch to everyone. The memo's rollout tests (shadow mode on real questions, red-teaming access control, usability sessions) are the next layer of evidence.

**Can I use this for a feature other than policy Q&A?** The data and config are separate from the code, so any retrieval-based assistant works by swapping the documents, roles, questions and criteria; see [Use it for your own feature](../README.md#use-it-for-your-own-feature). Features that take actions or hold multi-turn conversations would need new approaches and grading. The [product review](product_review.md) lists that as an enhancement.
