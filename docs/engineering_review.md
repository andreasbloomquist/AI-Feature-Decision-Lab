# Engineering review

A principal-engineer review of the whole repository, done after the first complete build. It records what was found, how each problem was fixed, and which test now guards against it. It also lists what is still open.

## How the review was done

- **Independent reviewers.** Two reviewers read the code without context from the author. One covered backend correctness, security and tests. The other covered the frontend, documentation, and whether the docs matched the code.
- **Author's own pass.** The author reviewed alongside them, looking for layering and duplication problems.
- **Automated tools.** `ruff` and ESLint (with the React hooks rules) were added and run across the codebase.
- **Verification.** Every finding below was reproduced first, or confirmed by reading the code. Each fix was checked with `make check` and in a real browser.

**Before and after:**

| | Before the review | After the review |
|---|---|---|
| Backend tests | 56 | 97 |
| Frontend tests | 11 | 20 |
| Linters | none | `ruff` (lint + format), ESLint, strict TypeScript |
| CI | tests only | lint, tests on Python 3.10 and 3.12, frontend checks, production build |
| Lint suppressions | 4 | 0 |

## Findings and fixes

Severity key: **Critical** means a secret or restricted data can leak. **High** means wrong results or a broken core path. **Medium** means a correctness risk or a maintainability problem a senior reviewer would block on. **Low** means polish.

### Security and access control

| # | Severity | Finding | Fix | Regression test |
|---|---|---|---|---|
| 1 | Critical | **Path traversal.** The route that serves the built UI joined the URL path to `frontend/dist` without resolving it. `GET /..%2F..%2F.env` returned the API key file. | `static_file()` resolves the path and refuses anything outside the build folder. | `test_rejects_traversal_absolute_directories_and_missing`, `test_encoded_traversal_over_http_returns_index_not_secret` |
| 2 | Critical | **Basic RAG leaked restricted IDs.** The `[NS-HR-001#2]` marker was removed from the answer, but the same ID was still sent to the browser in the citation list and the warning text. The existing test only checked the answer text. | An unauthorized citation's ID becomes `[restricted]`. Any mention of a restricted ID anywhere in the answer is redacted. The public response reports these as "unavailable". | `test_basic_rag_never_sends_restricted_id_to_the_browser`, `test_ask_endpoint_leaks_nothing_for_restricted_question` |
| 3 | High | **Guarded RAG's validation could be bypassed.** A lowercase marker (`[ns-hr-001#2]`), a malformed one (`[NS-HR-001 §2]`), or a plain-text mention got through as a valid answer. The grader's disclosure check was also case-sensitive. | IDs are matched regardless of case everywhere. Guarded RAG withholds any answer with a malformed marker, or one that names a restricted document anywhere. The first version of this fix also rejected harmless prose mentions of accessible documents (for example, "replaces NS-TRV-2025"), which would have withheld correct change answers; the final rule targets restricted documents only. The grader now also checks warnings and error text. | `test_guarded_rag_withholds_any_reference_to_restricted_document` (3 cases), `test_guarded_rag_may_name_an_accessible_superseded_policy_in_prose`, `test_disclosure_detection_is_case_insensitive_and_covers_warnings` |
| 4 | Medium | **Existence oracle.** A restricted document returned 403 and a missing one returned 404, so a user could probe for restricted IDs. | Both return the same 404 body. | `test_preview_endpoint_enforces_role` |
| 5 | Medium | **The secret-leak test had gaps.** It skipped `/api/ask`, the case detail endpoint and the exported run files. | The test now covers every endpoint, the SQLite file and a JSON export. | `test_no_secret_in_any_response_database_or_export` |

### Evaluation correctness

| # | Severity | Finding | Fix | Regression test |
|---|---|---|---|---|
| 6 | High | **A run could crash and stay "running" forever.** Only answering was wrapped in error handling; grading and storage were not. Passing the same approach twice raised a uniqueness error mid-run. | Answering and grading are isolated per case. Failures outside a case mark the run `failed`. Duplicate approach names are removed. The dataset loader rejects unknown roles, splits, categories and duplicate IDs. | `test_grading_failure_is_recorded_and_run_completes`, `test_storage_failure_marks_run_failed_instead_of_running`, `test_duplicate_approaches_are_run_once`, `test_dataset_validation_rejects_*` |
| 7 | High | **Past verdicts could change after the fact.** Decisions read today's `launch_criteria.yaml`, so editing a threshold silently changed an old run's verdict. Removing a case from the dataset crashed old runs. | Every run stores the criteria, their hash and the dataset cases. Decisions and metrics use the stored copies, and the UI flags when the criteria file has changed since. | `test_decision_uses_criteria_stored_with_the_run`, `test_run_is_graded_against_its_own_dataset_snapshot` |
| 8 | High | **A development-only run hid the real result.** `make eval-dev` created the newest live run, which had no held-out cases, so Compare and Decision went blank. | "Latest run" now means the newest live run that covers the held-out split, in the backend and the UI alike. The UI explains when a run lacks the selected split. | `prefers the newest live run that covers the held-out split, skipping dev-only runs` (frontend) |
| 9 | Medium | **One transient error blocked the cost verdict.** A single timeout with no token usage made cost "insufficient evidence" for the whole run. | Latency and cost are judged on the measured cases when at least 90% of cases are measured (`min_measurement_coverage`). Missing usage is still never counted as $0. | `test_one_unmeasured_case_does_not_block_cost_and_latency`, `test_cost_and_latency_need_minimum_measurement_coverage` |
| 10 | Low | **Wrong passage for document-level citations.** Passage IDs were sorted as strings, so `#10` came before `#2`. | Sorted numerically. | `test_document_level_citation_uses_numeric_passage_order` |

