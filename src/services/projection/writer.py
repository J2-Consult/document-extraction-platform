"""Idempotent projection writer (epic E07).

Orchestrates the pure decode step and a `ProjectionSink` port: every write
replaces one whole (tenant, document/mask, version) scope, so runs are
re-runnable in any order and a partially failed run converges on the next
attempt — the sink either lands the full scope or none of it.

Interface note: `ProjectionSink` lives here rather than in ``src/ports/``
because E07's owned paths are ``src/services/projection/`` and the read-side
query module only; relocating it to ``src/ports/projection.py`` is proposed
as follow-up housekeeping, not done unilaterally.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from services.projection.decode import decode_document_values, decode_mask_entries
from services.projection.rows import (
    DocumentValuesScope,
    ExtractedValueRow,
    MaskEntriesScope,
    MaskEntryRow,
)


class ProjectionSink(Protocol):
    """Transactional replace-by-scope persistence for projection rows.

    Implementations MUST replace atomically: delete the scope's existing rows
    and insert `rows` inside one transaction (or an equivalent all-or-nothing
    mechanism), so a failed write leaves the previous rows intact.
    """

    def replace_document_values(self, scope: DocumentValuesScope, rows: Sequence[ExtractedValueRow]) -> None: ...

    def replace_mask_entries(self, scope: MaskEntriesScope, rows: Sequence[MaskEntryRow]) -> None: ...


class ProjectionWriter:
    """Decode an immutable artifact body and replace its projection scope."""

    def __init__(self, sink: ProjectionSink) -> None:
        self._sink = sink

    def project_content(self, artifact: Mapping[str, Any]) -> tuple[ExtractedValueRow, ...]:
        """Project a content artifact into `extracted_values`; returns the rows."""
        rows = decode_document_values(artifact)
        scope = DocumentValuesScope(
            tenant_id=rows[0].tenant_id if rows else self._content_tenant(artifact),
            document_id=str(artifact["body"]["document_id"]),
            content_id=str(artifact["body"]["content_id"]),
            content_version=int(artifact["body"]["version"]),
        )
        self._sink.replace_document_values(scope, rows)
        return rows

    def project_mask(self, artifact: Mapping[str, Any]) -> tuple[MaskEntryRow, ...]:
        """Project a decoder-mask artifact into `mask_entries`; returns the rows."""
        rows = decode_mask_entries(artifact)
        # DecoderMaskBody requires >= 1 entry, so the scope is always derivable
        # from the rows themselves.
        scope = MaskEntriesScope(
            tenant_id=rows[0].tenant_id,
            mask_id=rows[0].mask_id,
            mask_version=rows[0].mask_version,
        )
        self._sink.replace_mask_entries(scope, rows)
        return rows

    @staticmethod
    def _content_tenant(artifact: Mapping[str, Any]) -> str:
        tenant_id = artifact.get("tenant_id")
        if not isinstance(tenant_id, str) or not tenant_id:
            raise ValueError("content artifact has no tenant_id; extracted values are tenant-owned")
        return tenant_id
