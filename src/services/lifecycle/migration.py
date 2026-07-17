"""MaskMigrator (epic E08): draft-mask migration driven by a lineage report.

Compatible elements carry their mask entries forward automatically into a
draft mask vN+1 — semantics untouched, attribution preserved, and
`inherited_from` updated to name the exact mask version the entry was copied
from. Everything the lineage could not carry 1:1 (split / merged / added /
ambiguous) becomes a review-worklist item for a human; nothing is guessed.

The draft is a DRAFT: `validate_for_activation` runs E01's InvariantValidator
(referential element resolution + target-mapping/attribution invariants)
against the new template before a release unit may activate it.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from domain.artifacts.errors import ValidationReport
from domain.artifacts.mask import DecoderMaskArtifact, DecoderMaskBody, MaskEntry, MaskRef
from domain.artifacts.template import TemplateArtifact, TemplateBody
from domain.lineage.model import ElementRelation, LineageEntry, LineageReport
from services.lifecycle.errors import LifecycleError
from services.validation.bundle import ArtifactBundle
from services.validation.validator import InvariantValidator

# Envelope timestamp used when wrapping bare bodies for validation; the
# validator only checks envelope/body agreement on ids/versions/tenant, so a
# fixed instant keeps validation pure and deterministic.
_VALIDATION_INSTANT = datetime(2026, 1, 1, tzinfo=UTC)


class WorklistItem(BaseModel):
    """One element change a human must resolve before the mask is complete."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    relation: ElementRelation
    old_element_ids: tuple[str, ...]
    new_element_ids: tuple[str, ...]
    # The mask entry that could not be carried forward; None for template
    # elements that are new in vN+1 (relation "added" — no entry exists yet).
    mask_entry_element_id: str | None
    reason: str = Field(min_length=1)


class DraftMigration(BaseModel):
    """Result of drafting a mask against a new template version."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    draft_mask_body: DecoderMaskBody
    review_worklist: tuple[WorklistItem, ...]


class MaskMigrator:
    def __init__(self, validator: InvariantValidator) -> None:
        self._validator = validator

    def draft(self, mask: DecoderMaskBody, lineage: LineageReport) -> DraftMigration:
        if mask.template_ref != lineage.from_ref:
            raise LifecycleError(
                f"mask {mask.mask_id} v{mask.version} references template "
                f"{mask.template_ref.template_id} v{mask.template_ref.version}, "
                f"but the lineage starts from v{lineage.from_ref.version}"
            )
        source_ref = MaskRef(mask_id=mask.mask_id, version=mask.version)
        entries: list[MaskEntry] = []
        worklist: list[WorklistItem] = []
        for entry in mask.entries:
            lineage_entry = lineage.entry_for_old(entry.element_id)
            if lineage_entry is None:
                raise LifecycleError(f"lineage has no entry for mask element '{entry.element_id}'")
            if lineage_entry.relation == "compatible":
                entries.append(_carry_forward(entry, lineage_entry, source_ref))
            elif lineage_entry.relation != "removed":
                worklist.append(_review_item(lineage_entry, entry.element_id))
        worklist += [_review_item(lineage_entry, None) for lineage_entry in _added_entries(lineage)]
        if not entries:
            raise LifecycleError(f"no compatible entries to migrate for mask {mask.mask_id} v{mask.version}")
        draft = mask.model_copy(
            update={"version": mask.version + 1, "template_ref": lineage.to_ref, "entries": entries}
        )
        return DraftMigration(draft_mask_body=draft, review_worklist=tuple(worklist))

    def validate_for_activation(self, draft: DecoderMaskBody, template: TemplateBody) -> ValidationReport:
        """Referential + target-mapping validation of a draft against its template."""
        bundle = ArtifactBundle(
            template=TemplateArtifact(
                artifact_id=template.template_id,
                version=template.version,
                tenant_id=None,
                created_at=_VALIDATION_INSTANT,
                body=template,
            ),
            mask=DecoderMaskArtifact(
                artifact_id=draft.mask_id,
                version=draft.version,
                tenant_id=draft.tenant_id,
                created_at=_VALIDATION_INSTANT,
                body=draft,
            ),
        )
        return self._validator.validate(bundle)


def _carry_forward(entry: MaskEntry, lineage_entry: LineageEntry, source_ref: MaskRef) -> MaskEntry:
    new_element_id = lineage_entry.new_element_ids[0]  # compatible is 1:1 by model invariant
    return entry.model_copy(
        update={
            "element_id": new_element_id,
            "attribution": entry.attribution.model_copy(update={"inherited_from": source_ref}),
        }
    )


def _review_item(lineage_entry: LineageEntry, mask_entry_element_id: str | None) -> WorklistItem:
    return WorklistItem(
        relation=lineage_entry.relation,
        old_element_ids=lineage_entry.old_element_ids,
        new_element_ids=lineage_entry.new_element_ids,
        mask_entry_element_id=mask_entry_element_id,
        reason=f"{lineage_entry.relation}: {lineage_entry.evidence}",
    )


def _added_entries(lineage: LineageReport) -> tuple[LineageEntry, ...]:
    return tuple(entry for entry in lineage.entries if entry.relation == "added")
