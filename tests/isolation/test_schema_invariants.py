"""Schema-level invariants enforced by E02's migrations.

- Versioned artifact rows are append-only (trigger + withheld grants).
- Exactly one active mask per (tenant, template, system_context).
- A mask referencing a customer-private template must be scope='customer' and
  owned by the same tenant (constraint trigger, checked across the RLS boundary).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest

from adapters.postgres.roles import ROLE_API_SERVICE
from adapters.postgres.session import tenant_transaction
from tests.isolation import helpers
from tests.isolation.conftest import RoleConnector

pytestmark = pytest.mark.isolation

_INSERT_MASK = (
    "INSERT INTO decoder_masks"
    " (tenant_id, mask_id, version, scope, template_id, template_version, system_context, active, body)"
    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
)


@pytest.fixture
def admin_conn(isolated_db: str) -> Iterator[psycopg.Connection[Any]]:
    """Superuser connection — used ONLY to prove integrity triggers bind even for
    the admin path (append-only, uniqueness, scope trigger). All tenant-isolation
    assertions in this suite run as restricted roles."""
    with psycopg.connect(isolated_db) as conn:
        yield conn


def test_versioned_artifact_body_update_is_rejected_even_for_admin(admin_conn: psycopg.Connection[Any]) -> None:
    """The append-only trigger fires for every role, superuser included."""
    for query, params in (
        ("UPDATE templates SET body = %s WHERE template_id = %s", ('{"tampered": true}', helpers.VENDOR_TEMPLATE)),
        ("UPDATE decoder_masks SET body = %s WHERE mask_id = %s", ('{"tampered": true}', helpers.VENDOR_MASK)),
    ):
        with pytest.raises(psycopg.errors.RestrictViolation):
            admin_conn.execute(query, params)
        admin_conn.rollback()


def test_versioned_artifact_delete_is_rejected_even_for_admin(admin_conn: psycopg.Connection[Any]) -> None:
    for query, params in (
        ("DELETE FROM templates WHERE template_id = %s", (helpers.VENDOR_TEMPLATE,)),
        ("DELETE FROM decoder_masks WHERE mask_id = %s", (helpers.VENDOR_MASK,)),
    ):
        with pytest.raises(psycopg.errors.RestrictViolation):
            admin_conn.execute(query, params)
        admin_conn.rollback()


def test_restricted_roles_have_no_update_or_delete_grant_on_artifacts(connect_as: RoleConnector) -> None:
    conn = connect_as(ROLE_API_SERVICE)
    with pytest.raises(psycopg.errors.InsufficientPrivilege), tenant_transaction(conn, helpers.TENANT_A):
        conn.execute(
            "UPDATE templates SET doc_class = 'x' WHERE template_id = %s", (helpers.TENANT_A_PRIVATE_TEMPLATE,)
        )
    with pytest.raises(psycopg.errors.InsufficientPrivilege), tenant_transaction(conn, helpers.TENANT_A):
        conn.execute("DELETE FROM decoder_masks WHERE mask_id = %s", (helpers.TENANT_A_MASK,))


def test_new_artifact_version_can_be_appended(connect_as: RoleConnector) -> None:
    """The sanctioned mutation path: append a new version row."""
    conn = connect_as(ROLE_API_SERVICE)
    with tenant_transaction(conn, helpers.TENANT_A):
        conn.execute(
            "INSERT INTO templates (tenant_id, template_id, version, doc_class, body)"
            " VALUES (%s, %s, 2, %s, %s) ON CONFLICT DO NOTHING",
            (helpers.TENANT_A, helpers.TENANT_A_PRIVATE_TEMPLATE, "invoice", '{"appended": true}'),
        )
        versions = helpers.scalar(
            conn, "SELECT count(*) FROM templates WHERE template_id = %s", (helpers.TENANT_A_PRIVATE_TEMPLATE,)
        )
        assert versions == 2


def test_second_active_mask_for_same_context_is_rejected(admin_conn: psycopg.Connection[Any]) -> None:
    with pytest.raises(psycopg.errors.UniqueViolation):
        admin_conn.execute(
            _INSERT_MASK,
            (
                helpers.TENANT_A,
                "mask_alpha_dup",
                1,
                "customer",
                helpers.TENANT_A_PRIVATE_TEMPLATE,
                1,
                helpers.SYSTEM_CONTEXT,
                True,
                "{}",
            ),
        )
    admin_conn.rollback()


def test_second_active_vendor_mask_for_same_context_is_rejected(admin_conn: psycopg.Connection[Any]) -> None:
    """NULLS NOT DISTINCT: the vendor baseline (tenant NULL) is single-active too."""
    with pytest.raises(psycopg.errors.UniqueViolation):
        admin_conn.execute(
            _INSERT_MASK,
            (None, "mask_vendor_dup", 1, "vendor", helpers.VENDOR_TEMPLATE, 1, helpers.SYSTEM_CONTEXT, True, "{}"),
        )
    admin_conn.rollback()


def test_inactive_mask_for_same_context_is_allowed(admin_conn: psycopg.Connection[Any]) -> None:
    admin_conn.execute(
        _INSERT_MASK + " ON CONFLICT DO NOTHING",
        (
            helpers.TENANT_A,
            "mask_alpha_inactive",
            1,
            "customer",
            helpers.TENANT_A_PRIVATE_TEMPLATE,
            1,
            helpers.SYSTEM_CONTEXT,
            False,
            "{}",
        ),
    )
    admin_conn.rollback()


def test_mask_on_private_template_with_wrong_scope_is_rejected_by_trigger(
    admin_conn: psycopg.Connection[Any], connect_as: RoleConnector
) -> None:
    # Admin path: a vendor-scope mask must not reference a customer-private template.
    with pytest.raises(psycopg.errors.CheckViolation):
        admin_conn.execute(
            _INSERT_MASK,
            (
                None,
                "mask_vendor_on_private",
                1,
                "vendor",
                helpers.TENANT_A_PRIVATE_TEMPLATE,
                1,
                "ctx_wrong",
                True,
                "{}",
            ),
        )
    admin_conn.rollback()

    # Tenant path: B authoring a mask against A's private template passes RLS
    # WITH CHECK (it is B's own row) but the constraint trigger — which checks
    # across the RLS boundary — must reject the wrong-tenant reference.
    conn = connect_as(ROLE_API_SERVICE)
    with pytest.raises(psycopg.errors.CheckViolation), tenant_transaction(conn, helpers.TENANT_B):
        conn.execute(
            _INSERT_MASK,
            (
                helpers.TENANT_B,
                "mask_bravo_on_alpha",
                1,
                "customer",
                helpers.TENANT_A_PRIVATE_TEMPLATE,
                1,
                "ctx_cross",
                True,
                "{}",
            ),
        )


def test_mask_on_own_private_template_with_customer_scope_is_accepted(connect_as: RoleConnector) -> None:
    conn = connect_as(ROLE_API_SERVICE)
    with tenant_transaction(conn, helpers.TENANT_A):
        conn.execute(
            _INSERT_MASK + " ON CONFLICT DO NOTHING",
            (
                helpers.TENANT_A,
                "mask_alpha_second_ctx",
                1,
                "customer",
                helpers.TENANT_A_PRIVATE_TEMPLATE,
                1,
                "ctx_second",
                True,
                "{}",
            ),
        )


def test_vendor_scope_mask_with_tenant_id_is_rejected(admin_conn: psycopg.Connection[Any]) -> None:
    """scope='vendor' <=> tenant_id IS NULL (CHECK constraint)."""
    with pytest.raises(psycopg.errors.CheckViolation):
        admin_conn.execute(
            _INSERT_MASK,
            (
                helpers.TENANT_A,
                "mask_vendor_with_tenant",
                1,
                "vendor",
                helpers.VENDOR_TEMPLATE,
                1,
                "ctx_bad",
                True,
                "{}",
            ),
        )
    admin_conn.rollback()
