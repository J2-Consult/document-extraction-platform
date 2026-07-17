"""E07 test support: seed the fixture corpus + projections into live Postgres.

Superuser credentials are used ONLY here (migrations, vendor/customer artifact
row seeding, and running the projection writer as part of seeding) — exactly
the admin paths that legitimately bypass RLS. Every assertion in the E07
integration and acceptance tests runs on connections opened as the restricted
service roles.

Shared by tests/integration/test_projections_postgres.py and the criterion
7/12 acceptance tests (same pattern as tests/isolation/helpers.py, which the
criterion-4 acceptance test imports).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Json

from adapters.postgres.migrator import apply_migrations
from adapters.postgres.projection_sink import PostgresProjectionSink
from services.projection.writer import ProjectionWriter

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_DIR = REPO_ROOT / "fixtures" / "artifacts"

TENANT_NORDVIK = "t-nordvik"
TEMPLATE_FIXTURES = ("tmpl_nvinv.v1", "tmpl_mbr.v1")
MASK_FIXTURES = ("mask_nvvendor.v1", "mask_nvcust.v1", "mask_mbrvendor.v1")
DOCUMENT_FIXTURES = ("doc_nv20260042", "doc_nv20260043", "doc_mbr001")
CONTENT_FIXTURES = ("content_nv20260042.v1", "content_nv20260043.v1", "content_mbr001.v1")
CONTENT_BY_DOCUMENT = {
    "doc_nv20260042": "content_nv20260042.v1",
    "doc_nv20260043": "content_nv20260043.v1",
    "doc_mbr001": "content_mbr001.v1",
}
# Per specs/FIXTURES-SPEC.md, mask_mbrvendor is "not active by default".
INACTIVE_MASK_IDS = frozenset({"mask_mbrvendor"})

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
INSERT INTO documents
    (tenant_id, document_id, version, template_id, template_version,
     content_id, content_version, source_sha256, state, body)
VALUES (%s, %s, 1, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT DO NOTHING
"""


def load_artifact(name: str) -> dict[str, Any]:
    """Load fixtures/artifacts/<name>.json as a plain dict (wire form)."""
    return dict(json.loads((ARTIFACTS_DIR / f"{name}.json").read_text(encoding="utf-8")))


def _seed_templates(conn: psycopg.Connection[Any]) -> None:
    for name in TEMPLATE_FIXTURES:
        artifact = load_artifact(name)
        body = artifact["body"]
        conn.execute(
            _INSERT_TEMPLATE,
            (
                artifact["tenant_id"],
                artifact["artifact_id"],
                artifact["version"],
                body["doc_class"],
                body["fingerprint"],
                Json(body),
            ),
        )


def _seed_masks(conn: psycopg.Connection[Any]) -> None:
    for name in MASK_FIXTURES:
        artifact = load_artifact(name)
        body = artifact["body"]
        conn.execute(
            _INSERT_MASK,
            (
                artifact["tenant_id"],
                artifact["artifact_id"],
                artifact["version"],
                body["scope"],
                body["template_ref"]["template_id"],
                body["template_ref"]["version"],
                body["system_context"],
                artifact["artifact_id"] not in INACTIVE_MASK_IDS,
                Json(body),
            ),
        )


def _seed_documents(conn: psycopg.Connection[Any]) -> None:
    for name in DOCUMENT_FIXTURES:
        registration = load_artifact(name)
        template_ref = registration["template_ref"]
        conn.execute(
            _INSERT_DOCUMENT,
            (
                registration["tenant_id"],
                registration["document_id"],
                template_ref["template_id"] if template_ref else None,
                template_ref["version"] if template_ref else None,
                registration["content_ref"]["content_id"],
                registration["content_ref"]["version"],
                registration["source"]["sha256"],
                registration["state"],
                Json(registration),
            ),
        )


def project_all_artifacts(conn: psycopg.Connection[Any]) -> None:
    """Run the projection writer over every fixture content + mask artifact."""
    writer = ProjectionWriter(PostgresProjectionSink(conn))
    for name in CONTENT_FIXTURES:
        writer.project_content(load_artifact(name))
    for name in MASK_FIXTURES:
        writer.project_mask(load_artifact(name))


def seed_projection_corpus(admin_conninfo: str) -> None:
    """Migrations + fixture artifact rows + projections (admin path; idempotent)."""
    apply_migrations(admin_conninfo)
    with psycopg.connect(admin_conninfo) as conn:
        _seed_templates(conn)
        _seed_masks(conn)
        _seed_documents(conn)
        project_all_artifacts(conn)
        conn.commit()
