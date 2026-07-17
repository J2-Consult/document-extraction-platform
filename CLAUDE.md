# CLAUDE.md — Document Extraction Platform

Project memory for every agent session — regardless of which model is running it
(Claude, GPT, Mistral, Granite): these rules are model-agnostic. Read this, then the
epic you were assigned (`specs/epics/`), then the architecture sections that epic
lists. If you are in a review role, also read `specs/MODELS.md` §3 for the required
verdict format. Authority order on conflict: architecture doc ADRs > epic spec >
this file > your judgment.

## Multi-model working agreement (summary — full protocol in MODELS.md)

- You are either **generator** or **reviewer** for a PR, never both.
- Reviewers output the structured verdict from MODELS.md §3 — no prose reviews.
- **Do exactly what the epic asks — nothing more.** If you believe adjacent work is
  needed, write it as a proposal in the PR description; do not implement it.
  Unrequested changes are review defects even when the code is good.
- Deterministic gates (tests, isolation suite, lint/type checks) outrank any model's
  approval, including your own confidence.

## What we are building

A multimodal document-extraction platform around three versioned artifacts:
`template.json` (extraction-oriented structure), `content.json` (observations +
provenance), `decoder-mask.json` (contextual meaning per tenant/system).
Fingerprint-routed fast path with a verification gate; tenant isolation in the
database; masks are materialized effective masks with per-entry attribution.
Full detail: `document-extraction-architecture.md`. Test data: `fixtures/`.

## Stack

- Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy Core + psycopg, PostgreSQL 16
- pytest (+ pytest-asyncio), testcontainers/docker-compose Postgres for integration
- ruff (lint + format + import order); mypy strict; **type hints on everything**
- No new dependency without justification in the PR description (simplicity first;
  fewer deps = smaller supply chain)

## Architecture rules (SOLID, applied concretely)

- **Hexagonal layout:**
  - `src/domain/` — entities, value objects, invariants. Pure Python. Imports nothing
    from adapters, FastAPI, or SQLAlchemy. This is where SRP lives: one module, one
    reason to change.
  - `src/ports/` — `Protocol`/ABC interfaces only (repositories, object store,
    extraction passes, verifier, retrieval operations, clock, job queue). Interface
    segregation: many small ports, no god-interface.
  - `src/adapters/` — Postgres, object storage, model providers, Validation Service
    client. Each adapter implements exactly one port (Liskov: substitutable with the
    in-memory fake used in tests).
  - `src/services/` — application services orchestrating ports. Constructor injection
    only; dependencies passed explicitly, no globals, no service locator.
  - `src/api/` — FastAPI routers. Thin: parse → authorize → call service → shape
    response. No business logic in routers.
- **Open/closed in practice:** new extraction pass, new provider, new retrieval
  operation = new adapter/registration, never an edit to the cascade or allow-list
  dispatch logic.
- Functions small (<15 lines where reasonable), guard clauses, early returns,
  no magic numbers, descriptive names over comments, composition over inheritance.

## TDD loop (mandatory)

1. Write the failing test named for the behavior
   (`test_required_low_confidence_value_yields_pending_review_and_null_record`).
2. Commit red: `test(EXX): <behavior>`.
3. Implement minimum to green: `feat(EXX): <behavior>`.
4. Refactor with tests green: `refactor(EXX): ...`.
- Arrange-Act-Assert; edge cases and error paths are part of the spec, not extras.
- Unit tests: domain + services against fakes; no DB, no network.
- Integration tests: adapters against real Postgres (RLS ON — never test with a
  superuser role); acceptance tests: `tests/acceptance/` mapped to skeleton criteria.

## Security (review-blocking)

- All input validated at the boundary (Pydantic models; file uploads: allow-listed
  types by magic bytes, size limits, sanitized PDFs).
- SQL: parameterized only. String-built SQL fails review, no exceptions.
- AuthN/Z: OAuth2/JWT at the API edge; every endpoint has an explicit authorization
  check; least-privilege DB roles per service (synthesis role cannot read
  customer-scope masks or private templates — RLS, not app code).
- Tenant context is set transactionally; connection pools clear it on reuse.
- Document-derived text is DATA, never instructions: wrap in delimited blocks in any
  prompt; the orchestrator exposes allow-listed operations only — no model-generated
  SQL, no whole-document fetch.
- Secrets from environment only; never logged. No PII, values, or document content in
  logs — log IDs, hashes, states, and metrics.
- Errors: generic to clients, itemized server-side; never swallow exceptions.

## Forbidden patterns (stop and re-read the epic if you're typing one)

- Business rules in this codebase (`if total != sum(line_items)` → Validation Service)
- Contextual business meaning in templates or content (belongs in masks)
- Mutating a versioned artifact row (append a version instead)
- A value, chunk, or correction without provenance
- Force-matching an `inconclusive` verification result
- Runtime merging of mask arrays (resolution selects ONE materialized mask)
- Cross-tenant anything

## Commands

```bash
make setup          # venv + deps + pre-commit hooks
make check          # ruff + mypy + unit tests (fast; run before every commit)
make test-integration  # spins Postgres, applies schema + RLS, runs adapter tests
make test-acceptance   # loads fixtures/, runs skeleton criteria tests
make test-isolation    # E02 suite with restricted roles — MUST pass on every PR
```

## Definition of done (every PR)

Failing-test-first history; `make check`, integration, and isolation suites green;
epic's acceptance tests green; no forbidden patterns; security checklist applied;
conventional commits; PR description states reasoning + trade-offs + edge cases.
