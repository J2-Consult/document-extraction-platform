"""E08 integration suite: lifecycle repository atomicity + the consultant
worklist under the `synthesis` role, against live Postgres.

Connection roles
----------------
- The `PostgresLifecycleRepository` tests run on the ADMIN connection: under
  E02's RLS design, vendor/shared artifact rows (tenant_id NULL) are written
  by the admin path only — no service role may insert or flip them — and
  vendor lifecycle operations are exactly that admin path (vendor-mask
  publication requires the admin scope at the service boundary too).
- The worklist assertions connect as the restricted `synthesis` role and
  prove the E02 invariant from E08's side: shared vendor rows are readable,
  customer masks and customer-private templates are invisible even with a
  tenant context set.

Appends use per-run unique artifact ids: versioned artifact rows are
append-only by trigger (no DELETE, ever), so re-running must never collide.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import psycopg
import pytest

from adapters.postgres.lifecycle_repo import PostgresLifecycleRepository
from adapters.postgres.migrator import admin_conninfo, apply_migrations
from adapters.postgres.roles import ROLE_SYNTHESIS, role_password
from adapters.postgres.session import tenant_transaction
from domain.artifacts.mask import DecoderMaskArtifact, DecoderMaskBody, MaskRef
from domain.artifacts.template import TemplateArtifact, TemplateBody, TemplateRef
from ports.lifecycle import ChangeRecord, DuplicateVersionError, ReleaseUnit, UnknownReleaseRefError
from services.lifecycle.worklist import uncovered_elements
from tests.integration import projections_corpus
from tests.isolation import helpers
from tests.unit.services.lifecycle._fixtures import build_tmpl_nvinv_v2, load_mask, load_template

pytestmark = pytest.mark.integration

CHANGE = ChangeRecord(actor="vendor-consultant-1", reason="integration test", at=0.0)


@pytest.fixture(scope="module", autouse=True)
def _migrated_database(pg_available: bool) -> None:
    if not pg_available:
        pytest.skip("Postgres not reachable — run 'docker-compose up -d'")
    apply_migrations(admin_conninfo())


@pytest.fixture
def admin_conn() -> Iterator[psycopg.Connection[Any]]:
    with psycopg.connect(admin_conninfo()) as conn:
        yield conn


def _unique_suffix() -> str:
    return uuid4().hex[:8]


def _rename_template(body: TemplateBody, template_id: str, version: int) -> TemplateArtifact:
    return TemplateArtifact(
        artifact_id=template_id,
        version=version,
        tenant_id=None,
        created_at=datetime(2026, 7, 1, tzinfo=UTC),
        body=body.model_copy(update={"template_id": template_id, "version": version}),
    )


def _rename_mask(
    body: DecoderMaskBody, mask_id: str, version: int, template_id: str, template_version: int
) -> DecoderMaskArtifact:
    renamed = body.model_copy(
        update={
            "mask_id": mask_id,
            "version": version,
            "template_ref": TemplateRef(template_id=template_id, version=template_version),
        }
    )
    return DecoderMaskArtifact(
        artifact_id=mask_id,
        version=version,
        tenant_id=None,
        created_at=datetime(2026, 7, 1, tzinfo=UTC),
        body=renamed,
    )


def _count_active(conn: psycopg.Connection[Any], template_id: str) -> int:
    row = conn.execute(
        "SELECT count(*) FROM decoder_masks WHERE template_id = %s AND active", (template_id,)
    ).fetchone()
    assert row is not None
    return int(row[0])


def test_append_and_read_back_round_trips_the_artifacts(admin_conn: psycopg.Connection[Any]) -> None:
    suffix = _unique_suffix()
    template_id, mask_id = f"tmpl_e08_{suffix}", f"mask_e08_{suffix}"
    repository = PostgresLifecycleRepository(admin_conn)
    template = _rename_template(load_template("tmpl_nvinv.v1").body, template_id, 1)
    mask = _rename_mask(load_mask("mask_nvvendor.v1").body, mask_id, 1, template_id, 1)

    repository.append_template_version(template, CHANGE)
    repository.append_mask_version(mask, CHANGE)
    admin_conn.commit()

    stored_template = repository.get_template(TemplateRef(template_id=template_id, version=1))
    stored_mask = repository.get_mask(MaskRef(mask_id=mask_id, version=1))
    assert stored_template is not None and stored_template.body == template.body
    assert stored_mask is not None and stored_mask.body == mask.body
    assert repository.list_template_versions(template_id) == (1,)
    assert repository.list_mask_versions(mask_id) == (1,)

    with pytest.raises(DuplicateVersionError):  # append-only: same version never overwrites
        repository.append_template_version(template, CHANGE)
    admin_conn.rollback()


def test_release_unit_activation_is_atomic_on_live_postgres(admin_conn: psycopg.Connection[Any]) -> None:
    suffix = _unique_suffix()
    template_id, mask_id = f"tmpl_e08_{suffix}", f"mask_e08_{suffix}"
    repository = PostgresLifecycleRepository(admin_conn)
    v1_body = load_template("tmpl_nvinv.v1").body
    v2_body = build_tmpl_nvinv_v2().model_copy(update={"template_id": template_id})
    repository.append_template_version(_rename_template(v1_body, template_id, 1), CHANGE)
    repository.append_template_version(
        TemplateArtifact(
            artifact_id=template_id,
            version=2,
            tenant_id=None,
            created_at=datetime(2026, 7, 1, tzinfo=UTC),
            body=v2_body,
        ),
        CHANGE,
    )
    mask_body = load_mask("mask_nvvendor.v1").body
    repository.append_mask_version(_rename_mask(mask_body, mask_id, 1, template_id, 1), CHANGE)
    repository.append_mask_version(_rename_mask(mask_body, mask_id, 2, template_id, 2), CHANGE)
    admin_conn.commit()

    # Drafts are appended INACTIVE; activation is a separate, atomic step.
    assert _count_active(admin_conn, template_id) == 0
    repository.activate_release_unit(
        ReleaseUnit(
            template_ref=TemplateRef(template_id=template_id, version=1),
            mask_refs=(MaskRef(mask_id=mask_id, version=1),),
        ),
        CHANGE,
    )
    admin_conn.commit()
    active = repository.get_active_mask(template_id, "erp_invoice", tenant_id=None)
    assert active is not None and active.version == 1

    # Pin the v1 bodies a processed document would reference.
    pinned_template = repository.get_template(TemplateRef(template_id=template_id, version=1))
    pinned_mask = repository.get_mask(MaskRef(mask_id=mask_id, version=1))
    assert pinned_template is not None and pinned_mask is not None
    template_snapshot = pinned_template.body.model_dump(by_alias=True)
    mask_snapshot = pinned_mask.body.model_dump(by_alias=True)

    # ATOMICITY: a unit whose second ref is unknown must roll back the first
    # mask's activation flip — all-or-nothing, observable in the database.
    bad_unit = ReleaseUnit(
        template_ref=TemplateRef(template_id=template_id, version=2),
        mask_refs=(MaskRef(mask_id=mask_id, version=2), MaskRef(mask_id="mask_missing", version=1)),
    )
    with pytest.raises(UnknownReleaseRefError):
        repository.activate_release_unit(bad_unit, CHANGE)
    admin_conn.rollback()
    active_after_failure = repository.get_active_mask(template_id, "erp_invoice", tenant_id=None)
    assert active_after_failure is not None
    assert active_after_failure.version == 1, "failed activation must leave v1 active (rolled back)"
    assert _count_active(admin_conn, template_id) == 1

    # The good unit activates template v2 + mask v2 together.
    repository.activate_release_unit(
        ReleaseUnit(
            template_ref=TemplateRef(template_id=template_id, version=2),
            mask_refs=(MaskRef(mask_id=mask_id, version=2),),
        ),
        CHANGE,
    )
    admin_conn.commit()
    active_v2 = repository.get_active_mask(template_id, "erp_invoice", tenant_id=None)
    assert active_v2 is not None and active_v2.version == 2
    assert _count_active(admin_conn, template_id) == 1, "exactly one active mask per context"

    # v1 documents stay reproducible: pinned versions are byte-for-byte intact.
    template_after = repository.get_template(TemplateRef(template_id=template_id, version=1))
    mask_after = repository.get_mask(MaskRef(mask_id=mask_id, version=1))
    assert template_after is not None and template_after.body.model_dump(by_alias=True) == template_snapshot
    assert mask_after is not None and mask_after.body.model_dump(by_alias=True) == mask_snapshot


def test_consultant_worklist_runs_under_the_synthesis_role_on_shared_rows_only() -> None:
    projections_corpus.seed_projection_corpus(admin_conninfo())  # fixture corpus incl. customer mask
    helpers.seed_isolation_rows(admin_conninfo())  # customer-private templates + customer masks

    conninfo = helpers.conninfo_for_role(ROLE_SYNTHESIS, role_password(ROLE_SYNTHESIS))
    with psycopg.connect(conninfo) as conn:
        # The worklist inputs are readable: shared vendor template + vendor mask.
        template_row = conn.execute(
            "SELECT body FROM templates WHERE template_id = %s AND version = %s", ("tmpl_nvinv", 1)
        ).fetchone()
        mask_row = conn.execute(
            "SELECT body FROM decoder_masks WHERE mask_id = %s AND version = %s", ("mask_nvvendor", 1)
        ).fetchone()
        assert template_row is not None, "synthesis must see the shared vendor template"
        assert mask_row is not None, "synthesis must see the vendor baseline mask"

        worklist = uncovered_elements(
            TemplateBody.model_validate(template_row[0]), DecoderMaskBody.model_validate(mask_row[0])
        )
        assert [item.element_id for item in worklist] == ["el_customer_name", "el_vendor_name"]

        # The E02 invariant, proven from E08's side: customer-scope masks and
        # customer-private templates are invisible to synthesis...
        assert helpers.scalar(conn, "SELECT count(*) FROM decoder_masks WHERE scope = 'customer'") == 0
        assert helpers.scalar(conn, "SELECT count(*) FROM templates WHERE tenant_id IS NOT NULL") == 0

        # ...even when a tenant context is set (policies are role-scoped).
        with tenant_transaction(conn, projections_corpus.TENANT_NORDVIK):
            assert helpers.scalar(conn, "SELECT count(*) FROM decoder_masks WHERE scope = 'customer'") == 0
            assert helpers.scalar(conn, "SELECT count(*) FROM templates WHERE tenant_id IS NOT NULL") == 0
