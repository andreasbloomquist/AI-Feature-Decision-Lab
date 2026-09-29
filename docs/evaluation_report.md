# Evaluation report

> **Generated file.** Run `make reports` to regenerate from the saved runs in SQLite. Do not edit by hand.

**Status: No live evaluation yet.** Every number below comes from the fixture run. Search results are real, because search needs no model. Basic and Guarded RAG results are computed on saved example responses written to exercise the interface; they are not model measurements and must not be quoted as results. Run `make eval` with an API key to produce a live report.

## Read this first: dataset size and limits

- 60 synthetic questions (45 in the held-out set) on a 21-document synthetic corpus. Enough to demonstrate a decision process, not to establish production reliability.
- Small denominators: 35 answerable, 6 unanswerable and 4 access-denied cases, so one case moves a rate by 3 to 25 points. Confidence intervals are shown for that reason.
- Questions were written by the same author as the documents, so they are cleaner and closer to the document wording than real employee questions.
- Deterministic fact matching is strict about figures and lenient about wording; the model judge is itself a model and can be wrong. Human review is the tie-breaker.
- Latency was measured from one machine and region at low concurrency; production latency and cost at peak volume are untested.
- Roles are selected in the UI, not authenticated. Access control is enforced and tested in the backend (retrieval, model context, citations, previews), not against a real identity provider.
- Cost is estimated from recorded tokens and the editable price table in `config/pricing.yaml`; missing usage is reported as unavailable, never as zero.

## Run configuration

| Field | Value |
|---|---|
| Run | `fixture-20260929T190305Z-a026` (fixture) |
| Created | 2026-09-29T19:03:05Z |
| Corpus | `corpus-123344c244d4` |
| Dataset | `northstar-policy-qa@1.0.0+6e15a5334bd6` |
| Prompts | search: `search-v1`, basic_rag: `basic-rag-v1`, guarded_rag: `guarded-rag-v1`, judge: `judge-v1` |
| Model | `fixture (not a model)` (effort: None) |
| Judge | none |

## Held-out results (used for the decision)

| Measure | Search | Basic RAG | Guarded RAG |
|---|---|---|---|
| Answer correctness (answerable) | 62.9% (22/35; 95% CI 46.3%–76.8%) | 97.1% (34/35; 95% CI 85.5%–99.5%) | 91.4% (32/35; 95% CI 77.6%–97.0%) |
| Deterministic fact match | 62.9% (22/35; 95% CI 46.3%–76.8%) | 97.1% (34/35; 95% CI 85.5%–99.5%) | 91.4% (32/35; 95% CI 77.6%–97.0%) |
| Citation validity (answered) | 84.2% (32/38; 95% CI 69.6%–92.6%) | 86.5% (32/37; 95% CI 72.0%–94.1%) | 100.0% (32/32; 95% CI 89.3%–100.0%) |
| Abstention quality (unanswerable) | 50.0% (3/6; 95% CI 18.8%–81.2%) | 50.0% (3/6; 95% CI 18.8%–81.2%) | 100.0% (6/6; 95% CI 61.0%–100.0%) |
| Access-denied handling | 75.0% (3/4; 95% CI 30.1%–95.4%) | 100.0% (4/4; 95% CI 51.0%–100.0%) | 100.0% (4/4; 95% CI 51.0%–100.0%) |
| Restricted disclosures | 0 in 45 cases | 0 in 45 cases | 0 in 45 cases |
| Latency p50 / p95 | <1 ms / <1 ms (n=45) | not measured (fixture) | not measured (fixture) |
| Model cost | $0 per question; $0 total (n=45) | unavailable (45 of 45 without token usage) | unavailable (45 of 45 without token usage) |
| Errors | 0 of 45 | 1 of 45 | 2 of 45 (1 provider/runtime, 1 withheld by the guard) |

**By category** (correct answers for answerable cases; correct abstention or safe decline otherwise):

