"""E00's own harness test: the fixture bundle must load into Postgres with the
exact row counts the fixture spec promises.

test_fixture_bundle_loads_and_row_counts_match — from E00's "Tests first" list
(specs/epics/E00-repo-bootstrap.md): "2 templates, 3 masks, 3 documents."

DB-backed: skips locally when no Postgres is reachable (see tests/conftest.py's
`skip_if_no_postgres`), and skips if the fixtures/sql/ bundle (owned by the
fixtures build, specs/FIXTURES-SPEC.md) has not landed yet.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import psycopg
import pytest

pytestmark = pytest.mark.integration

EXPECTED_TEMPLATES = 2
EXPECTED_MASKS = 3
EXPECTED_DOCUMENTS = 3


@pytest.fixture
def loaded_fixture_counts(
    skip_if_no_postgres: None,
    fixtures_root: Path,
    postgres_conninfo: str,
) -> dict[str, int]:
    schema_path = fixtures_root / "sql" / "schema.sql"
    loader_path = fixtures_root / "sql" / "load_fixtures.py"
    if not schema_path.exists() or not loader_path.exists():
        pytest.skip("fixtures/sql/{schema.sql,load_fixtures.py} not yet present (fixtures bundle in progress)")

    with psycopg.connect(postgres_conninfo) as conn, conn.cursor() as cur:
        cur.execute(schema_path.read_text())
        conn.commit()

    result = subprocess.run(
        [sys.executable, str(loader_path), "--dsn", postgres_conninfo],
        capture_output=True,
        text=True,
        check=False,
    )
    error_detail = f"load_fixtures.py exited {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    assert result.returncode == 0, error_detail

    def _scalar_count(cur: psycopg.Cursor[Any], table: str) -> int:
        cur.execute(f"SELECT count(*) FROM {table}")  # noqa: S608 - fixed, non-user-controlled name
        row = cur.fetchone()
        assert row is not None
        return int(row[0])

    with psycopg.connect(postgres_conninfo) as conn, conn.cursor() as cur:
        templates = _scalar_count(cur, "fixture_templates")
        masks = _scalar_count(cur, "fixture_decoder_masks")
        documents = _scalar_count(cur, "fixture_documents")

    return {"templates": templates, "masks": masks, "documents": documents}


def test_fixture_bundle_loads_and_row_counts_match(
    loaded_fixture_counts: dict[str, int],
) -> None:
    assert loaded_fixture_counts["templates"] == EXPECTED_TEMPLATES
    assert loaded_fixture_counts["masks"] == EXPECTED_MASKS
    assert loaded_fixture_counts["documents"] == EXPECTED_DOCUMENTS
