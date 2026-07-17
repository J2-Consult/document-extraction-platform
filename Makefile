# Document Extraction Platform — bootstrap Makefile (E00).
#
# VENV is overridable so the venv can be placed off any filesystem that
# mishandles file permissions on close (see README/CLAUDE.md environment notes):
#   make setup VENV=/path/off/the/problem/mount
#
# Note: recipes avoid `.ONESHELL:` — macOS ships GNU Make 3.81, which predates
# that directive. Multi-step conditional logic is instead written as a single
# logical recipe line using classic backslash continuation.

VENV ?= .venv
PYTHON := $(VENV)/bin/python
PYTEST_ARGS ?=

SHELL := /bin/bash

.PHONY: setup check test-integration test-acceptance test-isolation

setup:
	python3 -m venv "$(VENV)"
	"$(PYTHON)" -m pip install --upgrade pip
	"$(PYTHON)" -m pip install -e ".[dev]"
	"$(VENV)/bin/pre-commit" install || echo "NOTE: pre-commit hook install skipped"

# Scoped to E00's owned Python paths (everything except fixtures/ and specs/,
# per CLAUDE.md) so this gate doesn't block on other epics' in-flight work.
# benchmarks/ added by E04 (benchmarks/routing/ is real, type-checked Python,
# not test data — it needs the same gate as src/).
LINT_PATHS := src scripts tests benchmarks

check:
	"$(PYTHON)" -m ruff check $(LINT_PATHS)
	"$(PYTHON)" -m ruff format --check $(LINT_PATHS)
	"$(PYTHON)" -m mypy src scripts tests benchmarks
	"$(PYTHON)" -m pytest tests/unit -q $(PYTEST_ARGS)

# DB-backed targets: gate on Postgres reachability first. Unreachable + not CI
# => print SKIP and exit 0 (keeps local dev unblocked without Docker/Postgres).
# Unreachable + CI=true => fail hard (CI must never silently skip DB coverage).
test-integration:
	if ! "$(PYTHON)" -m scripts.db_check; then \
		if [ "$${CI:-}" = "true" ]; then \
			echo "FAIL: Postgres unreachable at $${POSTGRES_HOST:-localhost}:$${POSTGRES_PORT:-5432} and CI=true"; \
			exit 1; \
		fi; \
		echo "SKIP: Postgres unreachable at $${POSTGRES_HOST:-localhost}:$${POSTGRES_PORT:-5432} — run 'docker-compose up -d' to enable this target locally"; \
		exit 0; \
	fi; \
	code=0; \
	"$(PYTHON)" -m pytest tests/integration -m integration $(PYTEST_ARGS) || code=$$?; \
	if [ "$$code" = "5" ]; then \
		echo "SKIP: no integration tests collected yet"; \
		exit 0; \
	fi; \
	exit $$code

test-acceptance:
	if ! "$(PYTHON)" -m scripts.db_check; then \
		if [ "$${CI:-}" = "true" ]; then \
			echo "FAIL: Postgres unreachable at $${POSTGRES_HOST:-localhost}:$${POSTGRES_PORT:-5432} and CI=true"; \
			exit 1; \
		fi; \
		echo "SKIP: Postgres unreachable at $${POSTGRES_HOST:-localhost}:$${POSTGRES_PORT:-5432} — run 'docker-compose up -d' to enable this target locally"; \
		exit 0; \
	fi; \
	"$(PYTHON)" -m scripts.apply_fixtures; \
	code=0; \
	"$(PYTHON)" -m pytest tests/acceptance -m acceptance $(PYTEST_ARGS) || code=$$?; \
	if [ "$$code" = "5" ]; then \
		echo "SKIP: no acceptance tests collected yet"; \
		exit 0; \
	fi; \
	exit $$code

test-isolation:
	if ! "$(PYTHON)" -m scripts.db_check; then \
		if [ "$${CI:-}" = "true" ]; then \
			echo "FAIL: Postgres unreachable at $${POSTGRES_HOST:-localhost}:$${POSTGRES_PORT:-5432} and CI=true"; \
			exit 1; \
		fi; \
		echo "SKIP: Postgres unreachable at $${POSTGRES_HOST:-localhost}:$${POSTGRES_PORT:-5432} — run 'docker-compose up -d' to enable this target locally"; \
		exit 0; \
	fi; \
	"$(PYTHON)" -m adapters.postgres.migrator || exit 1; \
	"$(PYTHON)" -m pytest tests/isolation -m isolation $(PYTEST_ARGS)
