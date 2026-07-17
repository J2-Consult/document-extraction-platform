"""Criterion 4 core: as tenant A on restricted roles, tenant B does not exist.

Every test connects as a restricted service role (api_service / worker /
orchestrator_readonly) with tenant A's context set transactionally, and proves
at the SQL layer — no application filtering anywhere in the loop — that tenant
B's documents, decoder masks, private templates, jobs and review items can be
neither read, updated, inserted around, nor inferred from error text.
"""

from __future__ import annotations

import psycopg
import pytest

from adapters.postgres.roles import (
    ROLE_API_SERVICE,
    ROLE_ORCHESTRATOR_READONLY,
    ROLE_WORKER,
)
from adapters.postgres.session import tenant_transaction
from tests.isolation import helpers
from tests.isolation.conftest import RoleConnector

pytestmark = pytest.mark.isolation

_TENANT_ROLES = (ROLE_API_SERVICE, ROLE_WORKER, ROLE_ORCHESTRATOR_READONLY)


@pytest.mark.parametrize("role", _TENANT_ROLES)
def test_tenant_a_cannot_select_tenant_b_documents(connect_as: RoleConnector, role: str) -> None:
    conn = connect_as(role)
    with tenant_transaction(conn, helpers.TENANT_A):
        own = helpers.scalar(
            conn, "SELECT count(*) FROM documents WHERE document_id = %s", (helpers.TENANT_A_DOCUMENT,)
        )
        assert own == 1, "positive control: tenant A must see its own document"
        foreign = helpers.scalar(
            conn, "SELECT count(*) FROM documents WHERE document_id = %s", (helpers.TENANT_B_DOCUMENT,)
        )
        assert foreign == 0
        any_bravo = helpers.scalar(conn, "SELECT count(*) FROM documents WHERE tenant_id = %s", (helpers.TENANT_B,))
        assert any_bravo == 0


@pytest.mark.parametrize("role", _TENANT_ROLES)
def test_tenant_a_cannot_see_tenant_b_masks_private_templates_jobs_or_review_items(
    connect_as: RoleConnector, role: str
) -> None:
    conn = connect_as(role)
    with tenant_transaction(conn, helpers.TENANT_A):
        vendor_templates = helpers.scalar(
            conn, "SELECT count(*) FROM templates WHERE template_id = %s", (helpers.VENDOR_TEMPLATE,)
        )
        assert vendor_templates == 1, "positive control: vendor/shared template must be readable"
        for query, params in (
            ("SELECT count(*) FROM templates WHERE tenant_id = %s", (helpers.TENANT_B,)),
            ("SELECT count(*) FROM templates WHERE template_id = %s", (helpers.TENANT_B_PRIVATE_TEMPLATE,)),
            ("SELECT count(*) FROM decoder_masks WHERE tenant_id = %s", (helpers.TENANT_B,)),
            ("SELECT count(*) FROM decoder_masks WHERE mask_id = %s", (helpers.TENANT_B_MASK,)),
            ("SELECT count(*) FROM jobs WHERE tenant_id = %s", (helpers.TENANT_B,)),
            ("SELECT count(*) FROM review_items WHERE tenant_id = %s", (helpers.TENANT_B,)),
        ):
            assert helpers.scalar(conn, query, params) == 0, f"tenant B row leaked through: {query}"


def test_tenant_a_cannot_resolve_tenant_b_active_mask(connect_as: RoleConnector) -> None:
    """Mask resolution for B's context under A's tenant yields nothing (not B's mask)."""
    conn = connect_as(ROLE_ORCHESTRATOR_READONLY)
    with tenant_transaction(conn, helpers.TENANT_A):
        resolved = helpers.scalar(
            conn,
            "SELECT count(*) FROM decoder_masks WHERE template_id = %s AND system_context = %s AND active",
            (helpers.TENANT_B_PRIVATE_TEMPLATE, helpers.SYSTEM_CONTEXT),
        )
        assert resolved == 0


