"""Tenant context is transactional and cannot outlive its transaction.

Pool reuse is modelled the way a pool actually behaves: the same physical
connection is used for a second unit of work after the first one commits or
rolls back. Whatever tenant was set before must be gone — proven by RLS
returning zero tenant rows, not by application code.
"""

from __future__ import annotations

import pytest

from adapters.postgres.roles import ROLE_API_SERVICE
from adapters.postgres.session import (
    current_tenant_context,
    reset_tenant_context,
    tenant_transaction,
)
from tests.isolation import helpers
from tests.isolation.conftest import RoleConnector

pytestmark = pytest.mark.isolation


def test_pool_reuse_does_not_leak_tenant_context(connect_as: RoleConnector) -> None:
    conn = connect_as(ROLE_API_SERVICE)

    with tenant_transaction(conn, helpers.TENANT_A):
        assert current_tenant_context(conn) == helpers.TENANT_A
        visible = helpers.scalar(conn, "SELECT count(*) FROM documents")
        assert visible == 1, "positive control: tenant A sees its document inside the transaction"

    # Same physical connection, next pooled checkout: context must be gone.
    assert current_tenant_context(conn) is None
    assert helpers.scalar(conn, "SELECT count(*) FROM documents") == 0


def test_tenant_context_does_not_survive_rollback(connect_as: RoleConnector) -> None:
    conn = connect_as(ROLE_API_SERVICE)

    class _BoomError(Exception):
        pass

    with pytest.raises(_BoomError), tenant_transaction(conn, helpers.TENANT_A):
        assert current_tenant_context(conn) == helpers.TENANT_A
        raise _BoomError()

    assert current_tenant_context(conn) is None
    assert helpers.scalar(conn, "SELECT count(*) FROM documents") == 0


def test_reset_tenant_context_scrubs_session_scoped_value(connect_as: RoleConnector) -> None:
    """Even a session-scoped GUC (which our manager never sets) is cleared by the
    pool-reset hook, so a misbehaving caller cannot poison the next checkout."""
    conn = connect_as(ROLE_API_SERVICE)
    conn.execute("SELECT set_config('app.tenant_id', %s, false)", (helpers.TENANT_A,))
    conn.commit()
    assert current_tenant_context(conn) == helpers.TENANT_A
    assert helpers.scalar(conn, "SELECT count(*) FROM documents") == 1

    reset_tenant_context(conn)
    conn.commit()

    assert current_tenant_context(conn) is None
    assert helpers.scalar(conn, "SELECT count(*) FROM documents") == 0


def test_concurrent_connections_have_independent_tenant_contexts(connect_as: RoleConnector) -> None:
    conn_a = connect_as(ROLE_API_SERVICE)
    conn_b = connect_as(ROLE_API_SERVICE)
    with tenant_transaction(conn_a, helpers.TENANT_A), tenant_transaction(conn_b, helpers.TENANT_B):
        doc_a = helpers.scalar(conn_a, "SELECT document_id FROM documents")
        doc_b = helpers.scalar(conn_b, "SELECT document_id FROM documents")
    assert doc_a == helpers.TENANT_A_DOCUMENT
    assert doc_b == helpers.TENANT_B_DOCUMENT


def test_tenant_context_is_never_string_interpolated(connect_as: RoleConnector) -> None:
    """A hostile tenant id is inert as a bound parameter (no SQL injection path)."""
    conn = connect_as(ROLE_API_SERVICE)
    hostile = "t-alpha'; SET row_security = off; --"
    with tenant_transaction(conn, hostile):
        assert current_tenant_context(conn) == hostile, "hostile id must land as an inert bound value"
        assert helpers.scalar(conn, "SELECT count(*) FROM documents") == 0
    assert helpers.scalar(conn, "SELECT current_setting('row_security')") == "on"
