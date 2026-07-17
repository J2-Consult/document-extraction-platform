"""Fixtures for the E02 tenant-isolation suite.

`isolated_db` uses the superuser conninfo exactly once per session, to apply
migrations (which create the restricted roles) and seed a deterministic
two-tenant corpus. Every test asserts through `connect_as(...)` connections,
which authenticate as the restricted service roles — never the superuser.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import psycopg
import pytest

from adapters.postgres.roles import role_password
from tests.isolation import helpers

RoleConnector = Callable[[str], psycopg.Connection[Any]]


@pytest.fixture(scope="session")
def isolated_db(postgres_conninfo: str, pg_available: bool) -> str:
    """Migrated + seeded database; returns the admin conninfo (setup only)."""
    if not pg_available:
        pytest.skip(
            "Postgres not reachable — set POSTGRES_HOST/POSTGRES_PORT or run "
            "'docker-compose up -d' to enable the isolation suite locally"
        )
    helpers.prepare_isolated_database(postgres_conninfo)
    return postgres_conninfo


@pytest.fixture
def connect_as(isolated_db: str) -> Iterator[RoleConnector]:
    """Open (and later close) a connection authenticated as a restricted role."""
    opened: list[psycopg.Connection[Any]] = []

    def _connect(role: str) -> psycopg.Connection[Any]:
        conn = psycopg.connect(helpers.conninfo_for_role(role, role_password(role)))
        opened.append(conn)
        return conn

    yield _connect
    for conn in opened:
        conn.close()
