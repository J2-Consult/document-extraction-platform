"""`ScannedFingerprintExtractor` honors the `FingerprintFeatureExtractor`
protocol (page-count/dims only, zero lines) — see its module docstring for
what a real rasterize+deskew implementation would add.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from adapters.fingerprint.scanned import ScannedFingerprintExtractor
from ports.fingerprint import FingerprintFeatureExtractor


def test_scanned_extractor_satisfies_the_fingerprint_feature_extractor_protocol() -> None:
    assert isinstance(ScannedFingerprintExtractor(), FingerprintFeatureExtractor)


def test_scanned_extractor_reports_page_count_and_dims_but_zero_lines(
    fixture_pdf_path: Callable[[str], Path],
) -> None:
    extractor = ScannedFingerprintExtractor()
    pdf_bytes = fixture_pdf_path("nv_invoice_20260042").read_bytes()

    features = extractor.extract(pdf_bytes)

    assert features.fpv == 1
    assert features.page_count == 1
    assert len(features.pages) == 1
    page = features.pages[0]
    assert page.lines == ()
    assert page.w_bucket > 0
    assert page.h_bucket > 0


def test_scanned_extractor_two_page_document_reports_two_pages(fixture_pdf_path: Callable[[str], Path]) -> None:
    extractor = ScannedFingerprintExtractor()
    pdf_bytes = fixture_pdf_path("mbr_report_001").read_bytes()

    features = extractor.extract(pdf_bytes)

    assert features.page_count == 2
    assert all(page.lines == () for page in features.pages)
