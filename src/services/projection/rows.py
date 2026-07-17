"""Typed projection rows and replacement scopes (epic E07).

Plain frozen dataclasses — the wire between the pure decode step and whatever
`ProjectionSink` persists them. A scope names one whole unit of replacement:
the writer converges by deleting a scope and reinserting its rows, so a row
type and its scope always travel together.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class DocumentValuesScope:
    """Replacement unit for extracted values: one content version of one document."""

    tenant_id: str
    document_id: str
    content_id: str
    content_version: int


@dataclass(frozen=True, slots=True)
class ExtractedValueRow:
    """One observation from a content artifact, flattened for `extracted_values`."""

    tenant_id: str
    document_id: str
    content_id: str
    content_version: int
    element_id: str
    value: str | None
    state: str
    confidence_raw: float
    confidence_calibrated: float
    provenance: dict[str, Any]


@dataclass(frozen=True, slots=True)
class MaskEntriesScope:
    """Replacement unit for mask entries: one version of one mask (tenant-first)."""

    tenant_id: str | None
    mask_id: str
    mask_version: int


@dataclass(frozen=True, slots=True)
class MaskEntryRow:
    """One decoder-mask entry, flattened for `mask_entries` (attribution included)."""

    tenant_id: str | None
    mask_id: str
    mask_version: int
    scope: str
    template_id: str
    template_version: int
    system_context: str
    element_id: str
    semantic_role: str
    target_schema: str
    target_field: str
    target_datatype: str
    enum_map: dict[str, str | bool] | None
    section_path: str | None
    origin: str
    inherited_from_mask_id: str | None
    inherited_from_version: int | None
    overridden: bool
    validated_by: str | None
