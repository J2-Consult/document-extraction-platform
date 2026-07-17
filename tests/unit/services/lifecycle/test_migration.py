"""MaskMigrator.draft: compatible entries auto-migrate into a draft mask
vN+1 (attribution preserved, inherited_from updated to the source mask
version); split/merged/added/ambiguous elements land in the review worklist;
the draft is referentially validated with E01's InvariantValidator before
activation.
"""

from __future__ import annotations

import pytest

from domain.artifacts.mask import DecoderMaskBody, MaskRef
from domain.artifacts.template import TemplateRef
from domain.lineage.generator import LineageGenerator
from domain.lineage.model import LineageEntry, LineageReport
from services.lifecycle.errors import LifecycleError
from services.lifecycle.migration import MaskMigrator
from services.validation.validator import default_validator
from tests.unit.services.lifecycle._fixtures import build_tmpl_nvinv_v2, load_mask, load_template

VENDOR_MASK_REF = MaskRef(mask_id="mask_nvvendor", version=1)


@pytest.fixture
def vendor_mask() -> DecoderMaskBody:
    return load_mask("mask_nvvendor.v1").body


@pytest.fixture
def lineage_v1_to_v2() -> LineageReport:
    return LineageGenerator().compare(load_template("tmpl_nvinv.v1").body, build_tmpl_nvinv_v2())


@pytest.fixture
def migrator() -> MaskMigrator:
    return MaskMigrator(default_validator())


def test_compatible_entries_are_copied_into_the_draft(
    migrator: MaskMigrator, vendor_mask: DecoderMaskBody, lineage_v1_to_v2: LineageReport
) -> None:
    migration = migrator.draft(vendor_mask, lineage_v1_to_v2)

    draft = migration.draft_mask_body
    expected_compatible = {entry.element_id for entry in vendor_mask.entries if entry.element_id != "el_total_amount"}
    assert {entry.element_id for entry in draft.entries} == expected_compatible
    by_element = {entry.element_id: entry for entry in draft.entries}
    original = {entry.element_id: entry for entry in vendor_mask.entries}
    for element_id, entry in by_element.items():
        assert entry.semantic_role == original[element_id].semantic_role
        assert entry.target == original[element_id].target
        assert entry.enum_map == original[element_id].enum_map


def test_attribution_preserved_and_inherited_from_updated_to_source_mask(
    migrator: MaskMigrator, vendor_mask: DecoderMaskBody, lineage_v1_to_v2: LineageReport
) -> None:
    migration = migrator.draft(vendor_mask, lineage_v1_to_v2)

    for entry in migration.draft_mask_body.entries:
        assert entry.attribution.origin == "vendor"
        assert entry.attribution.overridden is False
        assert entry.attribution.validated_by == "vendor-consultant-1"
        assert entry.attribution.inherited_from == VENDOR_MASK_REF


def test_draft_body_bumps_version_and_points_at_the_new_template(
    migrator: MaskMigrator, vendor_mask: DecoderMaskBody, lineage_v1_to_v2: LineageReport
) -> None:
    draft = migrator.draft(vendor_mask, lineage_v1_to_v2).draft_mask_body

    assert draft.mask_id == vendor_mask.mask_id
    assert draft.version == vendor_mask.version + 1
    assert draft.template_ref == TemplateRef(template_id="tmpl_nvinv", version=2)
    assert draft.scope == vendor_mask.scope
    assert draft.tenant_id == vendor_mask.tenant_id
    assert draft.system_context == vendor_mask.system_context


def test_split_element_lands_in_review_worklist_not_in_draft(
    migrator: MaskMigrator, vendor_mask: DecoderMaskBody, lineage_v1_to_v2: LineageReport
) -> None:
    migration = migrator.draft(vendor_mask, lineage_v1_to_v2)

    split_items = [item for item in migration.review_worklist if item.relation == "split"]
    assert len(split_items) == 1
    item = split_items[0]
    assert item.mask_entry_element_id == "el_total_amount"
    assert item.old_element_ids == ("el_total_amount",)
    assert item.new_element_ids == ("el_total_excl_vat", "el_total_incl_vat")
    assert "el_total_amount" not in {entry.element_id for entry in migration.draft_mask_body.entries}