| Category | n | Search | Basic RAG | Guarded RAG |
|---|---|---|---|---|
| Single document | 18 | 16/18 | 17/18 | 17/18 |
| Multiple documents | 9 | 1/9 | 9/9 | 7/9 |
| Outdated / changed policy | 6 | 4/6 | 6/6 | 6/6 |
| Unanswerable | 6 | 3/6 | 3/6 | 6/6 |
| Role-based access | 6 | 4/6 | 6/6 | 6/6 |

## Development results

| Measure | Search | Basic RAG | Guarded RAG |
|---|---|---|---|
| Answer correctness (answerable) | 58.3% (7/12; 95% CI 31.9%–80.7%) | 100.0% (12/12; 95% CI 75.8%–100.0%) | 100.0% (12/12; 95% CI 75.8%–100.0%) |
| Deterministic fact match | 58.3% (7/12; 95% CI 31.9%–80.7%) | 100.0% (12/12; 95% CI 75.8%–100.0%) | 100.0% (12/12; 95% CI 75.8%–100.0%) |
| Citation validity (answered) | 92.3% (12/13; 95% CI 66.7%–98.6%) | 92.3% (12/13; 95% CI 66.7%–98.6%) | 100.0% (12/12; 95% CI 75.8%–100.0%) |
| Abstention quality (unanswerable) | 50.0% (1/2; 95% CI 9.4%–90.5%) | 50.0% (1/2; 95% CI 9.4%–90.5%) | 100.0% (2/2; 95% CI 34.2%–100.0%) |
| Access-denied handling | 100.0% (1/1; 95% CI 20.6%–100.0%) | 100.0% (1/1; 95% CI 20.6%–100.0%) | 100.0% (1/1; 95% CI 20.6%–100.0%) |
| Restricted disclosures | 0 in 15 cases | 0 in 15 cases | 0 in 15 cases |
| Latency p50 / p95 | <1 ms / 3 ms (n=15) | not measured (fixture) | not measured (fixture) |
| Model cost | $0 per question; $0 total (n=15) | unavailable (15 of 15 without token usage) | $0 per question; $0 total (n=1, 14 without usage) |
| Errors | 0 of 15 | 0 of 15 | 0 of 15 |

**By category** (correct answers for answerable cases; correct abstention or safe decline otherwise):

| Category | n | Search | Basic RAG | Guarded RAG |
|---|---|---|---|---|
| Single document | 6 | 4/6 | 6/6 | 6/6 |
| Multiple documents | 3 | 1/3 | 3/3 | 3/3 |
| Outdated / changed policy | 2 | 1/2 | 2/2 | 2/2 |
| Unanswerable | 2 | 1/2 | 1/2 | 2/2 |
| Role-based access | 2 | 2/2 | 2/2 | 2/2 |

## Held-out failures

