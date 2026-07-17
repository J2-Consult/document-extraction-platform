"""The absolute isolation invariant (architecture §7.4, epic E02).

The `synthesis` role works across tenants on SHARED knowledge only: vendor
templates (tenant_id IS NULL) and vendor-scope masks. It must not be able to
read any customer-scope mask or customer-private template — even when it sets
`app.tenant_id` itself — and it has no access at all to operational tables.
"""

from __future__ import annotations

import psycopg
import pytest

from adapters.postgres.roles import ROLE_SYNTHESIS
from adapters.postgres.session import tenant_transaction
from tests.isolation import helpers
from tests.isolation.conftest import RoleConnector

pytestmark = pytest.mark.isolation


def test_synthesis_role_cannot_select_customer_masks_or_private_templates(connect_as: RoleConnector) -> None:
    conn = connect_as(ROLE_SYNTHESIS)

    vendor_masks = helpers.scalar(conn, "SELECT count(*) FROM decoder_masks WHERE scope = 'vendor'")
    assert vendor_masks >= 1, "positive control: synthesis must read vendor-scope masks"
    vendor_templates = helpers.scalar(conn, "SELECT count(*) FROM templates WHERE tenant_id IS NULL")
    assert vendor_templates >= 1, "positive control: synthesis must read vendor/shared templates"

    assert helpers.scalar(conn, "SELECT count(*) FROM decoder_masks WHERE scope = 'customer'") == 0
    assert helpers.scalar(conn, "SELECT count(*) FROM decoder_masks WHERE tenant_id IS NOT NULL") == 0
    assert helpers.scalar(conn, "SELECT count(*) FROM templates WHERE tenant_id IS NOT NULL") == 0
    assert helpers.scalar(conn, "SELECT count(*) FROM decoder_masks WHERE mask_id = %s", (helpers.TENANT_B_MASK,)) == 0


@pytest.mark.parametrize("tenant", [helpers.TENANT_A, helpers.TENANT_B])
def test_synthesis_restriction_holds_even_with_tenant_context_set(connect_as: RoleConnector, tenant: str) -> None:
    """Setting app.tenant_id must not widen the synthesis role's row visibility."""
    conn = connect_as(ROLE_SYNTHESIS)
    with tenant_transaction(conn, tenant):
        assert helpers.scalar(conn, "SELECT count(*) FROM decoder_masks WHERE scope = 'customer'") == 0
        assert helpers.scalar(conn, "SELECT count(*) FROM templates WHERE tenant_id IS NOT NULL") == 0


@pytest.mark.parametrize("table", ["documents", "jobs", "review_items"])
def test_synthesis_role_has_no_access_to_operational_tables(connect_as: RoleConnector, table: str) -> None:
    queries = {
        "documents": "SELECT count(*) FROM documents",
        "jobs": "SELECT count(*) FROM jobs",
        "review_items": "SELECT count(*) FROM review_items",
    }
    conn = connect_as(ROLE_SYNTHESIS)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(queries[table])


def test_synthesis_role_cannot_write_shared_knowledge(connect_as: RoleConnector) -> None:
    conn = connect_as(ROLE_SYNTHESIS)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(
            "INSERT INTO templates (tenant_id, template_id, version, doc_class, body) VALUES (NULL, %s, 1, %s, %s)",
            ("tmpl_synthesis_write", "invoice", "{}"),
        )
