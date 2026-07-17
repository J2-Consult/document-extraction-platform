"""`NativeTextPass` adapter: REAL born-digital text extraction via pypdf.

Reuses E04's raw content-stream walker (`adapters.fingerprint._pdftext`) and
turns each text run into a source-space `TextSpan`. Span bboxes use the same
nominal Helvetica metrics as the fpv1 fingerprint algorithm (width =
len(text) * font_size * 0.5, height = font_size * 1.2), so a template
assembled from these spans fingerprints identically to one computed from the
raw PDF.

Deterministic: confidence is always 1.0, transform is the identity (native
text is already in source space), coordinate space is `page-<n>` (the
fixture convention).
"""

from __future__ import annotations

from adapters.fingerprint._pdftext import RawLine, extract_raw_pages
from domain.extraction import IDENTITY_TRANSFORM, PageDims, PassOutput, TextSpan

NATIVE_TEXT_COMPONENT_VERSION = "pypdf-native-text/1.0.0"

# Nominal Helvetica line metrics — MUST match `adapters.fingerprint.fpv.
# Fpv1Algorithm` so assembled-template fingerprints reproduce from-PDF ones.
_CHAR_WIDTH_FACTOR = 0.5
_LINE_HEIGHT_FACTOR = 1.2


def _span_from_line(line: RawLine, page_number: int) -> TextSpan:
    width = len(line.text) * line.font_size * _CHAR_WIDTH_FACTOR
    height = line.font_size * _LINE_HEIGHT_FACTOR
    return TextSpan(
        text=line.text,
        page=page_number,
        bbox=[line.x0, line.y0, line.x0 + width, line.y0 + height],
        coordinate_space=f"page-{page_number}",
        confidence=1.0,
    )


class PypdfNativeTextPass:
    """Deterministic native-text pass. Hostile-file safe: bounded by
    `timeout_s`, raises `PdfExtractionError` on unparseable input."""

    def __init__(self, *, timeout_s: float = 5.0) -> None:
        self._timeout_s = timeout_s

    def extract_text(self, pdf_bytes: bytes) -> PassOutput:
        raw_pages = extract_raw_pages(pdf_bytes, timeout_s=self._timeout_s)
        spans = tuple(
            _span_from_line(line, page_number)
            for page_number, page in enumerate(raw_pages, start=1)
            for line in page.lines
        )
        pages = tuple(
            PageDims(page=page_number, width=page.width, height=page.height)
            for page_number, page in enumerate(raw_pages, start=1)
        )
        return PassOutput(
            method="pdf_text",
            component_version=NATIVE_TEXT_COMPONENT_VERSION,
            transform_to_source=list(IDENTITY_TRANSFORM),
            pages=pages,
            spans=spans,
        )
