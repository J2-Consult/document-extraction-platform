"""Decode immutable artifact bodies into projection rows (epic E07).

Pure functions, no I/O: artifact JSON in (wire form), typed rows out. All
parsing goes through the E01 models so every invariant they enforce holds for
what lands in the projections — in particular the mask entries' `TargetBinding`
is parsed via its `schema` wire alias, never by poking at raw dicts.

Determinism: rows come out in the artifact's own entry order, and every field
is a pure function of the artifact body — decoding the same artifact twice
yields identical tuples, which is what makes the writer's delete-and-reinsert
idempotent.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from domain.artifacts.content import ContentArtifact
from domain.artifacts.mask import DecoderMaskArtifact
from services.projection.rows import ExtractedValueRow, MaskEntryRow


def decode_document_values(artifact: Mapping[str, Any]) -> tuple[ExtractedValueRow, ...]:
    """One `ExtractedValueRow` per observation of a content artifact.

    Raises ``ValueError`` for a content artifact without a tenant: extracted
    values are tenant-owned rows (documents are never vendor-shared), so a
    NULL tenant here could only be a mis-built artifact.
    """
    content = ContentArtifact.model_validate(artifact)
    if content.tenant_id is None:
        raise ValueError("content artifact has no tenant_id; extracted values are tenant-owned")
    body = content.body
    return tuple(
        ExtractedValueRow(
            tenant_id=content.tenant_id,
            document_id=body.document_id,
            content_id=body.content_id,
            content_version=body.version,
            element_id=observation.element_id,
            value=observation.value,
            state=observation.state,
            confidence_raw=observation.confidence.raw,
            confidence_calibrated=observation.confidence.calibrated,
            # exclude_none: E09 added the optional `corrected_by` field to
            # Provenance (disclosed addition); every pre-existing fixture
            # omits the key entirely on the wire, so byte-for-byte wire-form
            # parity (this function's contract) requires dropping it when
            # unset rather than emitting a new `null` key no fixture has.
            provenance=observation.provenance.model_dump(mode="json", exclude_none=True),
        )
        for observation in body.observations
    )


def decode_mask_entries(artifact: Mapping[str, Any]) -> tuple[MaskEntryRow, ...]:
    """One `MaskEntryRow` per entry of a decoder-mask artifact, attribution included."""
    mask = DecoderMaskArtifact.model_validate(artifact)
    body = mask.body
    return tuple(
        MaskEntryRow(
            tenant_id=body.tenant_id,
            mask_id=body.mask_id,
            mask_version=body.version,
            scope=body.scope,
            template_id=body.template_ref.template_id,
            template_version=body.template_ref.version,
            system_context=body.system_context,
            element_id=entry.element_id,
            semantic_role=entry.semantic_role,
            target_schema=entry.target.target_schema,
            target_field=entry.target.field,
            target_datatype=entry.target.datatype,
            enum_map=dict(entry.enum_map) if entry.enum_map is not None else None,
            section_path=entry.section_path,
            origin=entry.attribution.origin,
            inherited_from_mask_id=(
                entry.attribution.inherited_from.mask_id if entry.attribution.inherited_from else None
            ),
            inherited_from_version=(
                entry.attribution.inherited_from.version if entry.attribution.inherited_from else None
            ),
            overridden=entry.attribution.overridden,
            validated_by=entry.attribution.validated_by,
        )
        for entry in body.entries
    )