### Frontend

| # | Severity | Finding | Fix | Regression test |
|---|---|---|---|---|
| 11 | High | **No error handling, and out-of-order responses.** Most requests had no error handling, so a stale deep link showed "Loading…" forever. Quickly switching runs, filters or questions could show data for the wrong selection. | A shared `useAsync` hook exposes loading and error state, offers a retry, and ignores any response that arrives after a newer request started. Ask tracks its latest request, and the review form shows save errors. | `shows an error instead of loading forever` |
| 12 | Medium | **Keyboard and screen-reader gaps.** Inspect rows worked only by mouse. The source drawer didn't move focus or trap Tab. Status dots relied on colour alone. Chart points had no labels. | Rows contain real links. The drawer is a modal dialog that moves focus in, traps Tab, handles Escape and restores focus. Dots have text for screen readers, and chart points have labels. | `explains unavailable documents, moves focus in, and closes on Escape`; keyboard flow checked in a browser |
| 13 | Medium | **Values hardcoded that the backend already provides.** Chart thresholds, split sizes and the "succeeded" rule were duplicated in the UI. | Thresholds come from `/api/config`, and split sizes from the run. The backend sends a `succeeded` flag computed by the same function the reports use. | `never plots missing, partial or demo cost` |
| 14 | Medium | **Deep links lost state.** Changing a filter dropped the selected approach. "Try this question in Ask" didn't carry the question. Compare's split wasn't in the URL. | Every Inspect link keeps all parameters. Ask reads `q` and `role` from the URL. The split is part of the Compare URL. | `keeps every filter in row links, so deep links survive navigation` |
| 15 | Medium | **Lint suppressions with no linter.** Four `eslint-disable` comments hid real stale-closure bugs. | ESLint added. The suppressions were removed and the dependencies fixed; `useEffectEvent` replaces the one legitimate case. | `make lint` in CI |

### Code quality

| # | Severity | Finding | Fix |
|---|---|---|---|
| 16 | Medium | **Duplicated logic.** "Load a run's rows with their cases" existed in 4 places. "Pick the latest runs" existed in 2. The citation-validity rule existed in 2. The model call existed in both RAG approaches. BM25 defaults appeared in 4 places, and the judge prompt path in 3. | One `results.py` read layer, one `citation_is_valid()`, one `Approach.generate()`, and named constants. |
| 17 | Medium | **Layering.** The report generator imported the web layer to seed the fixture run. | `ensure_fixture_run` moved into the evaluation runner. |
| 18 | Medium | **Hardcoded dataset numbers contradicted each other.** The memo said "3 to 17 points" and the report said "3 to 25". | Limitations are computed from the dataset, and both documents use the same function. |
| 19 | Low | **Inefficiency.** Fetching one response loaded the whole run. Restricted passage n-grams were rebuilt for every graded response. | A direct query, and n-grams cached per document. |
| 20 | Low | **Dead code.** An unused parameter, an unused constant, an unused result field, and a `sys.path` hack in tests. | Removed; pytest now uses `pythonpath`. |
| 21 | Low | **SQLite robustness.** Foreign keys were not enforced, and there was no busy timeout for concurrent CLI and server use. | Foreign keys, WAL mode and a busy timeout on every connection. |

### Documentation

| # | Finding | Fix |
|---|---|---|
| 22 | The README said Node 20+, but the test tools need Node 22.22+. The Python 3.10 minimum was never tested. | README corrected, with `engines` in `package.json`. CI now runs Python 3.10 and 3.12, and the suite was run locally on 3.10. |
| 23 | The docs claimed criteria were "registered before held-out results were viewed", which the git history can't prove. | Reworded to what is verifiable: written before any live evaluation existed, and stored with every run. |
| 24 | The README and demo script presented fixture behaviour ("Basic RAG invents answers") as findings. | Reframed as hypotheses and illustrations. Screenshots are captioned as demo data. |
| 25 | The decision log cited "the spec", which isn't in the repo. | The requirements are now listed in the [PRD](PRD.md#requirements) (R1 to R10), and the decision log cites them by number. |
| 26 | The README said search citations "can't be invalid", but the report shows search at 84% citation validity. | Clarified: a search citation always points at a real passage, but the passage may come from the wrong policy. |

## Known limitations and next steps

These are open by choice, and are listed so a reader doesn't have to find them:

1. **No live evaluation has been run.** The decision is "no live evaluation yet" until someone runs `make eval` with a key. Everything is built so that run can say "do not launch".
2. **The fixture responses were written by hand.** They exercise the pipeline and the UI, but they are not evidence. See [decision 13](decisions.md#13-fixture-mode-saved-example-outputs-replayed-through-the-real-pipeline).
3. **Deterministic fact matching is lenient about wording.** Case O02 shows this: a wrong answer that mentions "manager" passes the fact check. The model judge and human review exist to catch it, and O02 is used in the demo to show it.
4. **No static type checking in CI.** Public functions have type hints, but no mypy or pyright gate runs. That is the next quality step (decision 24).
5. **The browser path is not tested in CI.** The four-view path was verified by hand with Playwright, and component and view tests run in CI. A small Playwright suite in CI is the next test investment (decision 21).
6. **Roles are simulated.** Access control is enforced and tested in the backend, but not against a real identity provider (see the [PRD](PRD.md#scope), excluded scope).
