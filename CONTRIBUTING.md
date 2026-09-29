# Contributing

This guide is for everyone who changes the repository, people and AI agents alike. AI agents should also read [AGENTS.md](AGENTS.md), which adds a short list of rules specific to them.

**The short version**
1. Branch from `main`. Never commit to `main` directly.
2. Keep each PR to one purpose, and open it against `main`.
3. Run `make check` before you push. CI runs the same checks.
4. Every PR that changes code gets a principal-engineer review before it merges (see [below](#principal-engineer-review)).
5. Update the docs and the [roadmap](docs/ROADMAP.md) in the same PR as the change.

## Setup

```bash
make setup    # Python venv in .venv plus frontend packages (Python 3.10+, Node 22.22+)
make check    # lint, format check, typecheck, backend and frontend tests
```

See the [README](README.md#run-it-locally) for running the app.

## Git workflow

### Branches

`main` is always releasable: CI is green, and the docs match the code. All work happens on short-lived branches cut from the latest `main`:

```bash
git switch main && git pull
git switch -c feat/run-diff-view
```

Name branches `<type>/<short-description>`, using the same types as commit messages (`feat/`, `fix/`, `docs/`, `refactor/`, `test/`, `chore/`). Branches created by Claude Code sessions start with `claude/`; that's fine.

### Commits

- **Subject line:** imperative mood, at most 72 characters, no trailing period. For example, `Fix existence oracle in public citations`. A `type:` prefix (`fix: …`) is welcome but not required.
- **Body:** say *why* the change is needed and what it affects, not a line-by-line list of what changed. Reference roadmap IDs (`R2.3`) and review finding numbers (`#35`) where they apply.
- **One logical change per commit.** Don't mix a refactor with a behaviour change.
- **No secrets, ever.** `.env` is git-ignored. If a key is committed by mistake, rotate the key first; rewriting history comes second.

### Pull requests

- **Open every PR against `main`.** The PR template gives the structure: summary, why, changes, testing, review checklist.
- **Keep PRs small and single-purpose.** A reviewer should be able to hold the whole diff in their head. Split large work into a stack: each PR targets the branch below it. When the lower PR merges and its branch is deleted, GitHub retargets the next PR to `main`.
- **The title says what the PR does**, for example `Add run-to-run diff view (R2.3)`.
- **Keep the branch current by merging `main` into it** (`git merge main`). Don't rebase or force-push a branch that someone else has checked out or reviewed. On a branch only you use, rebasing before review is fine.
- **Merge with "Squash and merge"** so that `main` has one commit per PR, titled after the PR. Delete the branch after merging.
- **Draft PRs** are for early feedback. Mark the PR ready only when `make check` passes and the checklist is complete.

### Protecting `main` (repository settings)

A repository admin should enable these under *Settings → Branches → Branch protection rules* for `main`:

- Require a pull request before merging, with at least 1 approval.
- Require status checks to pass: the `backend (3.10)`, `backend (3.12)` and `frontend` CI jobs.
- Require branches to be up to date before merging.
- Block force pushes and deletions.

## Principal-engineer review

Every PR that changes code, configuration, prompts, the dataset or the launch criteria gets a review at principal-engineer depth before it merges. Changes that are only documentation get the [documentation check](#documentation-standards) instead.

**Who reviews.** Someone other than the author. For work done by an AI agent, that means a separate reviewer: a human, or an independent agent with no context from the author. A reviewer's findings are verified before they're acted on: reproduce the problem, or confirm it by reading the code.

**What the review checks**, most important first:

1. **Decision integrity.** Can this change make the lab propose a launch decision that the evidence doesn't support? Look at metrics, grading, criteria, run selection, the handling of fixture data, and human overrides.
2. **Access control and secrets.** Can restricted content, restricted document IDs, or the existence of a restricted document reach a role that may not read it? Can an API key reach a response, log, database or export?
3. **Correctness.** Edge cases (empty splits, zero denominators, missing usage, timeouts, truncation), concurrency, and error paths that would mislabel a failure.
4. **Contracts.** API responses change additively only: fields are added, never renamed or removed. Frontend types match the backend. Every stored run stays readable.
5. **Tests.** Every behaviour change and every fixed defect has a named regression test that fails without the fix.
6. **Clarity.** Could the next person, or agent, understand this without the author? Are the names, comments and docs right?

**Recording the review.**
- Findings go in PR review comments.
- A finding of Medium severity or higher, and anything that changes how the decision is made, is also added to [docs/engineering_review.md](docs/engineering_review.md) with its fix and its regression test.

Severity:
- **Critical:** a secret or restricted data can leak.
- **High:** wrong results or a broken core path.
- **Medium:** a correctness risk or a maintainability problem a senior reviewer would block on.
- **Low:** polish.

## Documentation standards

The docs are read by people who have never seen the code, and by AI agents that act on them literally. Write for both:

- **Lead with the point.** The first sentence of every doc and section says what it is for.
- **Be concrete.** Give exact commands, file paths and defaults. Name the thing you mean, such as `config/launch_criteria.yaml`, rather than "the config".
- **One source of truth.** State a fact in one place and link to it everywhere else. Thresholds live in `config/launch_criteria.yaml`, roadmap items in `docs/ROADMAP.md`, and model defaults in `.env.example`.
- **Keep the docs true.** A PR that changes behaviour updates the docs that describe it. A reviewer who finds a doc that contradicts the code treats it as a bug.
- **Mark generated files.** `docs/evaluation_report.md` and `docs/decision_memo.md` are generated by `make reports`. Never edit them by hand.
- **Say what's unknown.** If something hasn't been measured or verified, say so rather than implying it has.

## Definition of done

A PR is ready to merge when:

- [ ] `make check` passes locally and CI is green.
- [ ] A principal-engineer review is complete, and every finding is fixed or answered.
- [ ] Every behaviour change and fixed defect has a regression test.
- [ ] Docs describe the new behaviour. `docs/ROADMAP.md` statuses are updated. Generated reports are regenerated with `make reports` if metrics or report logic changed.
- [ ] Nothing in the diff presents fixture data as a measurement.
- [ ] No secrets, and no personal data, in the diff.

## Where to start

- The [roadmap](docs/ROADMAP.md) lists the next items; items marked **Next** are ready to pick up.
- The [architecture doc](docs/architecture.md) explains the request and evaluation paths.
- The [technical decisions](docs/decisions.md) explain why things are the way they are. If you disagree with one, change it in a PR that updates its entry.
