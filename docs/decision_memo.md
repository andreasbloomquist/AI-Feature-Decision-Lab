# Decision memo: AI policy assistant

> **Generated file.** Run `make reports` to regenerate. Criteria: `config/launch_criteria.yaml`.

## Status: no live evaluation yet

There are no measured model results, so this memo makes **no launch recommendation**. Below is (1) the template the live memo follows and (2) an example filled in from fixture data only.

## 1. Template

- **Proposed action:** one of *proceed to a limited pilot*, *do not launch yet*, *do not launch*, or *insufficient evidence*, as computed from the launch criteria stored with the run.
- **Evidence:** held-out criteria table with counts and intervals; lift over search; latency and cost.
- **Major failure modes:** held-out failures for guarded RAG grouped by type, with case IDs.
- **Limits of the experiment:** dataset size, synthetic questions, judge reliability, single-machine latency.
- **Next test:** the experiment that addresses the first failing criterion, run on development data, then confirmed on a fresh held-out set.

## 2. Example based only on fixture data

> **Demonstration only.** Guarded and basic RAG responses here are saved examples written to exercise the interface, not model outputs. Nothing in this section is evidence about any model.

### Proposed action: Demonstration only: fixture data is not evidence

These results come from saved example responses written to exercise the interface. They are not model measurements and cannot support a launch decision. Run a live evaluation.

### Evidence (held-out set)

| Criterion | Threshold | Measured | State (demo only) |
|---|---|---|---|
| No unauthorized disclosure | <= 0 | 0 (n=45) | Pass |
| Correct answers on answerable cases | >= 80.0% | 91.4% (32/35) | Pass (interval crosses threshold) |
| Valid citations among answered cases | >= 95.0% | 100.0% (32/32) | Pass (interval crosses threshold) |
| Correct abstention on unanswerable cases | >= 90.0% | 100.0% (6/6) | Pass (interval crosses threshold) |
| 95th-percentile latency | <= 6.00 s | not measured | Insufficient evidence — not measured: fixture responses have no latency or token usage |
| Average model cost per question | <= $0.0200 | not measured | Insufficient evidence — not measured: fixture responses have no latency or token usage |

All approaches on the same criteria:

| Criterion | Search | Basic RAG | Guarded RAG |
|---|---|---|---|
| No unauthorized disclosure | Pass | Pass | Pass |
| Correct answers on answerable cases | Fail | Pass | Pass |
| Valid citations among answered cases | Fail | Fail | Pass |
| Correct abstention on unanswerable cases | Fail | Fail | Pass |
| 95th-percentile latency | Pass | Insufficient | Insufficient |
| Average model cost per question | Pass | Insufficient | Insufficient |

### Major failure modes (Guarded RAG, held-out)

- **Error (timeout, validation or provider)**: 2 case(s), e.g. M10, S19
- **Abstained when the policy did answer**: 1 case(s), e.g. M04

### Limits of this experiment

- 60 synthetic questions (45 in the held-out set) on a 21-document synthetic corpus. Enough to demonstrate a decision process, not to establish production reliability.
- Small denominators: 35 answerable, 6 unanswerable and 4 access-denied cases, so one case moves a rate by 3 to 25 points. Confidence intervals are shown for that reason.
- Questions were written by the same author as the documents, so they are cleaner and closer to the document wording than real employee questions.
- Deterministic fact matching is strict about figures and lenient about wording; the model judge is itself a model and can be wrong. Human review is the tie-breaker.
- Latency was measured from one machine and region at low concurrency; production latency and cost at peak volume are untested.
- Roles are selected in the UI, not authenticated. Access control is enforced and tested in the backend (retrieval, model context, citations, previews), not against a real identity provider.

### What we would test before a real rollout

1. Shadow mode: run guarded RAG on real employee questions (with consent) for 2 weeks without showing answers, and label a random sample of 200.
2. Red-team access control with HR and Finance: at least 50 adversarial prompts per restricted document, including prompt-injection text placed inside policy documents.
3. Freshness: confirm the policy sync picks up a superseded document within one business day, and that stale answers disappear.
4. Usability: 8 to 10 employee sessions to check whether people open citations and understand abstentions, and what they do next.
5. Operations: define who owns wrong answers, the escalation path to policy owners, and a weekly review of abstained questions as a content-gap backlog.
6. Load and cost: measure p95 latency and spend at expected peak volume, with a hard monthly budget alert.
