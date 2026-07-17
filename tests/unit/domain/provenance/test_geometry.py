"""`domain.provenance.geometry`: per-page geometry, mixed page sizes legal."""

from __future__ import annotations

import pytest

from domain.provenance.geometry import DocumentGeometry, PageGeometry


def test_page_geometry_with_positive_dimensions_constructs() -> None:
    page = PageGeometry(page=1, width=595.0, height=842.0, unit="pt", rotation=0)
    assert page.width == 595.0


def test_page_geometry_rejects_page_below_one() -> None:
    with pytest.raises(ValueError, match="page must be >= 1"):
        PageGeometry(page=0, width=595.0, height=842.0, unit="pt", rotation=0)


def test_page_geometry_rejects_non_positive_width() -> None:
    with pytest.raises(ValueError, match="width and height"):
        PageGeometry(page=1, width=0.0, height=842.0, unit="pt", rotation=0)


def test_page_geometry_rejects_non_positive_height() -> None:
    with pytest.raises(ValueError, match="width and height"):
        PageGeometry(page=1, width=595.0, height=-1.0, unit="pt", rotation=0)


def test_document_geometry_with_mixed_page_sizes_is_legal() -> None:
    # Page 1 is A4, page 2 is US Letter — deliberately different dimensions.
    a4 = PageGeometry(page=1, width=595.0, height=842.0, unit="pt", rotation=0)
    letter = PageGeometry(page=2, width=612.0, height=792.0, unit="pt", rotation=0)

    document = DocumentGeometry(pages=(a4, letter))

    assert document.page_count == 2
    assert document.page_geometry(1).width == 595.0
    assert document.page_geometry(2).width == 612.0


def test_document_geometry_rejects_empty_pages() -> None:
    with pytest.raises(ValueError, match="at least one page"):
        DocumentGeometry(pages=())


def test_document_geometry_rejects_duplicate_page_numbers() -> None:
    page = PageGeometry(page=1, width=595.0, height=842.0, unit="pt", rotation=0)
    with pytest.raises(ValueError, match="1..2"):
        DocumentGeometry(pages=(page, page))


def test_document_geometry_rejects_a_gap_in_page_numbers() -> None:
    page1 = PageGeometry(page=1, width=595.0, height=842.0, unit="pt", rotation=0)
    page3 = PageGeometry(page=3, width=595.0, height=842.0, unit="pt", rotation=0)
    with pytest.raises(ValueError, match="1..2"):
        DocumentGeometry(pages=(page1, page3))


def test_contains_page_is_true_within_range_and_false_outside_it() -> None:
    page1 = PageGeometry(page=1, width=595.0, height=842.0, unit="pt", rotation=0)
    page2 = PageGeometry(page=2, width=595.0, height=842.0, unit="pt", rotation=0)
    document = DocumentGeometry(pages=(page1, page2))

    assert document.contains_page(1) is True
    assert document.contains_page(2) is True
    assert document.contains_page(0) is False
    assert document.contains_page(3) is False


def test_page_geometry_lookup_raises_for_an_unrecorded_page() -> None:
    page1 = PageGeometry(page=1, width=595.0, height=842.0, unit="pt", rotation=0)
    document = DocumentGeometry(pages=(page1,))

    with pytest.raises(KeyError, match="no geometry recorded"):
        document.page_geometry(2)
