"""PypdfNativeTextPass: the REAL born-digital pass — pypdf text with source
coordinates, method='pdf_text', identity transform, full provenance stamping.
"""

from __future__ import annotations

import pytest

from adapters.fingerprint._pdftext import PdfExtractionError
from adapters.passes.native_text import NATIVE_TEXT_COMPONENT_VERSION, PypdfNativeTextPass
from domain.extraction import IDENTITY_TRANSFORM, TextSpan
from tests.unit.fakes.pdfs import NV_20260042, render_invoice_pdf_bytes, render_textless_pdf_bytes


def _span_by_text(spans: tuple[TextSpan, ...], text: str) -> TextSpan:
    matches = [span for span in spans if span.text == text]
    assert len(matches) == 1, f"expected exactly one span {text!r}, got {len(matches)}"
    return matches[0]


def test_born_digital_invoice_yields_pdf_text_spans_at_source_coordinates() -> None:
    output = PypdfNativeTextPass().extract_text(render_invoice_pdf_bytes(NV_20260042))

    assert output.method == "pdf_text"
    assert output.component_version == NATIVE_TEXT_COMPONENT_VERSION
    assert tuple(output.transform_to_source) == IDENTITY_TRANSFORM
    assert len(output.pages) == 1
    assert (output.pages[0].width, output.pages[0].height) == (595.0, 842.0)

    label = _span_by_text(output.spans, "Invoice number:")
    assert label.page == 1
    assert label.coordinate_space == "page-1"
    assert label.confidence == 1.0
    assert (label.bbox[0], label.bbox[1]) == (56.0, 780.0)
    assert label.bbox[2] > label.bbox[0] and label.bbox[3] > label.bbox[1]

    value = _span_by_text(output.spans, "2026-0042")
    assert (value.bbox[0], value.bbox[1]) == (206.0, 780.0)


def test_textless_pdf_yields_page_dims_but_no_spans() -> None:
    output = PypdfNativeTextPass().extract_text(render_textless_pdf_bytes())

    assert output.spans == ()
    assert len(output.pages) == 1
    assert output.pages[0].width == 595.0


def test_every_span_gets_a_provenance_fragment_with_pdf_text_method() -> None:
    output = PypdfNativeTextPass().extract_text(render_invoice_pdf_bytes(NV_20260042))

    fragments = output.provenance_fragments()

    assert len(fragments) == len(output.spans) > 0
    assert all(fragment.method == "pdf_text" for fragment in fragments)
    assert all(fragment.component_version == NATIVE_TEXT_COMPONENT_VERSION for fragment in fragments)


def test_garbage_bytes_raise_typed_extraction_error() -> None:
    with pytest.raises(PdfExtractionError):
        PypdfNativeTextPass().extract_text(b"MZ\x90\x00 this is not a pdf")