def test_added_element_lands_in_review_worklist_with_no_mask_entry(
    migrator: MaskMigrator, vendor_mask: DecoderMaskBody, lineage_v1_to_v2: LineageReport
) -> None:
    migration = migrator.draft(vendor_mask, lineage_v1_to_v2)

    added_items = [item for item in migration.review_worklist if item.relation == "added"]
    assert [item.new_element_ids for item in added_items] == [("el_reference",)]
    assert added_items[0].mask_entry_element_id is None


def test_merged_and_ambiguous_elements_land_in_review_worklist(
    migrator: MaskMigrator, vendor_mask: DecoderMaskBody
) -> None:
    lineage = LineageReport(
        from_ref=TemplateRef(template_id="tmpl_nvinv", version=1),
        to_ref=TemplateRef(template_id="tmpl_nvinv", version=2),
        entries=(
            LineageEntry(
                old_element_ids=("el_due_date", "el_invoice_date"),
                new_element_ids=("el_dates",),
                relation="merged",
                evidence="test",
            ),
            LineageEntry(
                old_element_ids=("el_currency",),
                new_element_ids=("el_currency_x",),
                relation="ambiguous",
                evidence="test",
            ),
        )
        + tuple(
            LineageEntry(
                old_element_ids=(entry.element_id,),
                new_element_ids=(entry.element_id,),
                relation="compatible",
                evidence="test",
            )
            for entry in vendor_mask.entries
            if entry.element_id not in {"el_due_date", "el_invoice_date", "el_currency"}
        ),
    )

    migration = MaskMigrator(default_validator()).draft(vendor_mask, lineage)

    relations = sorted(item.relation for item in migration.review_worklist)
    assert relations == ["ambiguous", "merged", "merged"]
    worklist_sources = {item.mask_entry_element_id for item in migration.review_worklist}
    assert worklist_sources == {"el_due_date", "el_invoice_date", "el_currency"}
    draft_ids = {entry.element_id for entry in migration.draft_mask_body.entries}
    assert draft_ids.isdisjoint({"el_due_date", "el_invoice_date", "el_currency"})


def test_compatible_entry_with_renumbered_element_id_is_remapped(
    migrator: MaskMigrator, vendor_mask: DecoderMaskBody
) -> None:
    lineage = LineageReport(
        from_ref=TemplateRef(template_id="tmpl_nvinv", version=1),
        to_ref=TemplateRef(template_id="tmpl_nvinv", version=2),
        entries=tuple(
            LineageEntry(
                old_element_ids=(entry.element_id,),
                new_element_ids=(f"{entry.element_id}_v2",),
                relation="compatible",
                evidence="test",
            )
            for entry in vendor_mask.entries
        ),
    )

    draft = migrator.draft(vendor_mask, lineage).draft_mask_body

    assert {entry.element_id for entry in draft.entries} == {f"{entry.element_id}_v2" for entry in vendor_mask.entries}


def test_lineage_for_a_different_template_version_is_rejected(
    migrator: MaskMigrator, vendor_mask: DecoderMaskBody, lineage_v1_to_v2: LineageReport
) -> None:
    stale_mask = vendor_mask.model_copy(update={"template_ref": TemplateRef(template_id="tmpl_nvinv", version=7)})

    with pytest.raises(LifecycleError):
        migrator.draft(stale_mask, lineage_v1_to_v2)


def test_validate_for_activation_passes_a_clean_draft(
    migrator: MaskMigrator, vendor_mask: DecoderMaskBody, lineage_v1_to_v2: LineageReport
) -> None:
    draft = migrator.draft(vendor_mask, lineage_v1_to_v2).draft_mask_body

    report = migrator.validate_for_activation(draft, build_tmpl_nvinv_v2())

    assert report.ok, f"expected a validator-clean draft, got: {report.violations}"


def test_validate_for_activation_rejects_unresolvable_element(
    migrator: MaskMigrator, vendor_mask: DecoderMaskBody, lineage_v1_to_v2: LineageReport
) -> None:
    draft = migrator.draft(vendor_mask, lineage_v1_to_v2).draft_mask_body
    entries = list(draft.entries)
    entries[0] = entries[0].model_copy(update={"element_id": "el_ghost"})
    broken = draft.model_copy(update={"entries": entries})

    report = migrator.validate_for_activation(broken, build_tmpl_nvinv_v2())

    assert report.ok is False
    assert "unknown-element-id" in {violation.code for violation in report.violations}
