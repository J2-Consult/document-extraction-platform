"""In-memory fixture-PDF rendering helpers for E05 tests.

Re-renders the fixture invoices via `fixtures/pdfs/generate_pdfs.py`'s own
functions — never by editing `fixtures/` — including the y-shifted variant
the anchor-robustness tests need (specs/design/E05-interfaces.md: "generate
via fixtures/pdfs/generate_pdfs.py functions with a y-offset param in the
TEST"). Import shim mirrors `benchmarks/routing/decoys.py`'s.

Pure test helpers, never shipped.
"""

from __future__ import annotations

import sys
from pathlib import Path

_FIXTURES_PDFS_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "pdfs"
if str(_FIXTURES_PDFS_DIR) not in sys.path:
    sys.path.insert(0, str(_FIXTURES_PDFS_DIR))

import generate_pdfs as generate_pdfs  # type: ignore[import-not-found]  # noqa: E402  (fixtures/pdfs/generate_pdfs.py)

NV_20260042 = generate_pdfs.NV_20260042
NV_20260043 = generate_pdfs.NV_20260043


def render_invoice_pdf_bytes(data: object) -> bytes:
    """Byte-identical in-memory render of a fixture invoice."""
    return bytes(generate_pdfs.render_invoice_pdf(data))


def render_invoice_pdf_shifted(data: object, *, dy: float) -> bytes:
    """Re-render a fixture invoice with every text op shifted by `dy` points
    vertically — same glyphs, same x positions, translated layout."""
    ops = [generate_pdfs.TextOp(op.x, op.y + dy, op.font_size, op.text) for op in generate_pdfs.invoice_text_ops(data)]
    content = generate_pdfs._content_stream(ops)  # noqa: SLF001 — test-only reuse of the fixture writer
    page = (generate_pdfs.PAGE_WIDTH, generate_pdfs.PAGE_HEIGHT, content)
    return bytes(generate_pdfs._assemble_pdf([page]))  # noqa: SLF001


def render_textless_pdf_bytes() -> bytes:
    """A structurally valid one-page PDF with NO text operations — the
    stand-in for a scanned (image-only) document in cascade tests."""
    page = (generate_pdfs.PAGE_WIDTH, generate_pdfs.PAGE_HEIGHT, b"")
    return bytes(generate_pdfs._assemble_pdf([page]))  # noqa: SLF001
