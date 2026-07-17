# Implementation spec pack — Document Extraction Platform

Specs and working agreements for building the platform with a Claude Code agent team,
test-driven, from the approved architecture (`document-extraction-architecture.md` +
client draft v0.2). One epic = one reviewable unit of work = typically one Claude Code
session (or a few, for the larger epics).

## Contents

| Path | Purpose |
|---|---|
| `CLAUDE.md` | Drop into the repo root — model-agnostic project memory for every agent session: stack, architecture rules, TDD loop, forbidden patterns, commands |
| `MODELS.md` | Multi-model working agreement: lane assignments, cross-review protocol with structured verdicts, arbitration rules, bake-off procedure |
| `epics/E00…E12` | Thirteen epic specifications, each self-contained: objective, interfaces, test-first plan, security requirements, definition of done |
| `../fixtures/` | The walking-skeleton fixture bundle — the acceptance-test data for everything |

## Operating model for the agent team

**One epic per session, tests first, review gate before merge.**

1. **Session start:** the agent reads `CLAUDE.md`, the epic file, and the architecture
   sections the epic references ("Read first"). Nothing else — epics are written to be
   self-sufficient so sessions don't drown in context.
2. **Red:** the agent writes the epic's listed acceptance/unit tests first and commits
   them failing (`test:` commit). Tests are the specification — if a test can't be
   written from the epic, the epic is wrong; stop and flag it, don't improvise.
3. **Green:** implement the minimum that passes. Ports (interfaces) before adapters;
   domain logic pure and framework-free.
4. **Refactor:** apply the review checklist in `CLAUDE.md` before opening the PR.
5. **Review gate:** a *different* session (or human) reviews the PR against the epic's
   definition of done + the checklist. The isolation test suite (E02) runs on every PR
   regardless of epic — a red isolation suite blocks everything.

## Dependency graph / phasing

```
Phase 0   E00 bootstrap
Phase 1   E01 contracts        E02 tenant isolation        (parallel)
Phase 2   E03 ingestion        E04 candidate routing       E06 provenance   (parallel)
Phase 3   E05 extraction cascade         E07 projections + query surface
Phase 4   E08 lineage + mask migration   E09 mapping + review workflow
Phase 5   E10 orchestrator retrieval     E11 embedding pipeline
Phase 6   E12 telemetry + pilot scorecard
```

Parallel epics must not touch the same modules; the epic files declare their owned
directories. When two agents need the same interface, the *port definition* lands in
E01's contracts package first and both depend on it.

## Non-negotiables (enforced in review, restated in every epic)

- **TDD is the workflow, not a report format.** No implementation commit without a
  preceding failing test in history.
- **Ports and adapters.** Domain code depends on abstractions (`Protocol`/ABC) only.
  Postgres, object storage, model providers, and the Validation Service are adapters,
  swappable in tests with in-memory fakes.
- **The architecture's forbidden patterns** (see `CLAUDE.md`) are review-blocking:
  business rules in this codebase, dynamic SQL, whole-document prompts,
  cross-tenant reads, mutation of versioned artifacts, values without provenance.
- **Pilot exit criteria** (v0.2 §12.1) are the program's definition of done — E12's
  scorecard makes them measurable.

## Claude Code specifics

Keep sessions scoped (one epic), let `CLAUDE.md` carry the standing rules, and prefer
`/clear`-fresh sessions per epic over one long session. For current Claude Code
capabilities and workflow features (subagents, hooks, memory), verify against the
docs rather than assumption: https://docs.claude.com/en/docs/claude-code/overview
