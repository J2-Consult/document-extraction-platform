"""LineageGenerator.compare(old, new): geometry + anchor-text based lineage.

Extraction-oriented ONLY — the generator sees pages, bboxes, kinds, and anchor
label texts; it never sees or infers business meaning. It must be
deterministic under element shuffling and renumbering (property test with a
seeded random.Random — matching decisions may not depend on element ids or
list order).
"""

from __future__ import annotations

import random

from domain.artifacts.template import Anchor, ElementKind, PageGeometry, TemplateBody, TemplateElement, TemplateRef
from domain.lineage.generator import LineageGenerator
from domain.lineage.model import LineageEntry, LineageReport

_FINGERPRINT = "fpv1:sha256:" + "0" * 64


def _element(
    element_id: str,
    bbox: tuple[float, float, float, float],
    label: str | None = None,
    kind: ElementKind = "value_region",
    page: int = 1,
) -> TemplateElement:
    anchor = None
    if label is not None:
        anchor = Anchor(label_text=label, label_bbox=[bbox[0] - 150, bbox[1], bbox[0] - 10, bbox[3]])
    return TemplateElement(element_id=element_id, kind=kind, page=page, bbox=list(bbox), anchor=anchor)


def _template(version: int, elements: list[TemplateElement]) -> TemplateBody:
    pages = sorted({element.page for element in elements})
    return TemplateBody(
        template_id="tmpl_lineage_test",
        version=version,
        doc_class="invoice",
        fingerprint=_FINGERPRINT,
        page_count=max(pages),
        pages=[
            PageGeometry(page=page, width=595.0, height=842.0, unit="pt", rotation=0)
            for page in range(1, max(pages) + 1)
        ],
        elements=elements,
    )


def _entry_for_old(report: LineageReport, element_id: str) -> LineageEntry:
    matches = [entry for entry in report.entries if element_id in entry.old_element_ids]
    assert len(matches) == 1, f"expected exactly one lineage entry for {element_id}, got {matches}"
    return matches[0]


def _entry_for_new(report: LineageReport, element_id: str) -> LineageEntry:
    matches = [entry for entry in report.entries if element_id in entry.new_element_ids]
    assert len(matches) == 1, f"expected exactly one lineage entry for {element_id}, got {matches}"
    return matches[0]


_BASE_ELEMENTS: list[TemplateElement] = [
    _element("el_number", (206, 780, 346, 792), label="Invoice number:"),
    _element("el_date", (206, 756, 346, 768), label="Invoice date:"),
    _element("el_total", (206, 612, 346, 624), label="Total amount:"),
    _element("el_approved", (206, 564, 346, 576), label="Approved:", kind="checkbox"),
]


def test_identical_templates_yield_all_compatible_one_to_one() -> None:
    old = _template(1, list(_BASE_ELEMENTS))
    new = _template(2, list(_BASE_ELEMENTS))

    report = LineageGenerator().compare(old, new)

    assert report.from_ref == TemplateRef(template_id="tmpl_lineage_test", version=1)
    assert report.to_ref == TemplateRef(template_id="tmpl_lineage_test", version=2)
    assert len(report.entries) == len(_BASE_ELEMENTS)
    assert all(entry.relation == "compatible" for entry in report.entries)


def test_moved_field_with_same_anchor_text_is_compatible() -> None:
    moved = _element("el_total_v2", (206, 300, 346, 312), label="Total amount:")
    old = _template(1, list(_BASE_ELEMENTS))
    new = _template(2, [element for element in _BASE_ELEMENTS if element.element_id != "el_total"] + [moved])

    report = LineageGenerator().compare(old, new)

    entry = _entry_for_old(report, "el_total")
    assert entry.relation == "compatible"
    assert entry.new_element_ids == ("el_total_v2",)
    assert "anchor" in entry.evidence


def test_field_split_into_two_regions_over_the_old_bbox_is_split() -> None:
    left = _element("el_total_excl", (206, 612, 274, 624), label="Total excl. VAT:")
    right = _element("el_total_incl", (278, 612, 346, 624), label="Total incl. VAT:")
    old = _template(1, list(_BASE_ELEMENTS))
    new = _template(2, [element for element in _BASE_ELEMENTS if element.element_id != "el_total"] + [left, right])

    report = LineageGenerator().compare(old, new)

    entry = _entry_for_old(report, "el_total")
    assert entry.relation == "split"
    assert entry.old_element_ids == ("el_total",)
    assert entry.new_element_ids == ("el_total_excl", "el_total_incl")


def test_brand_new_element_is_added_and_dropped_element_is_removed() -> None:
    added = _element("el_reference", (206, 200, 346, 212), label="Reference:")
    old = _template(1, list(_BASE_ELEMENTS))
    new = _template(2, [element for element in _BASE_ELEMENTS if element.element_id != "el_date"] + [added])

    report = LineageGenerator().compare(old, new)

    added_entry = _entry_for_new(report, "el_reference")
    assert added_entry.relation == "added"
    assert added_entry.old_element_ids == ()
    removed_entry = _entry_for_old(report, "el_date")
    assert removed_entry.relation == "removed"
    assert removed_entry.new_element_ids == ()


