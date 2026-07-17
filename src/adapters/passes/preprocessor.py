"""`PagePreprocessor` adapter: deterministic raster-preprocessing stand-in.

STUBBED: no real rasterization happens — `image_bytes` is a deterministic
placeholder derived from the source hash, page, and DPI (real rendering,
deskew, and denoise are provider-side engines).

REAL and load-bearing: page geometry comes from actually parsing the PDF
(pypdf), the working-space dimensions are the true dpi-scaled source dims,
and `transform_to_source` is computed from an E06 `PreprocessingRecord` —
the exact inverse-transform bookkeeping production preprocessing must
perform, which is what every downstream provenance depends on.
"""

from __future__ import annotations

import hashlib

from adapters.fingerprint._pdftext import extract_raw_pages
from domain.extraction import PageImage
from domain.provenance.preprocessing import PreprocessingRecord

PREPROCESSOR_COMPONENT_VERSION = "page-preprocessor-stub/1.0.0"

_SOURCE_DPI = 72.0  # PDF points are defined at 72 units per inch.


class DeterministicPagePreprocessor:
    def __init__(self, *, render_dpi: float = 300.0, timeout_s: float = 5.0) -> None:
        if render_dpi <= 0:
            raise ValueError("render_dpi must be positive")
        self._render_dpi = render_dpi
        self._timeout_s = timeout_s

    def preprocess(self, pdf_bytes: bytes, page: int) -> PageImage:
        raw_pages = extract_raw_pages(pdf_bytes, timeout_s=self._timeout_s)
        if not 1 <= page <= len(raw_pages):
            raise ValueError(f"page {page} out of range 1..{len(raw_pages)}")
        source_page = raw_pages[page - 1]

        record = PreprocessingRecord(
            render_dpi=self._render_dpi,
            deskew_angle_deg=0.0,
            crop=None,
            rotation_deg=0,
            pipeline_version=PREPROCESSOR_COMPONENT_VERSION,
        )
        scale = self._render_dpi / _SOURCE_DPI
        return PageImage(
            page=page,
            image_bytes=self._placeholder_raster(pdf_bytes, page),
            coordinate_space=f"page-{page}@{int(self._render_dpi)}dpi",
            dpi=self._render_dpi,
            width=source_page.width * scale,
            height=source_page.height * scale,
            transform_to_source=list(record.to_transform().inverse().as_tuple()),
        )

    def _placeholder_raster(self, pdf_bytes: bytes, page: int) -> bytes:
        source_hash = hashlib.sha256(pdf_bytes).hexdigest()
        return f"stub-raster:{source_hash}:page={page}:dpi={self._render_dpi}".encode("ascii")
