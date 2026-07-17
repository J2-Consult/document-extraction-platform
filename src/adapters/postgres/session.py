"""Transactional tenant-context management for Postgres connections (epic E02).

Row-level-security policies key on ``current_setting('app.tenant_id', true)``.
This module is the ONLY sanctioned way to set that GUC, and it sets it as a
*transaction-local* value via ``set_config(..., is_local => true)`` so the
context:

- is established inside an explicit transaction and torn down automatically on
  COMMIT or ROLLBACK — it cannot leak past the transaction boundary; and
- is never string-interpolated: the tenant id is bound as a query parameter to
  ``set_config`` (a plain function call), so no SQL is built from strings.

Pool hygiene: because the context is transaction-local, a connection returned to
a pool after its transaction ends carries no tenant context. ``reset_tenant_context``
is provided as an explicit belt-and-suspenders reset callback for pool
configuration (and to scrub any accidentally session-scoped value).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg

TENANT_GUC = "app.tenant_id"

_SET_LOCAL_TENANT = "SELECT set_config(%s, %s, true)"
_RESET_TENANT = "SELECT set_config(%s, '', false)"
_CURRENT_TENANT = "SELECT current_setting(%s, true)"


def _apply_local_tenant(conn: psycopg.Connection[Any], tenant_id: str) -> None:
    """Set the tenant GUC transaction-locally on an already-open transaction."""
    conn.execute(_SET_LOCAL_TENANT, (TENANT_GUC, tenant_id))


@contextmanager
def tenant_transaction(conn: psycopg.Connection[Any], tenant_id: str) -> Iterator[psycopg.Connection[Any]]:
    """Open a transaction with ``app.tenant_id`` bound for its whole lifetime.

    The context is set with ``set_config(..., is_local => true)``: it applies only
    until the surrounding transaction commits or rolls back, then disappears. RLS
    policies therefore see the tenant for every statement in the block and nothing
    afterwards.
    """
    with conn.transaction():
        _apply_local_tenant(conn, tenant_id)
        yield conn


def reset_tenant_context(conn: psycopg.Connection[Any]) -> None:
    """Scrub any tenant context from a connection before it is reused.

    Transaction-local context is already gone after COMMIT/ROLLBACK; this clears a
    session-scoped value too, so it is safe to register as a connection-pool reset
    callback (defence in depth against leakage across pooled checkouts).
    """
    conn.execute(_RESET_TENANT, (TENANT_GUC,))


def current_tenant_context(conn: psycopg.Connection[Any]) -> str | None:
    """Return the effective ``app.tenant_id`` (``None``/empty when unset)."""
    row = conn.execute(_CURRENT_TENANT, (TENANT_GUC,)).fetchone()
    if row is None:
        return None
    value = row[0]
    return None if value in (None, "") else str(value)
