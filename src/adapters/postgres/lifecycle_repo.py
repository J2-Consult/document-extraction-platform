"""PostgresLifecycleRepository (epic E08): thin adapter for the
`ports.lifecycle.LifecycleRepository` port over E02's `templates` /
`decoder_masks` tables.

- Appends are plain INSERTs; the tables' append-only trigger plus the unique
  identity indexes make overwrite unrepresentable — a duplicate
  (artifact_id, version) surfaces as `DuplicateVersionError`.
- Mask versions are appended INACTIVE (drafts). `activate_release_unit` is
  one database transaction: each mask ref is resolved with FOR UPDATE, the
  context's currently active mask is flipped off and the new one on; any
  unknown ref raises and the transaction ROLLS BACK every prior flip —
  all-or-nothing, which is what the E08 integration suite proves.
- Runs on the caller's connection. Vendor/shared rows (tenant_id NULL) are
  writable only by the admin path under E02's RLS policies — vendor lifecycle
  operations ARE that admin path (the service boundary additionally requires
  the admin scope for vendor-mask publication).
- Actor identity (`ChangeRecord`) is enforced at the port/service level and
  unit-tested against the fake; persisting it here needs an additive audit
  migration (proposed in the E08 PR, not written — E02 owns migrations).
"""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg import errors
from psycopg.types.json import Json

from domain.artifacts.mask import DecoderMaskArtifact, DecoderMaskBody, MaskRef
from domain.artifacts.template import TemplateArtifact, TemplateBody, TemplateRef
from ports.lifecycle import ChangeRecord, DuplicateVersionError, ReleaseUnit, UnknownReleaseRefError

_INSERT_TEMPLATE = """
INSERT INTO templates (tenant_id, template_id, version, doc_class, fingerprint, body)
VALUES (%s, %s, %s, %s, %s, %s)
"""

_INSERT_MASK = """
INSERT INTO decoder_masks
    (tenant_id, mask_id, version, scope, template_id, template_version, system_context, active, body)
VALUES (%s, %s, %s, %s, %s, %s, %s, false, %s)
"""

_SELECT_TEMPLATE = """
SELECT tenant_id, created_at, body FROM templates
WHERE template_id = %s AND version = %s
"""

_SELECT_MASK = """
SELECT tenant_id, created_at, body FROM decoder_masks
WHERE mask_id = %s AND version = %s
"""

_LOCK_MASK_CONTEXT = """
SELECT tenant_id, template_id, system_context FROM decoder_masks
WHERE mask_id = %s AND version = %s
FOR UPDATE
"""

_TEMPLATE_EXISTS = "SELECT 1 FROM templates WHERE template_id = %s AND version = %s"

_DEACTIVATE_CONTEXT = """
UPDATE decoder_masks SET active = false
WHERE tenant_id IS NOT DISTINCT FROM %s AND template_id = %s AND system_context = %s AND active
"""

_ACTIVATE_MASK = "UPDATE decoder_masks SET active = true WHERE mask_id = %s AND version = %s"

_SELECT_ACTIVE_MASK = """
SELECT tenant_id, created_at, body FROM decoder_masks
WHERE template_id = %s AND system_context = %s AND tenant_id IS NOT DISTINCT FROM %s AND active
"""

_LIST_TEMPLATE_VERSIONS = "SELECT version FROM templates WHERE template_id = %s ORDER BY version"
_LIST_MASK_VERSIONS = "SELECT version FROM decoder_masks WHERE mask_id = %s ORDER BY version"


