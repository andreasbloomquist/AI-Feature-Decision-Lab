# Technical decisions

This log records the architecture, tool and library choices behind the lab, the alternatives that were considered, and why they were not used.

These choices are not the best for every project. They are the best fit for this one, which has five constraints:

1. **It has to run on a reviewer's laptop in about two minutes with no API key and no external services.** The reviewer clones the repo, runs `make setup` and `make demo`, and the app works.
2. **The comparison has to be fair and easy to inspect.** All three approaches share the same retrieval, access control and response object, so any difference in results comes from the approach itself.
3. **Every number has to be traceable.** A reviewer should be able to follow any metric back to a case, a response, a prompt version and a config file.
4. **The scale is small.** There are 21 documents, 105 passages and 60 questions.
5. **It is a portfolio piece, so the code must be short enough for a reviewer to read.** A few hundred lines of our own code are preferable to a framework whose behaviour has to be taken on trust.

The [project requirements](PRD.md#requirements) fixed some choices: React, TypeScript and Vite for the frontend, Python and FastAPI for the backend, SQLite for storage, Markdown for policy documents, BM25 or an equivalent for keyword retrieval, and one real LLM provider through its official SDK. For those, this log explains how each one is used and what it would take to change it. For everything else, it explains why the chosen option was picked.

Each entry ends with **Revisit when**, the condition under which the decision should change.

## Index

| # | Area | Decision |
|---|---|---|
| 1 | Overall shape | One Python process serves the API and the built UI |
| 2 | Backend framework | FastAPI with Pydantic, served by Uvicorn |
| 3 | Persistence | SQLite through the standard library, plus a JSON export per run |
| 4 | Document format | Markdown with YAML front matter, one passage per `##` section |
| 5 | Retrieval | Our own BM25 implementation, no embeddings |
| 6 | Access control | A separate index per role, built after filtering |
| 7 | Superseded policies | Removed from retrieval; changes answered from the active policy |
| 8 | LLM provider and SDK | Anthropic, through the official `anthropic` Python SDK |
| 9 | Models and settings | `claude-opus-5-5` at low effort for answers, `claude-sonnet-5-5` for the judge, all configurable |
| 10 | LLM framework | None: no LangChain, LlamaIndex or LiteLLM |
| 11 | Output and citation format | Text contract with inline passage IDs, validated after generation |
| 12 | Refusal fallbacks and retries | Fallback to another model off; one SDK retry; no repair call |
| 13 | Fixture mode | Saved example outputs replayed through the real pipeline |
| 14 | Grading | Deterministic grader first, optional model judge, human review on top |
| 15 | Evaluation tooling | Our own runner rather than an eval framework or SaaS product |
| 16 | Statistics | Wilson intervals and nearest-rank percentiles |
| 17 | Configuration | Versioned YAML and Markdown files in git; secrets only in the environment |
| 18 | Frontend libraries | React only: no UI kit, router, state or data-fetching library |
| 19 | Charting | A hand-written SVG chart instead of a chart library |
| 20 | Styling | One plain CSS file with design tokens |
| 21 | Testing | pytest, Vitest, Testing Library, and a local fake of the provider API |
| 22 | Developer workflow | Makefile and virtualenv, no Docker; GitHub Actions for CI |
| 23 | Screenshots | Playwright, run once and not added as a project dependency |
| 24 | Code-quality tooling | ruff, ESLint, strict TypeScript, all enforced in CI |

---

## 1. Overall shape: one process serves the API and the built UI

**Decision.** In demo mode, FastAPI serves both `/api/*` and the compiled React app from `frontend/dist`, so `make demo` starts a single process on one port. During development, Vite's dev server runs on port 5173 and forwards `/api` requests to the backend on port 8000.

**Why.** It is the smallest setup that still separates frontend and backend code. The reviewer runs one command, opens one URL, and doesn't need CORS settings or a second terminal.

**Alternatives considered.**

| Option | Why not |
|---|---|
| Separate frontend and backend deployments | Adds a second process, CORS configuration and more setup steps, with no benefit for a local demo. |
| A full-stack framework such as Next.js, Remix or SvelteKit | The requirements call for a Python backend (R1). Running a Node server as well as Python would add a runtime that nothing needs. |
| Server-rendered templates (Jinja plus HTMX) | Fine for forms. It is weaker for interactive views like side-by-side answers, filters and the source drawer, and the requirements call for React (R1). |
| Streamlit or Gradio | Fastest way to demo a model, but the result looks like a notebook rather than a small internal product, and Inspect-style views and routing are hard to control. |

**Revisit when** the lab is deployed for other people to use. At that point the UI should be served from a CDN or static host, with the API behind authentication.

## 2. Backend framework: FastAPI with Pydantic, served by Uvicorn

**Decision.** FastAPI 0.141, Pydantic 2 for request validation, and Uvicorn as the server. App startup uses FastAPI's `lifespan` handler to seed the fixture run.

**Why.** FastAPI is required (R1), and it suits this project. Request models such as `AskRequest` and `ReviewRequest` reject bad input (unknown approach, invalid verdict, a 600-character question) before our code runs. The endpoints are plain functions that are easy to test with `TestClient`. It also produces an OpenAPI schema at `/docs` for free.

**Alternatives considered.**

| Option | Why not |
|---|---|
| Flask | Would work, but request validation and schema docs would have to be added by hand. |
| Django with Django REST Framework | Its ORM, admin site and migrations are heavy for five tables and about a dozen endpoints. |
| Litestar or Starlette alone | Capable, but FastAPI is more widely known, which matters for a portfolio reviewer. |
| A Node backend (Express, Fastify) | Python is required (R1). Python is also where the LLM, evaluation and statistics code sits most naturally. |

**Revisit when** requests need to run concurrently at scale. The model calls are synchronous because the SDK's sync client is simple and the evaluation runner parallelises with threads. A high-traffic service would switch to `AsyncAnthropic` and async endpoints.

## 3. Persistence: SQLite through the standard library, plus a JSON export per run

**Decision.** SQLite accessed with Python's built-in `sqlite3` module (`backend/app/db.py`). There are five tables: `runs`, `responses`, `reviews`, `ask_log` and `configuration`. Responses, grades and configuration snapshots are stored as JSON text. Each finished run is also written to `results/runs/<run_id>.json`.

**Why.**
- SQLite is required (R1). It needs no server and is a single file you can delete with `make clean-db`.
- Using the standard library instead of an ORM keeps the schema visible in one place: the `SCHEMA` string.
- Storing responses as JSON documents means a new field on the response object doesn't need a migration, while the columns we filter on (`run_id`, `case_id`, `approach`) remain real columns.
- The JSON export means a live run can be committed to git and read without the app.
- Runs are only ever inserted, never updated in place, and reviews live in their own table. That is how "re-running creates a new run" and "human review preserves the automated score" are enforced.
- Each connection enables foreign keys, write-ahead logging and a busy timeout, so the CLI runner and the API server can use the same file at the same time.
- Reads go through one module, `results.py`, which joins responses to their cases and computes metrics. The API, the decision logic and the report generator all use it, so a response row has the same shape everywhere.

**Alternatives considered.**

| Option | Why not |
|---|---|
| Postgres | Needs a server or Docker, which breaks the two-minute setup. Nothing here needs concurrent writers or row-level locking. |
| SQLAlchemy or SQLModel | An extra layer for five tables and a handful of queries. Readers would learn the ORM before they could read the storage code. |
| DuckDB | Excellent for analysing results, but the app mostly makes small transactional writes (one review, one response), which is SQLite's strength. |
| JSON or CSV files only | Easy to read, but filtering, joining reviews to responses and making concurrent writes from worker threads would all have to be written by hand. |
| A hosted experiment tracker (Weights & Biases, MLflow) | Adds an account or server, and SQLite is required (R1). |

**Revisit when** several people use the tool at once or runs grow to tens of thousands of rows. At that point, move to Postgres, add Alembic migrations, and promote frequently filtered JSON fields such as `outcome` and `error_type` to columns.

## 4. Document format: Markdown with YAML front matter, one passage per `##` section

**Decision.** Each policy is a `.md` file whose front matter holds `document_id`, `title`, `owner`, `effective_date`, `status`, `superseded_by`, `access_groups` and `country`. The loader rejects files that are missing required fields or mark a document superseded without saying what replaced it. Each `##` section becomes a passage with an ID such as `NS-TRV-2026#3`.

**Why.** Markdown is what policy owners already write, and it is required (R1). Splitting by section gives passages that mean something to a person ("Trip approvals") and are stable to cite. A reviewer clicking a citation lands on a heading they recognise, not an arbitrary 512-token slice.

**Alternatives considered.**

| Option | Why not |
|---|---|
| Fixed-size token chunks with overlap | Standard for long documents, but these policies are short. Fixed chunks would cut rules mid-sentence and give passages no readable name. |
| Sentence-level chunks | Too small. Most answers need two or three related sentences, such as a threshold and its exception. |
| Whole documents as the retrieval unit | Too coarse to cite precisely, and it wastes model context. |
| A document store or CMS (Notion, Confluence) | Adds network dependencies and credentials; ingestion from those systems is out of scope in the PRD. |

**Revisit when** documents get long (more than about 1,500 words per section). Then split large sections further while keeping the heading in each piece.

## 5. Retrieval: our own BM25 implementation, no embeddings

**Decision.** A roughly 100-line BM25 implementation in `backend/app/retrieval.py`, with settings k1 = 1.5 and b = 0.75, a small stop-word list, light plural stemming, and currency-aware tokens so `$2,000` becomes `$2000`. The document title and section heading are indexed along with the passage text. All three approaches use the same retriever.

**Why.**
- BM25 or an equivalent local implementation is required (R1).
- Writing it ourselves makes two things possible that matter here. First, each role's index is built only from documents that role can read (decision 6), so term statistics are never computed over restricted text. Second, a reviewer can read exactly how scores are calculated, and the search threshold in `config/approaches/search.yaml` refers to scores they can reproduce.
- With 105 passages, search takes well under a millisecond, so there is nothing to optimise.
- Using identical retrieval for all three approaches keeps the comparison fair: any difference comes from generation and guarding, not retrieval.

**Alternatives considered.**

| Option | Why not |
|---|---|
| `rank_bm25` (PyPI) | Would work, but has its own tokenisation assumptions. Replacing about 60 lines of scoring with a dependency saves little. |
| Elasticsearch or OpenSearch | Production-grade BM25 with document-level security, but needs a JVM service, which breaks local setup. The right choice at a real company with thousands of documents. |
| Tantivy, Whoosh or SQLite FTS5 | Solid local full-text engines. FTS5 was the closest runner-up. Our own implementation gives direct control over per-role statistics and tokenisation with no extra dependency. |
| Embeddings with a vector store (FAISS, Chroma, pgvector, Pinecone, Weaviate, Qdrant) | Better at paraphrase ("WFH gear" matching "home office equipment"). It would need an embedding model: either a hosted API, which breaks keyless fixture mode, or a local model download of hundreds of MB. It is also harder to reason about the score threshold. |
| Hybrid retrieval (BM25 plus embeddings with rank fusion) | Probably the best production option. It is the first "next experiment" the decision memo proposes if correctness fails because the right passage wasn't retrieved. |
| Re-ranking with a cross-encoder or LLM | Adds latency and cost to every question and hides whether gains come from retrieval or generation. |

**Known weaknesses of this choice.** The stemmer only strips plurals, so "reimburse" and "reimbursement" don't match, and there is no synonym handling. Search will under-answer paraphrased questions, and the RAG approaches inherit the same limit. This is intentional: it keeps the comparison about generation. It is also listed as a limitation.

**Revisit when** real employee questions come in, since they paraphrase more than the synthetic set, or the corpus grows past a few thousand passages.

## 6. Access control: a separate index per role, built after filtering

**Decision.** Four roles (`employee`, `hr`, `finance`, `admin`) map to access groups. `Retriever.index_for(role)` builds a BM25 index containing only the active documents that role may read. The same check is applied again at three more points:
- **Citation validation:** an unauthorized citation is invalid. Its ID is replaced with `[restricted]`, and any mention of a restricted ID in the answer text is redacted, matching IDs regardless of case.
- **Source previews:** `GET /api/documents/{id}?role=` returns the same 404 for a restricted document as for one that doesn't exist, so a user can't probe for restricted IDs. In the Ask response, citations to a restricted or nonexistent document both show the reason "unavailable".
- **Grading:** leaked document IDs, known restricted facts, and 8-word verbatim passages are counted as disclosures.

When a restricted question is asked, the assistant says it couldn't find the answer in the policies available to the user. It doesn't say "that's in an HR-only document".

**Why.** Access control must apply **before retrieval** (R3). Filtering results after retrieval would still let restricted text affect scoring (through IDF statistics) and would rely on the filter never being skipped. Filtering after generation would rely on the model not repeating what it saw. With a per-role index, restricted text is never in scope, so it cannot leak through snippets, context or scores. Saying "not found" rather than "restricted" avoids confirming that a sensitive document exists.

**Alternatives considered.**

| Option | Why not |
|---|---|
| Filter results after retrieval | Restricted documents would still affect IDF and ranking, and one missed filter call would leak content. |
| Tell the model not to reveal restricted content | Not a real control. It fails under prompt injection and doesn't satisfy "before retrieval". |
| Metadata filters in a vector database or Elasticsearch document-level security | The right tool at scale, and equivalent to our approach, but we have no such service (decision 5). |
| A policy engine (Open Policy Agent, Cerbos, Oso, AWS Verified Permissions) | Useful when rules are complex and shared across services. Four roles and one group check don't need one. |
| Real authentication (OIDC or SSO) | Out of scope in the PRD. Roles are chosen in the UI and treated as if they were authenticated. |
| Return `access_denied` when a restricted document would have matched | Detecting that requires searching restricted documents, which contradicts "before retrieval", and the message would confirm that the document exists. The `access_denied` status appears only in the source viewer's refusal. |

**Revisit when** real identity is connected. Map identity-provider groups to `ROLE_GROUPS` and add row-level access if documents gain per-person permissions.

## 7. Superseded policies: removed from retrieval; changes answered from the active policy

**Decision.** Documents with `status: superseded` are never indexed. Each active replacement has a "Changes from the previous version" section, which is how "What changed in the 2026 travel policy?" gets answered. Superseded documents can still be opened in the source viewer with a warning banner. Citing one is always invalid.

**Why.** The most common failure for policy assistants is confidently quoting the old rule. Removing old versions from retrieval eliminates that failure entirely, and a change log in the new policy is how organisations already communicate changes.

**Alternatives considered.** Keep old versions in the index but lower their score. Rejected because a strong keyword match can still win. Or keep them in and tell the model to prefer the latest date. Rejected because it depends on the model complying, and it makes the "cannot cite superseded policy" guarantee probabilistic.

**Revisit when** users need historical questions answered ("what was the rule in March 2025?"). That would need an explicit "as of" date on the question, not a softer filter.

## 8. LLM provider and SDK: Anthropic, through the official `anthropic` Python SDK

**Decision.** `AnthropicProvider` in `backend/app/llm.py` uses `anthropic` 1.x (`client.messages.create`). It maps the SDK's typed exceptions (`APITimeoutError`, `RateLimitError`, `AuthenticationError`, `BadRequestError`, `APIStatusError`, `APIConnectionError`) to short error kinds shown in the UI. It records input and output tokens from `response.usage`, and treats `stop_reason == "refusal"` as an error. The key is read by the SDK from `ANTHROPIC_API_KEY`. Our code never handles, logs or returns it.

**Why.**
- One real provider through its official SDK, configured by environment variables, is required (R1).
- The official SDK provides typed errors, which is how a timeout becomes a visible `timeout` error rather than a crash. It also provides configurable timeouts and retries, and accurate token usage for cost estimates.
- All provider code sits behind a small `LLMProvider` interface (`generate(system, user, max_tokens, fixture_key)`), so the fixture and test providers share the pipeline exactly, and another provider is a single class to add.

**Alternatives considered.**

| Option | Why not |
|---|---|
| OpenAI, Google Gemini, Mistral or Cohere SDKs | All would work. One provider is required (R1), and adding a second through the same interface is a small change. The comparison is between three approaches, not between vendors. |
| Cloud-hosted Claude (Amazon Bedrock, Google Vertex AI) | Useful when a company must keep traffic in its cloud account. Needs cloud credentials, which works against "add one key and run". |
| Local models (Ollama, llama.cpp, vLLM) | No per-token cost and data stays local, but requires a multi-GB download and a capable machine, and quality on strict citation contracts varies a lot. A good future comparison row, not the default. |
| Raw HTTP with `requests` or `httpx` | Loses typed errors and retries, and the official SDK is required (R1). |

**Revisit when** the company has a preferred or contracted provider, or needs data residency. Add a provider class and set `LLM_PROVIDER`.

## 9. Models and settings

**Decision.**
- **Answer model:** `claude-opus-5-5` (Claude Opus 5.5) with `output_config.effort = "low"`.
- **Judge model:** `claude-sonnet-5-5` (Claude Sonnet 5.5).
- **Truncation:** a response that stops at `max_tokens` is recorded as a `truncated` error, never graded as a complete answer.
- **Limits:** 20-second timeout, one SDK retry, `max_tokens` of 2,000.
- **Configuration:** everything is overridable in `.env` (`LLM_MODEL`, `LLM_EFFORT`, `JUDGE_MODEL`, `LLM_TIMEOUT_S`, `LLM_MAX_RETRIES`). Prices live in `config/pricing.yaml`.

**Why.**
- **Answer model:** Opus is the capable default for following a strict contract ("cite every claim, abstain otherwise"). Low effort is chosen on the *hypothesis* that it keeps short, well-scoped questions within the six-second p95 and $0.02-per-question criteria. No live run has tested that yet, and the decision view will say so if it is wrong.
- **Judge model:** a cheaper model from a different tier. Judging is a narrower task, and using a different model than the one being graded reduces the risk of a model grading itself favourably.
- **Effort is set explicitly.** Opus 5.5 always thinks; effort is the only control, and its API default is `medium`, so leaving it unset would silently raise latency and cost. Opus 5.5 also replaces Opus 5 at a lower price ($4 / $20 per million tokens, against $5 / $25).
- **Max tokens:** 2,000 leaves room for the model's internal reasoning, so answers aren't cut off halfway. If one is, it counts as an error rather than an answer.

**Alternatives considered.**
- **A smaller answer model** (Sonnet or Haiku). It would be faster and cheaper, and it is the natural next experiment if the latency or cost criterion fails. Starting from the most capable model answers the first question: can this work at all? After that, the question becomes how cheap it can be.
- **Higher effort.** Likely more accurate on multi-document questions, but it risks the latency and cost criteria. It is a single environment variable, so it is easy to test on the development split.
- **Using the answer model as the judge.** Simpler, but it raises the self-grading concern.

**Revisit when** the first live run comes back. If cost or latency fails, compare `claude-sonnet-5-5` and `claude-haiku-4-5` on the development split. If correctness fails on multi-document cases, try medium effort.

## 10. LLM framework: none (no LangChain, LlamaIndex or LiteLLM)

**Decision.** Prompts are plain template files. Retrieval, prompt formatting, the model call, parsing and validation are ordinary Python functions in `backend/app/approaches/`.

**Why.** The whole point of the lab is to show exactly what differs between Basic and Guarded RAG. With a framework, that difference would be buried in chain and retriever abstractions, prompt templates inside the library, and callbacks. Here, the diff between `basic_rag.py` and `guarded_rag.py` is the experiment. Fewer dependencies also means less to update when libraries change, and fewer surprises when the pipeline must never make a hidden second call.

**Alternatives considered.**

| Option | Why not |
|---|---|
| LangChain or LangGraph | Quick for prototypes, but its abstractions would hide the exact prompt and control flow we are trying to measure. |
| LlamaIndex | Strong ingestion and indexing, but the same concern, and our corpus is tiny. |
| Haystack | A clear pipeline model and good for production search, but more setup than 21 documents justify. |
| LiteLLM (one interface for many providers) | Useful when comparing vendors. One provider through its official SDK is required (R1), and our own interface is about 20 lines. |
| DSPy (automatic prompt optimisation) | Interesting, but optimising prompts automatically against a small dataset invites overfitting, and the held-out set must not be tuned against. |

**Revisit when** the assistant grows into a multi-step agent (looking things up, filing requests). Orchestration code then earns its keep.

## 11. Output and citation format: text contract with inline passage IDs, validated after generation

**Decision.**
- **Passage IDs in context:** passages are sent to the model labelled with IDs such as `[NS-TRV-2026#3]`.
- **Basic RAG:** asked to cite those IDs.
- **Guarded RAG:** must reply in a two-line `STATUS: ANSWERED|ABSTAINED` / `ANSWER:` format.
- **Parsing and validation:** `citations.py` parses the markers and checks each one: the document exists, the role may read it, it is not superseded, and the passage was in the model's context.
- **When validation fails:** Guarded RAG withholds the whole answer. Basic RAG shows the answer but marks those citations "unverified" and never turns them into source links.

**Why.**
- Inline IDs are easy for a model to produce and for a person to read in the raw output. They also make "cited something it wasn't given" a simple set check.
- Validating after generation is required (R4), and it works the same for every provider.
- The two-line contract is easy to parse. If it can't be parsed, the response becomes a recorded `unparseable_output` error rather than a guess.

**Alternatives considered.**

| Option | Why not |
|---|---|
| Anthropic's built-in citations feature (documents with `citations` enabled) | Returns character-level citations from the provider. It would tie the citation format to one vendor, and the "fabricated citation" failure we need to measure largely stops happening, so Basic and Guarded RAG become harder to compare fairly. Worth testing later as a Guarded RAG variant. |
| Structured JSON output (`output_config.format`, or tool use with a strict schema) | Guarantees the shape of the reply. It would be a reasonable upgrade for Guarded RAG. The text contract was kept so both RAG approaches produce comparable plain-language answers, and because parse failures are themselves worth measuring. |
| Numbered references (`[1]`, `[2]`) mapped back to passages | Less typing for the model, but more room for off-by-one mapping errors, and the raw output is harder to read on its own. |

**Revisit when** a live run shows many `unparseable_output` errors. Switch Guarded RAG to structured output, version the prompt as v2, and compare on the development split.

## 12. Refusal fallbacks and retries: fallback off, one retry, no repair call

**Decision.**
- **Fallback:** the Anthropic API can re-run a refused request on a different model. We don't enable that.
- **Retries:** one automatic SDK retry for connection errors, 429s and 5xx responses.
- **No repair call:** when Guarded RAG's answer fails validation, we don't make a second call to fix it.

**Why.** An experiment has to measure one configured model. A silent fallback would mix two models' answers in one run. A repair call is explicitly ruled out (R4), would hide the failure rate, and would double the cost of exactly the cases most likely to be wrong.

**Alternatives considered.** Enable fallback for production use, where availability matters more than a clean measurement; the refusal is then logged and the served model recorded. Retry validation failures with a stricter prompt; rejected for the reasons above.

**Revisit when** moving from experiment to pilot. Fallback is reasonable there, provided the served model is recorded for each answer.

## 13. Fixture mode: saved example outputs replayed through the real pipeline

**Decision.** Without a key, `FixtureProvider` returns saved raw model text from `data/fixtures/llm_outputs.json`, keyed by approach, role and question. That text then goes through the same parsing, citation validation and grading as live output.
- **Labelling:** fixture responses carry `fixture: true` and show "Demo response". They never have latency or token counts, so cost shows as "unavailable (demo)".
- **Search stays live:** search needs no model, so its results are real even in fixture mode.
- **Decision page:** fixture runs get the verdict "demonstration only" and neutral "Demo" badges instead of green or red.
- **Source of the outputs:** `scripts/build_fixtures.py` writes them and lists which cases deliberately show failure modes.

**Why.** A keyless demo that is visibly labelled and never presented as measurement is required (R5). Replaying raw text through the real pipeline, rather than replaying finished graded results, means fixture mode also exercises the validators. For example, the fabricated citation in case S09 is actually rejected by the code. And the UI shows exactly the same components in both modes.

**Alternatives considered.**

| Option | Why not |
|---|---|
| Record real model responses once and commit them (VCR-style cassettes) | This would be the best option for realism, but no key was available when the project was built. If a live run is made, `results/runs/*.json` fills that role. |
| A mock that returns the reference answer | Too clean. It would show no failure modes, making Inspect and the memo example empty. |
| A small local model for the demo | Big download, slow, and its results could be mistaken for real measurements. |
| Hide the RAG approaches when there's no key | Reviewers couldn't explore the interface, which R5 asks for. |

**Revisit when** a live run exists. Consider regenerating fixtures from real, lightly curated model outputs so the demo looks like real behaviour, keeping the demo label.

## 14. Grading: deterministic first, optional model judge, human review on top

**Decision.**
- **Deterministic grader** (`grading.py`), which always runs. It checks:
  - status and required facts, matched against aliases with word boundaries on normalised text;
  - citation existence, authorization, active status, whether the passage was in context, and whether an acceptable source was cited;
  - disclosures: restricted IDs, restricted facts, and 8-word verbatim spans from restricted passages.
- **Model judge** (`judge.py`), optional in live runs. It grades answered, answerable cases as correct, partially correct or incorrect, says whether citations support the answer, and gives a rationale. Its verdicts are always labelled "model-judged".
- **Human reviews** are stored separately. The final label follows human, then judge, then deterministic, and the original grades are never overwritten.

**Why.** Each layer covers the one below it.
- The deterministic grader is reproducible, free and strict about numbers and access, which are the things that must never be wrong. But it can be fooled by wording: case O02 in the fixture is marked correct because "manager" appears, even though the answer wrongly adds VP approval.
- The judge understands meaning but is itself a model.
- Humans are the final authority, and keeping all three lets anyone see where they disagree.

**Alternatives considered.**

| Option | Why not |
|---|---|
| Only a model judge | Cheaper to build, but security-critical checks like disclosures shouldn't depend on a model, and results change from run to run. |
| Only exact or fuzzy string matching | Too brittle for paraphrased answers on its own. |
| Text-similarity scores (ROUGE, BLEU, BERTScore) | They measure overlap with the reference wording, not whether the policy fact is right. A correct answer worded differently scores low, and a wrong number can score high. |
| RAG-specific metric libraries (Ragas faithfulness, answer relevancy) | Useful signals, but most are model-judged under the hood and add dependencies. They don't cover role-based disclosure, which is our most important check. |

**Revisit when** the judge and deterministic grader disagree often in live runs. Review the disagreements by hand, then tighten the fact aliases or the judge prompt (as v2) using development cases only.

## 15. Evaluation tooling: our own runner rather than an eval framework

**Decision.** `backend/app/evaluation.py` runs every case and approach in a thread pool.
- **Isolation:** any exception while answering or grading a case becomes a recorded `internal_error` response, and the run continues. If something outside a single case fails, such as the database, the run is marked `failed` rather than left as `running`.
- **Self-contained runs:** every run stores the corpus hash, dataset hash, prompt versions and model configuration. It also stores a full snapshot with the launch criteria, their hash, and the dataset cases it was graded against. Reopening a run, or deciding on it later, uses that snapshot, not whatever the files say today.
- **Held-out discipline:** the CLI supports `--split development`, so tuning never touches held-out data. The Decision view and reports skip development-only runs when picking the latest result.

**Why.** The requirements are specific (R6 to R9): per-case isolation, immutable runs, version stamps, a held-out discipline, SQLite storage, human review and a custom decision view. Existing tools cover pieces of this. None cover the role-based disclosure metric or the decision logic, and most need a hosted account or their own storage.

**Alternatives considered.**

| Option | Why not |
|---|---|
| promptfoo | Very good for comparing prompts and models from YAML test files. It is a Node tool with its own result store, and would need custom assertions for access control and a separate place for human review. |
| DeepEval or Ragas | Python eval libraries with many built-in LLM-judged metrics. Useful to borrow ideas from, but they would be a second grading system alongside the one we need anyway. |
| OpenAI Evals, Inspect AI (UK AI Security Institute) | Well-designed frameworks for benchmark-style tasks. More structure than a 60-case product evaluation needs. |
| Hosted platforms (LangSmith, Braintrust, Arize Phoenix, Weights & Biases Weave, Humanloop) | Strong tracing, dataset and review tools, but they require an account and send data to a third party. A reviewer couldn't run the lab offline. |

**Revisit when** the team runs evaluations weekly on real traffic, with several reviewers. A hosted platform's review queues and trace views would then be worth the dependency. The run export format is simple JSON, so it can be imported.

## 16. Statistics: Wilson intervals and nearest-rank percentiles

**Decision.** Every rate is shown as a value, a count (numerator/denominator) and a 95% Wilson interval. An empty denominator shows "no cases", not 0%. A criterion computed from fewer than 5 cases is "insufficient evidence". Latency p50 and p95 use the nearest-rank method, so the reported p95 is always a latency that actually happened.

**Why.** With 6 unanswerable held-out cases, one case moves the rate by 17 points, so the uncertainty has to be visible. The Wilson interval behaves sensibly at 0% and 100% and with small samples, where the textbook normal approximation breaks down (for example, it gives a zero-width interval at 6 out of 6).

**Measurement coverage.** Latency and cost are judged on the cases that were measured, but only when at least 90% of cases have a measurement (`min_measurement_coverage`). The alternatives were worse. Requiring 100% would let one timeout with no token usage block the cost verdict. Averaging the missing cases in as $0 would break R7.

**Alternatives considered.** The normal approximation: wrong at small n. Clopper-Pearson intervals: valid but overly conservative. Bootstrap intervals: more general but not deterministic unless seeded, and more than a single proportion needs. Interpolated percentiles (numpy's default): fine, but they can report a latency that never occurred. SciPy or statsmodels: not needed for two short formulas.

**Revisit when** comparing two approaches directly. A paired test such as McNemar's on the same cases would answer whether the difference between them is real.

## 17. Configuration: versioned files in git, secrets only in the environment

**Decision.**
- **Settings files:** approach settings and launch criteria are YAML (`config/approaches/*.yaml`, `config/launch_criteria.yaml`). Prompts are Markdown files with a version header (`config/prompts/*.md`). Prices are in `config/pricing.yaml`.
- **Snapshots and hashes:** every run stores a snapshot of all of this, and the decision page shows a hash of the criteria file.
- **Environment:** runtime settings and the API key come from environment variables or a git-ignored `.env`, read by a 15-line loader in `settings.py`. The browser only receives the key's variable name and whether it is set.

**Why.** Prompts and thresholds are the experiment's independent variables, so they belong in version control, where changes show up in diffs. Each run stores the criteria and their hash, so a threshold edited after results are seen cannot change an existing verdict, and the Decision view flags that the current file differs (R9).

**Alternatives considered.**

| Option | Why not |
|---|---|
| Prompts inside Python code | Harder to diff and review, and mixes experiment design with implementation. |
| A prompt management service (LangSmith Hub, PromptLayer, Humanloop) | Adds a network dependency, and versions would live outside git. |
| `pydantic-settings` or `python-dotenv` | Both are good. The needs here (a few variables, and never override the real environment) fit in 15 lines, so a dependency wasn't worth it. |
| TOML or JSON for configuration | JSON doesn't allow comments, which the pricing and criteria files need. TOML would work just as well; YAML was chosen because the front matter already uses it, so the project needs one parser. |
| A secrets manager (Vault, AWS Secrets Manager, Doppler) | Right for production, too much for a local lab. |

**Revisit when** deploying. Inject secrets from the platform's secret store, and keep `.env` for local development only.

## 18. Frontend libraries: React only

**Decision.** React 19 and TypeScript 6 (strict), built with Vite 8. There are no other runtime dependencies.
- **Routing:** about 30 lines of hash-based code (`router.ts`).
- **Data fetching:** a typed wrapper around `fetch` (`api.ts`) plus one small hook, `useAsync`, which exposes loading and error state and ignores a response if a newer request has started. Switching runs or filters quickly can therefore never show data for the wrong selection.
- **State:** `useState` plus two React contexts, one for the server configuration and one for the source drawer.
- **Deep links:** every Inspect filter and selection is in the URL, and all links preserve it.

TypeScript is pinned to 6.0, not the newer 7.x, because typescript-eslint doesn't support 7.x yet. Linting was judged more valuable than the newest compiler.

**Why.**
- React, TypeScript and Vite are required (R1).
- The app has four views with little shared state. Hash routing means deep links such as `#/inspect?run=…&case=U02&focus=basic_rag` work without any server rewrite rules, which is how the Decision view links failing criteria to example cases.
- With no extra libraries, the app is about 80 KB gzipped, and there is less to learn or update.

**Alternatives considered.**

| Option | Why not |
|---|---|
| React Router or TanStack Router | Both are the standard choices for larger apps. With four flat routes, our own 30 lines are enough. |
| TanStack Query or SWR | Caching, deduplication and automatic refetching help when many views share server data. Here the need is narrower: loading, error and stale-response handling, which `useAsync` covers in about 40 lines. TanStack Query is the first thing to add if views start sharing cached data. |
| Redux, Zustand or Jotai | No complex shared state to manage. |
| A component library (MUI, Chakra, Mantine, Ant Design) | Speeds up building, but makes the app look like the library's template. The goal is a restrained look, like a small internal product. Tables, badges and a drawer are simple to write. |
| Headless components (Radix, shadcn/ui) | Radix would be the first addition if the UI grows. Its accessible dialogs and menus would be worth having. The drawer here is a modal dialog: it moves focus in, traps Tab, closes on Escape, and returns focus to the citation. |

**Revisit when** the UI grows beyond about six views or needs complex forms. Add a router and Radix primitives first.

## 19. Charting: a hand-written SVG chart

**Decision.** The "quality versus cost" chart (`QualityCostChart.tsx`) is about 90 lines of SVG and React.
- **Content:** three points, dashed launch-threshold lines, direct labels, a legend, and a hover or focus tooltip.
- **Colours:** the three series use the first three slots of a palette checked for colour-blind separation, and each point also has a text label, so identity never depends on colour alone.
- **Missing cost:** an approach whose cost is unknown is not plotted. The legend says why ("cost unavailable for 45 of 45 cases").

**Why.** A chart library tends to plot a missing value as 0, which R7 forbids for cost. Three points don't justify a 100 KB dependency. Writing the SVG directly also gives full control over the threshold lines and the "not plotted" explanation.

**Alternatives considered.** Recharts, Nivo, Victory, Chart.js, ECharts and Plotly are all fine for dashboards with many chart types. D3 is the most flexible but is itself low-level for three points. Vega-Lite is a good choice for exploratory charts in a report.

**Revisit when** the Compare view gains more charts, such as latency distributions or per-category breakdowns. Then use Recharts or Vega-Lite.

## 20. Styling: one plain CSS file with design tokens

**Decision.** `frontend/src/styles.css` defines colour, radius and font tokens as CSS custom properties, followed by plain class-based styles for each part of the UI. One breakpoint at 1000 px stacks the columns.

**Why.** About 270 lines of CSS cover the whole app with no build plugins or class-name conventions to learn. Keeping status colours (ok, warning, error, demo) as named tokens is what makes demo badges look consistently different from live pass/fail badges everywhere.

**Alternatives considered.** Tailwind: productive, but the class strings make components harder to scan in a portfolio review, and it adds a build step. CSS Modules: good for isolating styles, but unnecessary at this size. CSS-in-JS (styled-components, Emotion): adds runtime cost and is falling out of favour with modern React.

**Revisit when** multiple people work on the UI. CSS Modules or Tailwind then reduce style collisions.

## 21. Testing: pytest, Vitest, Testing Library, and a local fake of the provider API

**Decision.**
- **Backend:** pytest with FastAPI's `TestClient`. Each API test gets its own temporary SQLite file. Approach tests use `ScriptedProvider`, a test double whose output we choose, to create exact failures: fabricated citations, superseded citations, timeouts, unparseable output.
- **Provider adapter:** tested against a small local HTTP server that mimics the Messages endpoint. This covers usage parsing, the effort setting, and timeout mapping without a network or key.
- **Frontend:** Vitest with jsdom and Testing Library, covering components and all four views against a mocked `fetch`: error states, deep links, demo labelling, and chart rules.
- **Python versions:** CI runs the backend suite on Python 3.10 (the documented minimum) and 3.12.

**Why.** Each acceptance criterion maps to at least one named test, and every defect found in the [engineering review](engineering_review.md) has a regression test. A test double makes failure paths deterministic, which a real model can't be relied on to produce. The fake server tests the real SDK code, not a mock of it. Vitest shares Vite's configuration, so there is no separate Babel or Jest setup.

**Alternatives considered.**

| Option | Why not |
|---|---|
| Jest | Mature, but needs separate transform configuration for Vite projects. Vitest is compatible with Jest's API and uses the existing config. |
| `respx` or `pytest-httpx` to mock HTTP | They patch the HTTP client inside the process. The `anthropic` 1.x SDK uses its own HTTP client, so a real local socket is a more robust fake. |
| VCR.py (record and replay real API calls) | Needs a key to record, and recordings can accidentally capture headers containing keys. |
| Playwright end-to-end tests in CI | Valuable, but adds browser setup to CI. The main user path was verified by hand in a real browser instead (decision 23). A small Playwright suite is the next test investment. |
| Snapshot tests of components | Tend to break on harmless changes. Tests assert on behaviour instead, for example that invalid citations are never clickable. |

**Revisit when** the UI changes often. Add Playwright tests for the four-view path to CI.

## 22. Developer workflow: Makefile and virtualenv, no Docker; GitHub Actions for CI

**Decision.** A `Makefile` with `setup`, `demo`, `api`, `web`, `eval`, `eval-dev`, `reports`, `fixtures`, `lint`, `test` and `check`. A standard `.venv` for Python and `npm ci` for Node. GitHub Actions runs everything in `make check` on each push, plus a production build.

**Why.** Make is available on macOS and Linux, and the targets double as documentation of the workflow. A virtualenv plus npm is what most reviewers already have.

**Alternatives considered.**

| Option | Why not |
|---|---|
| Docker or Docker Compose | Makes the environment reproducible, but needs Docker installed and a large image. First startup is slower than the two-minute target. A good optional addition for reviewers without Python 3.10+ or Node 20+. |
| `uv`, Poetry or PDM for Python | `uv` in particular is much faster. Plain `pip` with a requirements file avoids asking reviewers to install another tool. |
| `just` or Taskfile | More pleasant syntax than Make, but another tool to install. |
| pnpm or Yarn | Either would work. npm ships with Node. |
| Other CI (GitLab CI, CircleCI) | The repo is on GitHub. |

**Known limitation.** Make isn't available by default on Windows. Windows users can run the commands listed in each target directly, or use WSL.

**Revisit when** reviewers report setup trouble. Add a `Dockerfile` and a `uv`-based setup as an alternative path.

## 23. Screenshots: Playwright, run once and not added as a project dependency

**Decision.** The README screenshots were captured with Playwright driving the preinstalled Chromium through the main path: ask a question, open a source, try a restricted question, then Compare, Inspect and Decision. The same session checked the review flow and that there were no console errors. Playwright was installed in a temporary directory, not added to `package.json`.

**Why.** Screenshots are needed once per UI change. Adding a browser-automation package and browser download to every reviewer's `npm ci` would slow down setup for everyone.

**Alternatives considered.** Manual screenshots: not repeatable. Storybook visual tests: useful for component libraries, heavy for four views. Adding Playwright as a dev dependency: the right move once there is an end-to-end suite (decision 21).

**Revisit when** Playwright end-to-end tests are added. Screenshot capture then becomes a script in the same suite.

## 24. Code-quality tooling: ruff, ESLint, strict TypeScript, and CI that runs them

**Decision.**
- **Python:** `ruff` for linting (pyflakes, pycodestyle, isort, bugbear, pyupgrade, simplify, ruff-specific rules) and formatting. Configuration is in `backend/pyproject.toml`.
- **TypeScript:** ESLint with `typescript-eslint` and the React hooks rules, and TypeScript in strict mode.
- **Enforcement:** `make lint` runs all of it and CI fails on any finding. The code has no lint suppressions.

**Why.** Style debates are settled by the formatter, and whole classes of bugs are caught before review: unused imports and variables, likely bugs flagged by bugbear, and missing effect dependencies. The hooks rules found stale-closure bugs in the first version of the Inspect and Compare views.

**Alternatives considered.** Black plus isort plus flake8: equivalent but three tools instead of one. mypy or pyright in CI: valuable. The backend has type hints on public functions, but a strict type-check pass is the next quality step. Prettier: the ESLint rules plus consistent hand formatting were enough at this size. Pre-commit hooks: a good addition for contributors; CI already enforces the same checks.

**Revisit when** more contributors join. Add pre-commit and a strict pyright run.

---

## Summary of what would change for a production pilot

| Area | Lab choice | Pilot choice |
|---|---|---|
| Identity | Role picked in the UI | SSO (OIDC), groups mapped to roles |
| Retrieval | Local BM25, per-role index | Hybrid BM25 plus embeddings with document-level security (for example OpenSearch, or Postgres with pgvector and row-level security) |
| Storage | SQLite | Postgres with migrations |
| Content | Markdown in git | Sync from the policy system of record, with freshness checks |
| Model calls | Sync SDK, no fallback | Async SDK, fallback enabled with the served model recorded, streaming answers |
| Evaluation | Local runner, 60 cases | Same runner plus a hosted review queue and weekly samples of real traffic |
| Deployment | `make demo` | Container image, CDN for the UI, secrets from the platform store |
