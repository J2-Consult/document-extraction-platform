"""Apply the fixture bundle's schema.sql and run load_fixtures.py against Postgres.

Invoked by `make test-acceptance`. The fixture SQL itself (`fixtures/sql/`) is
owned by the fixtures bundle (specs/FIXTURES-SPEC.md) and may not exist yet while
that work is in progress — this script degrades to a clear SKIP in that case
rather than failing the whole target.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from scripts.db_check import postgres_available

FIXTURES_SQL_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "sql"


def _conninfo() -> str:
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    dbname = os.environ.get("POSTGRES_DB", "docext")
    user = os.environ.get("POSTGRES_USER", "docext")
    password = os.environ.get("POSTGRES_PASSWORD", "docext_dev_password")
    return f"host={host} port={port} dbname={dbname} user={user} password={password}"


def _apply_schema() -> None:
    schema_path = FIXTURES_SQL_DIR / "schema.sql"
    if not schema_path.exists():
        print(f"SKIP: {schema_path} not present yet (fixtures bundle in progress)")
        return

    import psycopg

    with psycopg.connect(_conninfo()) as conn, conn.cursor() as cur:
        cur.execute(schema_path.read_text())
        conn.commit()


def _run_loader() -> int:
    loader_path = FIXTURES_SQL_DIR / "load_fixtures.py"
    if not loader_path.exists():
        print(f"SKIP: {loader_path} not present yet (fixtures bundle in progress)")
        return 0
    result = subprocess.run([sys.executable, str(loader_path)], env=os.environ.copy(), check=False)
    return result.returncode


def main() -> int:
    if not postgres_available():
        ci = os.environ.get("CI", "").lower() == "true"
        if ci:
            print("FAIL: Postgres unreachable and CI=true", file=sys.stderr)
            return 1
        print("SKIP: Postgres unreachable — skipping fixture load")
        return 0
    _apply_schema()
    return _run_loader()


if __name__ == "__main__":
    sys.exit(main())
