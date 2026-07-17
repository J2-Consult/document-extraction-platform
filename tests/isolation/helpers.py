"""Shared helpers for the E02 tenant-isolation suite.

Also imported by the criterion-4 acceptance test, so everything needed to bring
the live database into a testable state (migrations applied, deterministic
two-tenant seed rows present) lives here.

Superuser credentials are used ONLY inside :func:`prepare_isolated_database`
(applying migrations, creating roles, seeding rows across tenants — exactly the
admin paths that legitimately bypass RLS). Every assertion in the suite runs on
connections opened as the restricted service roles.
"""

from __future__ import annotations

import os
from typing import Any

import psycopg
from psycopg.types.json import Json

from adapters.postgres.migrator import apply_migrations

TENANT_A = "t-alpha"
TENANT_B = "t-bravo"

VENDOR_TEMPLATE = "tmpl_vendor"
TENANT_A_PRIVATE_TEMPLATE = "tmpl_alpha_private"
TENANT_B_PRIVATE_TEMPLATE = "tmpl_bravo_private"

VENDOR_MASK = "mask_vendor"
TENANT_A_MASK = "mask_alpha"
TENANT_B_MASK = "mask_bravo"

TENANT_A_DOCUMENT = "doc_alpha_1"
TENANT_B_DOCUMENT = "doc_bravo_1"
TENANT_A_JOB = "job_alpha_1"
TENANT_B_JOB = "job_bravo_1"
TENANT_A_REVIEW_ITEM = "rev_alpha_1"
TENANT_B_REVIEW_ITEM = "rev_bravo_1"

# Canary planted in tenant B's rows; no error message or result visible to
# tenant A may ever contain it. Not a credential — a leak-detection marker.
TENANT_B_CANARY = "bravo-canary-marker"

SYSTEM_CONTEXT = "erp_invoice"

_INSERT_TEMPLATE = """
INSERT INTO templates (tenant_id, template_id, version, doc_class, fingerprint, body)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT DO NOTHING
"""

_INSERT_MASK = """
INSERT INTO decoder_masks
    (tenant_id, mask_id, version, scope, template_id, template_version, system_context, active, body)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT DO NOTHING
"""

_INSERT_DOCUMENT = """
INSERT INTO documents (tenant_id, document_id, version, template_id, template_version, state, body)
VALUES (%s, %s, %s, %s, %s, %s, %s)
"""

_INSERT_JOB = """
INSERT INTO jobs (tenant_id, job_id, document_id, kind, state, body)
VALUES (%s, %s, %s, %s, %s, %s)
"""

_INSERT_REVIEW_ITEM = """
INSERT INTO review_items (tenant_id, review_item_id, document_id, element_id, state, body)
VALUES (%s, %s, %s, %s, %s, %s)
"""


def conninfo_for_role(user: str, password: str) -> str:
    """libpq conninfo for `user` against the harness database (POSTGRES_* env)."""
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    dbname = os.environ.get("POSTGRES_DB", "docext")
    return f"host={host} port={port} dbname={dbname} user={user} password={password}"


def _seed_templates(conn: psycopg.Connection[Any]) -> None:
    rows = [
        (None, VENDOR_TEMPLATE, 1, "invoice", "fpv1:sha256:" + "0" * 64, Json({"kind": "vendor baseline"})),
        (TENANT_A, TENANT_A_PRIVATE_TEMPLATE, 1, "invoice", None, Json({"kind": "alpha private"})),
        (TENANT_B, TENANT_B_PRIVATE_TEMPLATE, 1, "invoice", None, Json({"canary": TENANT_B_CANARY})),
    ]
    for row in rows:
        conn.execute(_INSERT_TEMPLATE, row)


def _seed_masks(conn: psycopg.Connection[Any]) -> None:
    rows = [
        (None, VENDOR_MASK, 1, "vendor", VENDOR_TEMPLATE, 1, SYSTEM_CONTEXT, True, Json({"entries": []})),
        (
            TENANT_A,
            TENANT_A_MASK,
            1,
            "customer",
            TENANT_A_PRIVATE_TEMPLATE,
            1,
            SYSTEM_CONTEXT,
            True,
            Json({"entries": []}),
        ),
        (
            TENANT_B,
            TENANT_B_MASK,
            1,
            "customer",
            TENANT_B_PRIVATE_TEMPLATE,
            1,
            SYSTEM_CONTEXT,
            True,
            Json({"canary": TENANT_B_CANARY}),
        ),
    ]
    for row in rows:
        conn.execute(_INSERT_MASK, row)


def _seed_operational_rows(conn: psycopg.Connection[Any]) -> None:
    conn.execute("DELETE FROM review_items WHERE tenant_id IN (%s, %s)", (TENANT_A, TENANT_B))
    conn.execute("DELETE FROM jobs WHERE tenant_id IN (%s, %s)", (TENANT_A, TENANT_B))
    conn.execute("DELETE FROM documents WHERE tenant_id IN (%s, %s)", (TENANT_A, TENANT_B))
    conn.execute(
        _INSERT_DOCUMENT,
        (TENANT_A, TENANT_A_DOCUMENT, 1, TENANT_A_PRIVATE_TEMPLATE, 1, "processed", Json({"kind": "alpha doc"})),
    )
    canary_body = Json({"canary": TENANT_B_CANARY})
    conn.execute(
        _INSERT_DOCUMENT,
        (TENANT_B, TENANT_B_DOCUMENT, 1, TENANT_B_PRIVATE_TEMPLATE, 1, "processed", canary_body),
    )
    conn.execute(_INSERT_JOB, (TENANT_A, TENANT_A_JOB, TENANT_A_DOCUMENT, "extract", "queued", Json({})))
    conn.execute(_INSERT_JOB, (TENANT_B, TENANT_B_JOB, TENANT_B_DOCUMENT, "extract", "queued", canary_body))
    conn.execute(
        _INSERT_REVIEW_ITEM, (TENANT_A, TENANT_A_REVIEW_ITEM, TENANT_A_DOCUMENT, "el_total", "pending", Json({}))
    )
    conn.execute(
        _INSERT_REVIEW_ITEM,
        (TENANT_B, TENANT_B_REVIEW_ITEM, TENANT_B_DOCUMENT, "el_total", "pending", Json({"canary": TENANT_B_CANARY})),
    )


def seed_isolation_rows(admin_conninfo: str) -> None:
    """Seed deterministic two-tenant rows (admin/superuser path; idempotent)."""
    with psycopg.connect(admin_conninfo) as conn:
        _seed_templates(conn)
        _seed_masks(conn)
        _seed_operational_rows(conn)
        conn.commit()


def prepare_isolated_database(admin_conninfo: str) -> None:
    """Apply migrations (schema + RLS + roles) and seed the two-tenant corpus."""
    apply_migrations(admin_conninfo)
    seed_isolation_rows(admin_conninfo)


def scalar(conn: psycopg.Connection[Any], query: str, params: tuple[Any, ...] = ()) -> Any:
    """Run a single-value query and return the first column of the first row."""
    row = conn.execute(query, params).fetchone()
    assert row is not None
    return row[0]
