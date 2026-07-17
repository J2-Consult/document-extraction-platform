"""Born-digital fingerprint extractor: native PDF text-line geometry via pypdf.

Reproduces `fixtures/fpv1.py`'s algorithm exactly (verified by a pinned
parity test against the two fixture invoice PDFs and `tmpl_nvinv.v1.json`'s
stored fingerprint): extract each text run's `(x, y, text, font_size)` from
the raw content-stream operators (`adapters.fingerprint._pdftext`), discard
the text before it ever reaches the fpv algorithm, and hand the geometry to
`fpv.py`'s registered algorithm for quantization + canonical structuring.

Excluded by construction: this module imports pypdf + this package's own
helpers only.
"""

from __future__ import annotations

from adapters.fingerprint import fpv
from adapters.fingerprint._pdftext import extract_raw_pages
from ports.fingerprint import FingerprintFeatures


class BornDigitalFingerprintExtractor:
    """`FingerprintFeatureExtractor` for born-digital (native-text) PDFs."""

    def __init__(self, *, fpv_version: int | None = None, timeout_s: float = 5.0) -> None:
        self._fpv_version = fpv_version if fpv_version is not None else fpv.current_version()
        self._timeout_s = timeout_s

    def extract(self, pdf_bytes: bytes) -> FingerprintFeatures:
        raw_pages = extract_raw_pages(pdf_bytes, timeout_s=self._timeout_s)
        algorithm = fpv.get_algorithm(self._fpv_version)
        return algorithm.build_features(page_count=len(raw_pages), pages=raw_pages)
