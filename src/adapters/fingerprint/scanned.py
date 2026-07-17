"""Scanned-document fingerprint extractor: post-deskew geometry stub.

Real scanned PDFs carry no extractable text layer, so the born-digital
strategy (native `Tm`/`Tj` geometry) does not apply. A production
implementation would:

1. Rasterize each page at a fixed, low DPI.
2. Deskew via a Hough-line or projection-profile angle estimate.
3. Binarize and derive line/column bounding boxes from horizontal/vertical
   ink-projection peaks — geometry only, no OCR, no glyph classification,
   matching the born-digital strategy's content-blind contract.
4. Quantize identically to `fpv.py`'s grid, so the two strategies produce
   directly comparable keys for the same fpv version.

This stub honors the `FingerprintFeatureExtractor` protocol so it can be
wired into the router today, without a rasterization dependency (no new
dependency this epic): it extracts only page count + page dimensions
(bucketed) via pypdf's page metadata — never pixels, never text — and
reports zero lines per page. Fingerprints produced by this stub are
consequently coarse (page-count/size only) and will alias across
same-sized scanned documents; that degradation is intentional and
documented here rather than papered over with a fabricated result.
"""

from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader

from adapters.fingerprint import fpv
from adapters.fingerprint._timeout import BoundedTimeoutError, run_bounded
from ports.fingerprint import FingerprintFeatures


class ScannedFingerprintExtractionError(RuntimeError):
    """Raised when `pdf_bytes` cannot be parsed, or parsing exceeds its time budget."""


class ScannedFingerprintExtractor:
    """`FingerprintFeatureExtractor` stub for scanned (image-only) PDFs."""

    def __init__(self, *, fpv_version: int | None = None, timeout_s: float = 5.0) -> None:
        self._fpv_version = fpv_version if fpv_version is not None else fpv.current_version()
        self._timeout_s = timeout_s

    def extract(self, pdf_bytes: bytes) -> FingerprintFeatures:
        try:
            dims = run_bounded(self._read_page_dims, pdf_bytes, timeout_s=self._timeout_s)
        except BoundedTimeoutError as exc:
            raise ScannedFingerprintExtractionError(f"exceeded {self._timeout_s}s budget") from exc
        algorithm = fpv.get_algorithm(self._fpv_version)
        pages: list[fpv.PageBBoxes] = [(width, height, []) for width, height in dims]
        return algorithm.features_from_bboxes(page_count=len(pages), pages=pages)

    @staticmethod
    def _read_page_dims(pdf_bytes: bytes) -> list[tuple[float, float]]:
        try:
            reader = PdfReader(BytesIO(pdf_bytes))
            return [(float(page.mediabox.width), float(page.mediabox.height)) for page in reader.pages]
        except Exception as exc:  # noqa: BLE001 - hostile input: any pypdf failure becomes a typed error
            raise ScannedFingerprintExtractionError(f"failed to parse PDF: {type(exc).__name__}") from exc