class PostgresLifecycleRepository:
    """One connection, parameterized SQL only, no schema of its own."""

    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self._conn = conn

    def append_template_version(self, artifact: TemplateArtifact, change: ChangeRecord) -> None:
        body = artifact.body
        try:
            self._conn.execute(
                _INSERT_TEMPLATE,
                (
                    artifact.tenant_id,
                    body.template_id,
                    body.version,
                    body.doc_class,
                    body.fingerprint,
                    Json(body.model_dump(by_alias=True, mode="json")),
                ),
            )
        except errors.UniqueViolation as exc:
            raise DuplicateVersionError(
                f"template {body.template_id} v{body.version} already exists (append-only)"
            ) from exc

    def append_mask_version(self, artifact: DecoderMaskArtifact, change: ChangeRecord) -> None:
        body = artifact.body
        try:
            self._conn.execute(
                _INSERT_MASK,
                (
                    artifact.tenant_id,
                    body.mask_id,
                    body.version,
                    body.scope,
                    body.template_ref.template_id,
                    body.template_ref.version,
                    body.system_context,
                    Json(body.model_dump(by_alias=True, mode="json")),
                ),
            )
        except errors.UniqueViolation as exc:
            raise DuplicateVersionError(f"mask {body.mask_id} v{body.version} already exists (append-only)") from exc

    def activate_release_unit(self, unit: ReleaseUnit, change: ChangeRecord) -> None:
        with self._conn.transaction():
            if (
                self._conn.execute(
                    _TEMPLATE_EXISTS, (unit.template_ref.template_id, unit.template_ref.version)
                ).fetchone()
                is None
            ):
                raise UnknownReleaseRefError(
                    f"template {unit.template_ref.template_id} v{unit.template_ref.version} not found"
                )
            for ref in unit.mask_refs:
                self._flip_active(ref)

    def _flip_active(self, ref: MaskRef) -> None:
        """Deactivate the ref's context, then activate the ref — inside the
        caller's transaction, so a later failure rolls this flip back too."""
        row = self._conn.execute(_LOCK_MASK_CONTEXT, (ref.mask_id, ref.version)).fetchone()
        if row is None:
            raise UnknownReleaseRefError(f"mask {ref.mask_id} v{ref.version} not found")
        tenant_id, template_id, system_context = row
        self._conn.execute(_DEACTIVATE_CONTEXT, (tenant_id, template_id, system_context))
        self._conn.execute(_ACTIVATE_MASK, (ref.mask_id, ref.version))

    def get_template(self, ref: TemplateRef) -> TemplateArtifact | None:
        row = self._conn.execute(_SELECT_TEMPLATE, (ref.template_id, ref.version)).fetchone()
        if row is None:
            return None
        return TemplateArtifact(
            artifact_id=ref.template_id,
            version=ref.version,
            tenant_id=row[0],
            created_at=row[1],
            body=TemplateBody.model_validate(row[2]),
        )

    def get_mask(self, ref: MaskRef) -> DecoderMaskArtifact | None:
        row = self._conn.execute(_SELECT_MASK, (ref.mask_id, ref.version)).fetchone()
        return self._mask_from_row(row)

    def get_active_mask(
        self, template_id: str, system_context: str, tenant_id: str | None
    ) -> DecoderMaskArtifact | None:
        row = self._conn.execute(_SELECT_ACTIVE_MASK, (template_id, system_context, tenant_id)).fetchone()
        return self._mask_from_row(row)

    def list_template_versions(self, template_id: str) -> tuple[int, ...]:
        rows = self._conn.execute(_LIST_TEMPLATE_VERSIONS, (template_id,)).fetchall()
        return tuple(int(row[0]) for row in rows)

    def list_mask_versions(self, mask_id: str) -> tuple[int, ...]:
        rows = self._conn.execute(_LIST_MASK_VERSIONS, (mask_id,)).fetchall()
        return tuple(int(row[0]) for row in rows)

    def _mask_from_row(self, row: tuple[Any, ...] | None) -> DecoderMaskArtifact | None:
        if row is None:
            return None
        body = DecoderMaskBody.model_validate(row[2])
        return DecoderMaskArtifact(
            artifact_id=body.mask_id,
            version=body.version,
            tenant_id=row[0],
            created_at=row[1],
            body=body,
        )
