"""E05 domain value objects: PageImage, Region, TextSpan, PassOutput.

Every output fragment must carry enough to build E06 provenance — method,
component_version, bbox, coordinate_space (+ transform_to_source) — per
specs/design/E05-interfaces.md "Key shapes".
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from domain.extraction import (
    IDENTITY_TRANSFORM,
    PageDims,
    PageImage,
    PassOutput,
    Region,
    TextSpan,
)


def _text_span(text: str = "Invoice number:", confidence: float = 1.0) -> TextSpan:
    return TextSpan(
        text=text,
        page=1,
        bbox=[56.0, 780.0, 131.0, 792.0],
        coordinate_space="page-1",
        confidence=confidence,
    )


def _region(kind: str = "text", score: float = 0.9) -> Region:
    return Region(page=1, bbox=[206.0, 780.0, 346.0, 792.0], coordinate_space="page-1", kind=kind, score=score)  # type: ignore[arg-type]


def _pass_output(spans: tuple[TextSpan, ...] = (), regions: tuple[Region, ...] = ()) -> PassOutput:
    return PassOutput(
        method="pdf_text",
        component_version="native-text-pypdf/1.0.0",
        transform_to_source=list(IDENTITY_TRANSFORM),
        pages=(PageDims(page=1, width=595.0, height=842.0),),
        spans=spans,
        regions=regions,
    )


def test_identity_transform_is_the_affine_identity_six_tuple() -> None:
    assert IDENTITY_TRANSFORM == (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def test_page_image_rejects_empty_bytes_and_non_positive_dpi() -> None:
    with pytest.raises(ValidationError):
        PageImage(
            page=1,
            image_bytes=b"",
            coordinate_space="page-1@300dpi",
            dpi=300.0,
            width=2480.0,
            height=3508.0,
            transform_to_source=list(IDENTITY_TRANSFORM),
        )
    with pytest.raises(ValidationError):
        PageImage(
            page=1,
            image_bytes=b"raster",
            coordinate_space="page-1@300dpi",
            dpi=0.0,
            width=2480.0,
            height=3508.0,
            transform_to_source=list(IDENTITY_TRANSFORM),
        )


def test_region_bbox_must_be_exactly_four_coordinates() -> None:
    with pytest.raises(ValidationError):
        Region(page=1, bbox=[1.0, 2.0, 3.0], coordinate_space="page-1", kind="text", score=0.5)


def test_region_score_is_bounded_to_unit_interval() -> None:
    with pytest.raises(ValidationError):
        _region(score=1.5)


def test_text_span_defaults_to_full_confidence_and_is_frozen() -> None:
    span = TextSpan(text="Net 30 days", page=1, bbox=[206.0, 636.0, 261.0, 648.0], coordinate_space="page-1")
    assert span.confidence == 1.0
    with pytest.raises(ValidationError):
        span.text = "tampered"


def test_pass_output_carries_method_component_version_and_page_dims() -> None:
    output = _pass_output(spans=(_text_span(),))
    assert output.method == "pdf_text"
    assert output.component_version == "native-text-pypdf/1.0.0"
    assert output.pages[0].width == 595.0
    with pytest.raises(ValidationError):
        output.method = "ocr"


def test_provenance_fragments_cover_every_span_and_region_with_all_e06_fields() -> None:
    span = _text_span()
    region = _region()
    output = _pass_output(spans=(span,), regions=(region,))

    fragments = output.provenance_fragments()

    assert len(fragments) == 2
    for fragment in fragments:
        assert fragment.method == "pdf_text"
        assert fragment.component_version == "native-text-pypdf/1.0.0"
        assert len(fragment.bbox) == 4
        assert fragment.coordinate_space == "page-1"
        assert fragment.page == 1
        assert tuple(fragment.transform_to_source) == IDENTITY_TRANSFORM
    assert {tuple(fragment.bbox) for fragment in fragments} == {tuple(span.bbox), tuple(region.bbox)}


def test_pass_output_rejects_unknown_extraction_method() -> None:
    with pytest.raises(ValidationError):
        PassOutput(
            method="telepathy",  # type: ignore[arg-type]
            component_version="x/1",
            transform_to_source=list(IDENTITY_TRANSFORM),
        )
