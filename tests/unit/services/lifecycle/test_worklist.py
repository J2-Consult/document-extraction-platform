"""Consultant worklist: template elements uncovered by the vendor baseline
mask. Pure computation over shared (vendor) artifacts only — the integration
suite runs it against live Postgres as the `synthesis` role, which can see
nothing else.
"""

from __future__ import annotations

import pytest

from domain.artifacts.template import Anchor, TemplateElement, TemplateRef
from services.lifecycle.errors import LifecycleError
from services.lifecycle.worklist import uncovered_elements
from tests.unit.services.lifecycle._fixtures import load_mask, load_template


def test_fixture_vendor_mask_leaves_exactly_the_unmapped_value_elements_uncovered() -> None:
    template = load_template("tmpl_nvinv.v1").body
    vendor_mask = load_mask("mask_nvvendor.v1").body

    uncovered = uncovered_elements(template, vendor_mask)

    assert [item.element_id for item in uncovered] == ["el_customer_name", "el_vendor_name"]
    assert all(item.kind == "value_region" for item in uncovered)


def test_full_coverage_yields_an_empty_worklist() -> None:
    template = load_template("tmpl_nvinv.v1").body
    vendor_mask = load_mask("mask_nvvendor.v1").body
    covered_ids = {entry.element_id for entry in vendor_mask.entries}
    trimmed = template.model_copy(
        update={"elements": [element for element in template.elements if element.element_id in covered_ids]}
    )

    assert uncovered_elements(trimmed, vendor_mask) == ()


def test_label_elements_are_not_extraction_targets_and_never_appear() -> None:
    template = load_template("tmpl_nvinv.v1").body
    label = TemplateElement(
        element_id="el_some_label",
        kind="label",
        page=1,
        bbox=[10.0, 10.0, 60.0, 22.0],
        anchor=Anchor(label_text="Some label:", label_bbox=[10.0, 10.0, 60.0, 22.0]),
    )
    with_label = template.model_copy(update={"elements": [*template.elements, label]})

    uncovered = uncovered_elements(with_label, load_mask("mask_nvvendor.v1").body)

    assert "el_some_label" not in {item.element_id for item in uncovered}


def test_mask_for_a_different_template_version_is_rejected() -> None:
    template = load_template("tmpl_nvinv.v1").body
    stale_mask = load_mask("mask_nvvendor.v1").body.model_copy(
        update={"template_ref": TemplateRef(template_id="tmpl_nvinv", version=9)}
    )

    with pytest.raises(LifecycleError):
        uncovered_elements(template, stale_mask)


def test_customer_masks_are_not_a_consultant_baseline() -> None:
    template = load_template("tmpl_nvinv.v1").body

    with pytest.raises(LifecycleError):
        uncovered_elements(template, load_mask("mask_nvcust.v1").body)