@pytest.mark.parametrize(
    "table_and_key",
    [
        ("documents", "document_id", helpers.TENANT_B_DOCUMENT),
        ("jobs", "job_id", helpers.TENANT_B_JOB),
        ("review_items", "review_item_id", helpers.TENANT_B_REVIEW_ITEM),
    ],
)
def test_tenant_a_cannot_update_tenant_b_rows(connect_as: RoleConnector, table_and_key: tuple[str, str, str]) -> None:
    table, key_column, key_value = table_and_key
    updates = {
        "documents": "UPDATE documents SET state = 'tampered' WHERE document_id = %s",
        "jobs": "UPDATE jobs SET state = 'tampered' WHERE job_id = %s",
        "review_items": "UPDATE review_items SET state = 'tampered' WHERE review_item_id = %s",
    }
    conn = connect_as(ROLE_API_SERVICE)
    with tenant_transaction(conn, helpers.TENANT_A):
        cursor = conn.execute(updates[table], (key_value,))
        assert cursor.rowcount == 0, f"tenant A updated tenant B's row in {table} via {key_column}"


def test_tenant_a_cannot_insert_rows_attributed_to_tenant_b(connect_as: RoleConnector) -> None:
    conn = connect_as(ROLE_API_SERVICE)
    # RLS WITH CHECK violation, SQLSTATE 42501
    with pytest.raises(psycopg.errors.InsufficientPrivilege), tenant_transaction(conn, helpers.TENANT_A):
        conn.execute(
            "INSERT INTO documents (tenant_id, document_id, version, state, body) VALUES (%s, %s, 1, %s, %s)",
            (helpers.TENANT_B, "doc_smuggled", "registered", "{}"),
        )


def test_tenant_a_cannot_insert_vendor_shared_rows(connect_as: RoleConnector) -> None:
    """Vendor rows (tenant_id NULL) are writable only via the admin path."""
    conn = connect_as(ROLE_API_SERVICE)
    with pytest.raises(psycopg.errors.InsufficientPrivilege), tenant_transaction(conn, helpers.TENANT_A):
        conn.execute(
            "INSERT INTO templates (tenant_id, template_id, version, doc_class, body) VALUES (NULL, %s, 1, %s, %s)",
            ("tmpl_smuggled_vendor", "invoice", "{}"),
        )


def test_no_tenant_context_sees_no_tenant_rows(connect_as: RoleConnector) -> None:
    conn = connect_as(ROLE_API_SERVICE)
    total = helpers.scalar(conn, "SELECT count(*) FROM documents")
    assert total == 0, "a connection without tenant context must see zero documents"


def test_error_text_cannot_be_used_to_infer_tenant_b_rows(connect_as: RoleConnector) -> None:
    """No duplicate-key oracle across tenants, and no error text leaks B's data.

    Tenant-first composite keys mean A inserting B's exact document id succeeds
    under A's tenant instead of failing with a cross-tenant unique violation —
    the classic existence oracle. Any error raised anywhere in this test must
    not contain tenant B's planted secret.
    """
    conn = connect_as(ROLE_API_SERVICE)
    try:
        with tenant_transaction(conn, helpers.TENANT_A):
            conn.execute(
                "INSERT INTO documents (tenant_id, document_id, version, state, body) VALUES (%s, %s, 1, %s, %s)",
                (helpers.TENANT_A, helpers.TENANT_B_DOCUMENT, "registered", "{}"),
            )
            conn.execute(
                "DELETE FROM documents WHERE tenant_id = %s AND document_id = %s",
                (helpers.TENANT_A, helpers.TENANT_B_DOCUMENT),
            )
    except psycopg.Error as exc:  # pragma: no cover - only on regression
        pytest.fail(f"cross-tenant duplicate-key oracle: inserting B's id under A errored: {exc}")

    with tenant_transaction(conn, helpers.TENANT_A):
        cursor = conn.execute(
            "UPDATE documents SET state = 'x' WHERE tenant_id = %s RETURNING body::text", (helpers.TENANT_B,)
        )
        rows = cursor.fetchall()
        assert rows == [], "RETURNING leaked tenant B rows"

    with pytest.raises(psycopg.errors.InsufficientPrivilege) as excinfo, tenant_transaction(conn, helpers.TENANT_A):
        conn.execute(
            "INSERT INTO documents (tenant_id, document_id, version, state, body) VALUES (%s, %s, 1, %s, %s)",
            (helpers.TENANT_B, helpers.TENANT_B_DOCUMENT, "registered", "{}"),
        )
    assert helpers.TENANT_B_CANARY not in str(excinfo.value), "error text leaked tenant B's data"
