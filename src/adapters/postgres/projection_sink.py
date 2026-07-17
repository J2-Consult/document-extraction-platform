"""Postgres `ProjectionSink` (epic E07): transactional replace-by-scope writes.

Implements exactly one port (`services.projection.writer.ProjectionSink`),
substitutable with the in-memory fake used in the unit tests. Each replace is
a delete-and-reinsert of one whole (tenant, document/mask, version) scope
inside a single transaction — psycopg's ``Connection.transaction()`` gives a
savepoint when a transaction is already open, so a failed replace never leaves
a half-written scope either way.

SQL discipline: parameterized statements only; jsonb columns bound via
``psycopg.types.json.Json``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import psycopg
from psycopg.types.json import Json

from services.projection.rows import (
    DocumentValuesScope,
    ExtractedValueRow,
    MaskEntriesScope,
    MaskEntryRow,
)

_DELETE_DOCUMENT_VALUES = """
DELETE FROM extracted_values
WHERE tenant_id = %s AND document_id = %s AND content_id = %s AND content_version = %s
"""

_INSERT_DOCUMENT_VALUE = """
INSERT INTO extracted_values
    (tenant_id, document_id, content_id, content_version, element_id,
     value, state, confidence_raw, confidence_calibrated, provenance)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

_DELETE_MASK_ENTRIES = """
DELETE FROM mask_entries
WHERE tenant_id IS NOT DISTINCT FROM %s AND mask_id = %s AND mask_version = %s
"""

_INSERT_MASK_ENTRY = """
INSERT INTO mask_entries
    (tenant_id, mask_id, mask_version, scope, template_id, template_version,
     system_context, element_id, semantic_role, target_schema, target_field,
     target_datatype, enum_map, section_path, origin, inherited_from_mask_id,
     inherited_from_version, overridden, validated_by)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


class PostgresProjectionSink:
    """Replace-by-scope projection persistence against the E07 projection tables."""

    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self._conn = conn

    def replace_document_values(self, scope: DocumentValuesScope, rows: Sequence[ExtractedValueRow]) -> None:
        with self._conn.transaction(), self._conn.cursor() as cur:
            cur.execute(
                _DELETE_DOCUMENT_VALUES,
                (scope.tenant_id, scope.document_id, scope.content_id, scope.content_version),
            )
            cur.executemany(
                _INSERT_DOCUMENT_VALUE,
                [
                    (
                        row.tenant_id,
                        row.document_id,
                        row.content_id,
                        row.content_version,
                        row.element_id,
                        row.value,
                        row.state,
                        row.confidence_raw,
                        row.confidence_calibrated,
                        Json(row.provenance),
                    )
                    for row in rows
                ],
            )

    def replace_mask_entries(self, scope: MaskEntriesScope, rows: Sequence[MaskEntryRow]) -> None:
        with self._conn.transaction(), self._conn.cursor() as cur:
            cur.execute(_DELETE_MASK_ENTRIES, (scope.tenant_id, scope.mask_id, scope.mask_version))
            cur.executemany(
                _INSERT_MASK_ENTRY,
                [
                    (
                        row.tenant_id,
                        row.mask_id,
                        row.mask_version,
                        row.scope,
                        row.template_id,
                        row.template_version,
                        row.system_context,
                        row.element_id,
                        row.semantic_role,
                        row.target_schema,
                        row.target_field,
                        row.target_datatype,
                        Json(row.enum_map) if row.enum_map is not None else None,
                        row.section_path,
                        row.origin,
                        row.inherited_from_mask_id,
                        row.inherited_from_version,
                        row.overridden,
                        row.validated_by,
                    )
                    for row in rows
                ],
            )