def test_two_old_regions_covered_by_one_new_region_are_merged() -> None:
    merged = _element("el_totals", (206, 612, 346, 624), label="Totals:")
    old = _template(
        1,
        [
            _element("el_total_excl", (206, 612, 274, 624), label="Total excl. VAT:"),
            _element("el_total_incl", (278, 612, 346, 624), label="Total incl. VAT:"),
            _element("el_number", (206, 780, 346, 792), label="Invoice number:"),
        ],
    )
    new = _template(2, [merged, _element("el_number", (206, 780, 346, 792), label="Invoice number:")])

    report = LineageGenerator().compare(old, new)

    entry = _entry_for_new(report, "el_totals")
    assert entry.relation == "merged"
    assert entry.old_element_ids == ("el_total_excl", "el_total_incl")


def test_same_geometry_with_changed_anchor_text_is_ambiguous_not_guessed() -> None:
    relabeled = _element("el_total", (206, 612, 346, 624), label="Grand total:")
    old = _template(1, list(_BASE_ELEMENTS))
    new = _template(2, [element for element in _BASE_ELEMENTS if element.element_id != "el_total"] + [relabeled])

    report = LineageGenerator().compare(old, new)

    entry = _entry_for_old(report, "el_total")
    assert entry.relation == "ambiguous"


def test_anchorless_element_with_unchanged_geometry_is_compatible() -> None:
    table_columns = [{"name": "description", "datatype": "string"}]
    old_table = TemplateElement(
        element_id="el_items",
        kind="table",
        page=1,
        bbox=[56, 432, 500, 494],
        columns=table_columns,  # type: ignore[arg-type]
    )
    new_table = TemplateElement(
        element_id="el_items_v2",
        kind="table",
        page=1,
        bbox=[56, 432, 500, 494],
        columns=table_columns,  # type: ignore[arg-type]
    )
    old = _template(1, [*_BASE_ELEMENTS, old_table])
    new = _template(2, [*_BASE_ELEMENTS, new_table])

    report = LineageGenerator().compare(old, new)

    entry = _entry_for_old(report, "el_items")
    assert entry.relation == "compatible"
    assert entry.new_element_ids == ("el_items_v2",)


def test_elements_on_different_pages_never_match_geometrically() -> None:
    old = _template(1, [_element("el_a", (100, 100, 200, 112), page=1)])
    new = _template(2, [_element("el_b", (100, 100, 200, 112), page=2)])

    report = LineageGenerator().compare(old, new)

    assert _entry_for_old(report, "el_a").relation == "removed"
    assert _entry_for_new(report, "el_b").relation == "added"


def _renamed_and_shuffled(
    template: TemplateBody, rng: random.Random, prefix: str
) -> tuple[TemplateBody, dict[str, str]]:
    """Shuffle element order and rename every element id; returns (template, new_id -> original_id)."""
    elements = list(template.elements)
    rng.shuffle(elements)
    rename = {element.element_id: f"{prefix}{index:03d}" for index, element in enumerate(elements)}
    renamed = [element.model_copy(update={"element_id": rename[element.element_id]}) for element in elements]
    inverse = {new_id: old_id for old_id, new_id in rename.items()}
    return template.model_copy(update={"elements": renamed}), inverse


def _canonical(
    report: LineageReport, old_inverse: dict[str, str], new_inverse: dict[str, str]
) -> set[tuple[str, tuple[str, ...], tuple[str, ...]]]:
    return {
        (
            entry.relation,
            tuple(sorted(old_inverse.get(element_id, element_id) for element_id in entry.old_element_ids)),
            tuple(sorted(new_inverse.get(element_id, element_id) for element_id in entry.new_element_ids)),
        )
        for entry in report.entries
    }


def test_lineage_is_deterministic_under_element_shuffling_and_renumbering() -> None:
    generator = LineageGenerator()
    split_left = _element("el_total_excl", (206, 612, 274, 624), label="Total excl. VAT:")
    split_right = _element("el_total_incl", (278, 612, 346, 624), label="Total incl. VAT:")
    moved = _element("el_number_moved", (206, 320, 346, 332), label="Invoice number:")
    added = _element("el_reference", (206, 200, 346, 212), label="Reference:")
    old = _template(1, list(_BASE_ELEMENTS))
    new = _template(
        2,
        [element for element in _BASE_ELEMENTS if element.element_id not in {"el_total", "el_number"}]
        + [split_left, split_right, moved, added],
    )

    identity: dict[str, str] = {}
    baseline = _canonical(generator.compare(old, new), identity, identity)
    assert baseline == _canonical(generator.compare(old, new), identity, identity), "same input must reproduce"

    rng = random.Random(20260716)
    for _ in range(25):
        shuffled_old, old_inverse = _renamed_and_shuffled(old, rng, "o")
        shuffled_new, new_inverse = _renamed_and_shuffled(new, rng, "n")
        report = generator.compare(shuffled_old, shuffled_new)
        assert _canonical(report, old_inverse, new_inverse) == baseline


def test_report_entries_are_deterministically_ordered() -> None:
    old = _template(1, list(_BASE_ELEMENTS))
    new = _template(2, list(reversed(_BASE_ELEMENTS)))

    first = LineageGenerator().compare(old, new)
    second = LineageGenerator().compare(old, new)

    assert first == second
    ordering = [(entry.old_element_ids, entry.new_element_ids) for entry in first.entries]
    assert ordering == sorted(ordering)