| Case | Approach | Category | Outcome | Detail |
|---|---|---|---|---|
| S21 | Basic RAG | Single document | error | timeout: model request timed out (simulated in fixture) |
| U04 | Basic RAG | Unanswerable | invented_answer | Yes. Employees can take extended time off after five years; request it in the People porta |
| U06 | Basic RAG | Unanswerable | invented_answer | Relocation costs follow the Travel Policy: flights are booked in TripDesk and hotels are c |
| U07 | Basic RAG | Unanswerable | invented_answer | US employees have flexible paid time off, so jury duty can be taken as paid time off. [NS- |
| M04 | Guarded RAG | Multiple documents | unnecessary_abstention | model_abstained |
| M10 | Guarded RAG | Multiple documents | error | citation_validation_failed: NS-SEC-001 (not_in_context) |
| S19 | Guarded RAG | Single document | error | timeout: model request timed out (simulated in fixture) |
| M04 | Search | Multiple documents | incorrect | Travel to a conference follows the Travel Policy and is paid from your team's travel budge |
| M06 | Search | Multiple documents | unnecessary_abstention | best BM25 score 4.59 is below the threshold 5.0 |
| M07 | Search | Multiple documents | partial | Submit expenses in Ledgerly, Northstar's expense tool, within 30 days of the date the expe |
| M08 | Search | Multiple documents | partial | UK employees may carry up to 5 unused days of annual leave into the next holiday year. [NS |
| M09 | Search | Multiple documents | partial | Contractors, interns on assignments of less than 3 months, and employees assigned to an of |
| M10 | Search | Multiple documents | partial | You may take your Northstar laptop abroad. [NS-SEC-002#4] |
| M11 | Search | Multiple documents | partial | In the UK the cap is £180 per night, or £240 per night in London. Caps exclude taxes. [NS- |
| M12 | Search | Multiple documents | partial | In high-cost US cities (New York, San Francisco, Boston and Seattle) the cap is $325 per n |
| O06 | Search | Outdated / changed policy | partial | Contractors, interns on assignments of less than 3 months, and employees assigned to an of |
| O07 | Search | Outdated / changed policy | incorrect | This policy explains how long Northstar keeps records about employees and candidates. [NS- |
| R03 | Search | Role-based access | answered_without_access | Every client entertainment expense needs an itemized receipt, regardless of amount, and a  |
| R08 | Search | Role-based access | partial | Unused privileged accounts are disabled after 30 days. [NS-ADM-001#2] |
| S12 | Search | Single document | incorrect | UK employees may carry up to 5 unused days of annual leave into the next holiday year. Car |
| S24 | Search | Single document | incorrect | Give at least 2 weeks' notice for absences of 5 days or more. [NS-PTO-001#5] |
| U06 | Search | Unanswerable | invented_answer | In high-cost US cities (New York, San Francisco, Boston and Seattle) the cap is $325 per n |
| U07 | Search | Unanswerable | invented_answer | US employees have flexible paid time off. Employees are encouraged to take at least 15 day |
| U08 | Search | Unanswerable | invented_answer | Northstar pays 20 weeks at full pay, followed by statutory pay for the remaining paid week |

## Scoring rubric

- **Deterministic grader** (always runs): response status; required facts present, matched by aliases on normalized text with word boundaries; citations exist, are authorized for the role, are active, were in the model's context, and include an acceptable source; restricted document IDs, restricted facts (from `data/eval/restricted_markers.yaml` and each case's `forbidden_facts`) and 8-word verbatim spans from restricted passages in any answer shown to an unauthorized role.
- **Model judge** (optional, live runs): grades answered, answerable cases as correct, partially correct or incorrect against the reference answer and required facts, checks citation support, and stores a rationale. Its verdicts are labeled model-judged.
- **Human review**: a reviewer can mark any answer correct, partially correct or incorrect with a note. The automated grade and judge verdict are kept. Final label priority: human > model judge > deterministic.
- **Denominators**: correctness over all answerable cases (abstentions and errors count as not correct); citation validity over answered cases; abstention quality over unanswerable cases; disclosures counted over all cases.
- **Latency**: nearest-rank median and 95th percentile of wall-clock time per question.

## Search threshold and retrieval floor (development split only)

Search abstains when the best BM25 score is below **5.0**; guarded RAG skips the model when it is below **2.0**. Both values were chosen by looking at the development split only:

| Case | Answerability | Best BM25 score | Search | Guarded floor |
|---|---|---|---|---|
| S01 | answerable | 13.84 | answer | call model |
| S02 | answerable | 8.19 | answer | call model |
| S03 | answerable | 15.60 | answer | call model |
| S04 | answerable | 24.89 | answer | call model |
| S05 | answerable | 15.36 | answer | call model |
| S06 | answerable | 8.78 | answer | call model |
| M01 | answerable | 12.70 | answer | call model |
| M02 | answerable | 10.93 | answer | call model |
| M03 | answerable | 12.93 | answer | call model |
| O01 | answerable | 6.28 | answer | call model |
| O02 | answerable | 6.33 | answer | call model |
| U01 | unanswerable | 1.79 | abstain | abstain |
| U02 | unanswerable | 7.91 | answer | call model |
| R01 | access_denied | 3.37 | abstain | call model |
| R02 | answerable | 22.17 | answer | call model |

The held-out set was not used to choose either value.
