"""Pinned parity test: `BornDigitalFingerprintExtractor` + `fpv.py` must
reproduce `fixtures/fpv1.py` byte-for-byte on the raw fixture PDFs.

Both fixture invoices place every label AND value at identical coordinates
(fixtures/pdfs/generate_pdfs.py's design constraint) so both MUST fingerprint
identically — and that shared key MUST equal `tmpl_nvinv.v1.json`'s stored
`fingerprint`, which `fixtures/build_bundle.py` stamped from the same
geometry via `fixtures/fpv1.py` directly. This test proves the platform-side
extractor (pypdf-based, from raw PDF bytes) agrees with that independent
source of truth without importing it.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from adapters.fingerprint import fpv
from adapters.fingerprint.born_digital import BornDigitalFingerprintExtractor
from domain.artifacts.canonical import JsonCanonicalSerializer

_PINNED_TMPL_NVINV_FINGERPRINT = "fpv1:sha256:c4ef0d493b22402722768efda21d570c9bd121ec6371ed6dffc3d99e33e6aac5"


def test_both_fixture_invoices_produce_the_same_fpv1_key_from_raw_pdf_bytes(
    fixture_pdf_path: Callable[[str], Path],
) -> None:
    extractor = BornDigitalFingerprintExtractor()
    serializer = JsonCanonicalSerializer()

    key_0042 = fpv.fingerprint_key(extractor.extract(fixture_pdf_path("nv_invoice_20260042").read_bytes()), serializer)
    key_0043 = fpv.fingerprint_key(extractor.extract(fixture_pdf_path("nv_invoice_20260043").read_bytes()), serializer)

    assert key_0042 == key_0043
    assert key_0042.startswith("fpv1:sha256:")


def test_fpv1_key_from_raw_pdf_bytes_equals_tmpl_nvinv_stored_fingerprint(
    fixture_pdf_path: Callable[[str], Path],
    load_fixture_artifact: Callable[[str], dict[str, Any]],
) -> None:
    extractor = BornDigitalFingerprintExtractor()
    serializer = JsonCanonicalSerializer()

    key = fpv.fingerprint_key(extractor.extract(fixture_pdf_path("nv_invoice_20260042").read_bytes()), serializer)

    stored_fingerprint = load_fixture_artifact("tmpl_nvinv.v1")["body"]["fingerprint"]
    assert key == stored_fingerprint
    assert key == _PINNED_TMPL_NVINV_FINGERPRINT
