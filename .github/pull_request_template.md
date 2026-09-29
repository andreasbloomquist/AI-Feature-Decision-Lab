## Summary

<!-- One or two sentences: what this PR does. Include roadmap IDs (e.g. R2.3) if it delivers one. -->

## Why

<!-- The problem it solves, for whom. Link issues, review findings or roadmap items. -->

## Changes

<!-- The notable changes, grouped by area. Call out any API field added, config or criteria change, or migration. -->

## Testing

<!-- What you ran and the result. Say plainly what was NOT verified (e.g. "not run against a live model"). -->

- [ ] `make check` passes

## Review checklist

See [CONTRIBUTING.md → Principal-engineer review](../CONTRIBUTING.md#principal-engineer-review).

- [ ] Independent principal-engineer review done (or docs-only change)
- [ ] Decision integrity: no path to a recommendation the evidence doesn't support
- [ ] Access control and secrets: no restricted content, restricted ID, document existence or key can leak
- [ ] API changes are additive; `frontend/src/types.ts` updated
- [ ] Every behaviour change and fixed defect has a regression test
- [ ] Docs updated (README, `docs/`, `AGENTS.md`); `docs/ROADMAP.md` statuses updated
- [ ] Generated reports regenerated with `make reports` if metrics or report logic changed
- [ ] Nothing presents fixture data as a measurement
