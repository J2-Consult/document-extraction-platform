"""LineageEntry/LineageReport shapes (specs/design/E08-interfaces.md).

The relation vocabulary is closed (compatible | split | merged | added |
removed | ambiguous) and each relation constrains the old/new id
cardinalities — a "compatible" entry is 1:1 by definition, a "split" is
1:many, and so on. These are extraction-oriented structural facts only;
no business meaning is ever inferred or carried here.
"""

from __future__ import annotations

from typing import get_args

import pytest
from pydantic import ValidationError

from domain.artifacts.template import TemplateRef
from domain.lineage.model import ElementRelation, LineageEntry, LineageReport


def _entry(relation: str, old: tuple[str, ...], new: tuple[str, ...]) -> LineageEntry:
    return LineageEntry(
        relation=relation,  # type: ignore[arg-type]
        old_element_ids=old,
        new_element_ids=new,
        evidence="test",
    )


def test_element_relation_vocabulary_is_closed() -> None:
    assert set(get_args(ElementRelation)) == {
        "compatible",
        "split",
        "merged",
        "added",
        "removed",
        "ambiguous",
    }


@pytest.mark.parametrize(
    ("relation", "old", "new"),
    [
        ("compatible", ("el_a",), ("el_a2",)),
        ("split", ("el_a",), ("el_b", "el_c")),
        ("merged", ("el_a", "el_b"), ("el_c",)),
        ("added", (), ("el_new",)),
        ("removed", ("el_gone",), ()),
        ("ambiguous", ("el_a", "el_b"), ("el_c", "el_d")),
    ],
)
def test_legal_relation_cardinalities_construct(relation: str, old: tuple[str, ...], new: tuple[str, ...]) -> None:
    entry = _entry(relation, old, new)
    assert entry.relation == relation
    assert entry.old_element_ids == old
    assert entry.new_element_ids == new


@pytest.mark.parametrize(
    ("relation", "old", "new"),
    [
        ("compatible", ("el_a", "el_b"), ("el_c",)),  # compatible must be 1:1
        ("compatible", ("el_a",), ()),
        ("split", ("el_a",), ("el_b",)),  # split must fan out to >= 2
        ("split", ("el_a", "el_b"), ("el_c", "el_d")),
        ("merged", ("el_a",), ("el_b",)),  # merged must fan in from >= 2
        ("added", ("el_a",), ("el_b",)),  # added has no old side
        ("removed", ("el_a",), ("el_b",)),  # removed has no new side
        ("ambiguous", (), ()),  # ambiguous still involves elements
    ],
)
def test_illegal_relation_cardinalities_are_rejected(relation: str, old: tuple[str, ...], new: tuple[str, ...]) -> None:
    with pytest.raises(ValidationError):
        _entry(relation, old, new)


def test_report_carries_from_and_to_refs_and_is_frozen() -> None:
    report = LineageReport(
        from_ref=TemplateRef(template_id="tmpl_x", version=1),
        to_ref=TemplateRef(template_id="tmpl_x", version=2),
        entries=(_entry("compatible", ("el_a",), ("el_a",)),),
    )
    assert report.from_ref.version == 1
    assert report.to_ref.version == 2
    with pytest.raises(ValidationError):
        report.entries = ()


def test_entry_element_ids_within_one_side_are_unique() -> None:
    with pytest.raises(ValidationError):
        _entry("merged", ("el_a", "el_a"), ("el_b",))
    with pytest.raises(ValidationError):
        _entry("split", ("el_a",), ("el_b", "el_b"))
