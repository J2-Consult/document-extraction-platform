"""Minimal psycopg-based migration runner for the E02 schema (no alembic).

Applies every ``migrations/NNNN_*.sql`` file in lexical order as the admin
(superuser) connection, after ensuring the four restricted service roles exist
with passwords from the environment. All migration files are idempotent
(``IF NOT EXISTS`` / ``CREATE OR REPLACE`` / ``DROP ... IF EXISTS`` +
revoke-then-grant), so the runner simply re-applies the full set on every run —
safe against a dirty database, no bookkeeping table needed at this scale.

SQL discipline: migration DDL is static SQL read from files; the only composed
statements are ``CREATE/ALTER ROLE`` (whose name and password cannot be bound
parameters in PostgreSQL) and they are built exclusively with ``psycopg.sql``
``Identifier``/``Literal`` composition — never string formatting. Role existence
checks are parameterized queries.

Run via ``python -m adapters.postgres.migrator`` (used by ``make test-isolation``).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql

from adapters.postgres.roles import ALL_ROLES, role_password

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"

_ROLE_EXISTS = "SELECT 1 FROM pg_roles WHERE rolname = %s"
_CREATE_ROLE = sql.SQL("CREATE ROLE {} WITH LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD {}")
_ALTER_ROLE = sql.SQL("ALTER ROLE {} WITH LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD {}")


def admin_conninfo() -> str:
    """Admin conninfo from POSTGRES_* env vars (migrations + role creation only)."""
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    dbname = os.environ.get("POSTGRES_DB", "docext")
    user = os.environ.get("POSTGRES_USER", "docext")
    password = os.environ.get("POSTGRES_PASSWORD", "docext_dev_password")
    return f"host={host} port={port} dbname={dbname} user={user} password={password}"


def ensure_roles(conn: psycopg.Connection[Any]) -> None:
    """Create (or converge) the restricted service roles; never widens privileges."""
    for role in ALL_ROLES:
        statement = _ALTER_ROLE if conn.execute(_ROLE_EXISTS, (role,)).fetchone() else _CREATE_ROLE
        conn.execute(statement.format(sql.Identifier(role), sql.Literal(role_password(role))))


def migration_files(migrations_dir: Path | None = None) -> list[Path]:
    """Numbered migration files in application order."""
    directory = migrations_dir or MIGRATIONS_DIR
    return sorted(directory.glob("[0-9][0-9][0-9][0-9]_*.sql"))


def apply_migrations(conninfo: str | None = None, migrations_dir: Path | None = None) -> list[str]:
    """Ensure roles, then apply every migration file; returns applied file names."""
    files = migration_files(migrations_dir)
    if not files:
        raise FileNotFoundError(f"no migration files found in {migrations_dir or MIGRATIONS_DIR}")
    applied: list[str] = []
    with psycopg.connect(conninfo or admin_conninfo()) as conn:
        ensure_roles(conn)
        conn.commit()
        for path in files:
            conn.execute(path.read_text(encoding="utf-8"))  # static DDL from file
            conn.commit()
            applied.append(path.name)
    return applied


def main() -> int:
    applied = apply_migrations()
    for name in applied:
        print(f"applied {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
