# E00 — Repository bootstrap & walking-skeleton harness

**Objective:** a repo where every later epic can start red-green-refactor on minute one.
**Depends on:** — (Phase 0). **Owned paths:** everything scaffolding; no domain logic.
**Read first:** specs/CLAUDE.md; architecture doc §13; fixtures/README.md.

## Scope
- Hexagonal skeleton: `src/{domain,ports,adapters,services,api}`, `tests/{unit,integration,acceptance}`, `migrations/`.
- Tooling: pyproject (ruff, mypy strict, pytest), pre-commit, Makefile targets exactly as named in CLAUDE.md, GitHub Actions CI running check + integration + isolation.
- docker-compose: Postgres 16 for integration/acceptance; test settings via env.
- Fixture harness: `tests/conftest.py` fixtures that load `fixtures/` JSON + PDFs; a `make test-acceptance` target that applies `fixtures/sql/schema.sql` and runs `fixtures/sql/load_fixtures.py` into the test DB.
- Empty acceptance-test scaffolds: one skipped test per v0.2 skeleton criterion (1–16), named for the behavior, each tagged with its epic (`@pytest.mark.epic("E04")`). These are the program's backlog in executable form.

## Non-goals
No domain code, no schema beyond applying the fixture SQL verbatim.

## Tests first
- `test_make_check_passes_on_clean_clone` (CI job is the assertion).
- `test_fixture_bundle_loads_and_row_counts_match` (2 templates, 3 masks, 3 documents).
- `test_all_16_acceptance_scaffolds_are_collected_and_skipped`.

## Security
- Pre-commit secret scan; dependency audit job (pip-audit) in CI; `.env.example` only, never `.env`.

## Definition of done
Fresh clone → `make setup && make check && make test-acceptance` green (with 16 skips); CI mirrors it; CLAUDE.md at repo root.
