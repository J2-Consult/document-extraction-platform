"""Deterministic stub passes (preprocessor, OCR, layout, specialized
detectors): stand-ins for provider-side engines, but the interfaces,
coordinate-space bookkeeping, and provenance stamping are REAL and tested.
"""

from __future__ import annotations

import pytest

from adapters.passes.detectors import DETECTOR_STUB_COMPONENT_VERSION, EchoSpecializedDetector
from adapters.passes.layout import LAYOUT_STUB_COMPONENT_VERSION, ScriptedLayoutDetector
from adapters.passes.ocr import OCR_STUB_COMPONENT_VERSION, ScriptedOcrPass
from adapters.passes.preprocessor import DeterministicPagePreprocessor
from domain.extraction import PageImage, Region, TextSpan
from domain.provenance.transform import AffineTransform
from tests.unit.fakes.pdfs import NV_20260042, render_invoice_pdf_bytes

_RENDER_DPI = 300.0
_DPI_SCALE = _RENDER_DPI / 72.0


def _preprocessed_page() -> PageImage:
    pdf_bytes = render_invoice_pdf_bytes(NV_20260042)
    return DeterministicPagePreprocessor(render_dpi=_RENDER_DPI).preprocess(pdf_bytes, 1)


def _working_span(text: str, image: PageImage) -> TextSpan:
    return TextSpan(text=text, page=image.page, bbox=[100.0, 200.0, 300.0, 240.0], coordinate_space="unstamped")


def test_preprocessor_scales_page_dims_by_dpi_and_names_the_coordinate_space() -> None:
    image = _preprocessed_page()

    assert image.page == 1
    assert image.dpi == _RENDER_DPI
    assert image.width == pytest.approx(595.0 * _DPI_SCALE)
    assert image.height == pytest.approx(842.0 * _DPI_SCALE)
    assert image.coordinate_space == f"page-1@{int(_RENDER_DPI)}dpi"
    assert image.image_bytes


def test_preprocessor_transform_maps_working_points_back_to_source_space() -> None:
    image = _preprocessed_page()

    to_source = AffineTransform.from_sequence(image.transform_to_source)
    source_x, source_y = to_source.apply_to_point(56.0 * _DPI_SCALE, 780.0 * _DPI_SCALE)

    assert source_x == pytest.approx(56.0, abs=1e-6)
    assert source_y == pytest.approx(780.0, abs=1e-6)


def test_preprocessor_is_deterministic_and_rejects_out_of_range_pages() -> None:
    pdf_bytes = render_invoice_pdf_bytes(NV_20260042)
    preprocessor = DeterministicPagePreprocessor(render_dpi=_RENDER_DPI)

    first = preprocessor.preprocess(pdf_bytes, 1)
    second = preprocessor.preprocess(pdf_bytes, 1)
    assert first.image_bytes == second.image_bytes

    with pytest.raises(ValueError, match="page"):
        preprocessor.preprocess(pdf_bytes, 2)


def test_scripted_ocr_restamps_spans_into_the_image_coordinate_space() -> None:
    image = _preprocessed_page()
    ocr = ScriptedOcrPass(spans_by_page={1: (_working_span("12500.00", image),)})

    output = ocr.recognize_text(image)

    assert output.method == "ocr"
    assert output.component_version == OCR_STUB_COMPONENT_VERSION
    assert output.transform_to_source == image.transform_to_source
    assert len(output.spans) == 1
    assert output.spans[0].coordinate_space == image.coordinate_space
    assert output.spans[0].page == image.page


def test_scripted_layout_restamps_regions_and_reports_detector_method() -> None:
    image = _preprocessed_page()
    region = Region(page=1, bbox=[10.0, 20.0, 400.0, 60.0], coordinate_space="unstamped", kind="kv", score=0.8)
    layout = ScriptedLayoutDetector(regions_by_page={1: (region,)})

    output = layout.detect_regions(image)

    assert output.method == "detector"
    assert output.component_version == LAYOUT_STUB_COMPONENT_VERSION
    assert len(output.regions) == 1
    assert output.regions[0].coordinate_space == image.coordinate_space
    assert output.regions[0].kind == "kv"


def test_echo_specialized_detector_refines_exactly_the_region_it_was_given() -> None:
    image = _preprocessed_page()
    region = Region(
        page=1, bbox=[56.0, 432.0, 500.0, 494.0], coordinate_space=image.coordinate_space, kind="table", score=0.7
    )

    output = EchoSpecializedDetector(kind="table").detect(image, region)

    assert output.method == "detector"
    assert output.component_version == DETECTOR_STUB_COMPONENT_VERSION
    assert output.regions == (region,)


def test_echo_specialized_detector_rejects_regions_of_the_wrong_kind() -> None:
    image = _preprocessed_page()
    region = Region(page=1, bbox=[0.0, 0.0, 1.0, 1.0], coordinate_space=image.coordinate_space, kind="kv", score=0.7)

    with pytest.raises(ValueError, match="kind"):
        EchoSpecializedDetector(kind="table").detect(image, region)
