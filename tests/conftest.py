"""Shared pytest fixtures: fixture-bundle loaders (specs/FIXTURES-SPEC.md) and
Postgres reachability helpers.

The fixtures/ bundle is built by a separate workstream and may be partially or
fully absent while that work is in progress. Fixtures here degrade to
`pytest.skip` with a clear message rather than raising, so collection always
succeeds and epics can write tests against the spec'd paths immediately.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from scripts.db_check import postgres_available

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_ROOT = REPO_ROOT / "fixtures"


@pytest.fixture(scope="session")
def fixtures_root() -> Path:
    """Path to the fixtures/ bundle root (specs/FIXTURES-SPEC.md)."""
    return FIXTURES_ROOT


@pytest.fixture(scope="session")
def postgres_conninfo() -> str:
    """libpq conninfo string built from POSTGRES_* env vars (see .env.example)."""
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    dbname = os.environ.get("POSTGRES_DB", "docext")
    user = os.environ.get("POSTGRES_USER", "docext")
    password = os.environ.get("POSTGRES_PASSWORD", "docext_dev_password")
    return f"host={host} port={port} dbname={dbname} user={user} password={password}"


@pytest.fixture(scope="session")
def pg_available() -> bool:
    """True iff a Postgres server is reachable at POSTGRES_HOST/POSTGRES_PORT."""
    return postgres_available()


@pytest.fixture
def skip_if_no_postgres(pg_available: bool) -> None:
    """Skip the current test when no Postgres server is reachable.

    Depend on this fixture (rather than `pg_available` directly) in any test
    that requires a live database connection.
    """
    if not pg_available:
        pytest.skip(
            "Postgres not reachable — set POSTGRES_HOST/POSTGRES_PORT or run "
            "'docker-compose up -d' to enable this test locally"
        )


def _load_json_or_skip(path: Path) -> dict[str, Any]:
    if not path.exists():
        pytest.skip(
            f"fixture not yet present: {path.relative_to(REPO_ROOT)} "
            "(fixtures bundle in progress — see specs/FIXTURES-SPEC.md)"
        )
    return dict(json.loads(path.read_text()))


@pytest.fixture
def load_fixture_artifact(fixtures_root: Path) -> Callable[[str], dict[str, Any]]:
    """Load fixtures/artifacts/<name>.json, e.g. load_fixture_artifact("tmpl_nvinv.v1")."""

    def _load(name: str) -> dict[str, Any]:
        return _load_json_or_skip(fixtures_root / "artifacts" / f"{name}.json")

    return _load


@pytest.fixture
def load_fixture_schema(fixtures_root: Path) -> Callable[[str], dict[str, Any]]:
    """Load fixtures/schemas/<name>.json, e.g. load_fixture_schema("template.schema")."""

    def _load(name: str) -> dict[str, Any]:
        return _load_json_or_skip(fixtures_root / "schemas" / f"{name}.json")

    return _load


@pytest.fixture
def fixture_pdf_path(fixtures_root: Path) -> Callable[[str], Path]:
    """Path to fixtures/pdfs/<name>.pdf, skipping if not yet present."""

    def _get(name: str) -> Path:
        path = fixtures_root / "pdfs" / f"{name}.pdf"
        if not path.exists():
            pytest.skip(
                f"fixture PDF not yet present: {path.relative_to(REPO_ROOT)} "
                "(fixtures bundle in progress — see specs/FIXTURES-SPEC.md)"
            )
        return path

    return _get
