"""Shared native-PDF raw text-line geometry extraction (pypdf-based).

Single low-level primitive shared by `born_digital.py` (which discards the
text and keeps geometry only, for fingerprinting) and `verifier.py` (which
also needs the text, for label-anchor verification). Both are native PDF
parsing via pypdf — never OCR, never a model call.

Implementation note: pypdf's high-level `extract_text(visitor_text=...)`
callback applies its own layout heuristics (synthetic space insertion,
stale/coalesced text-matrix reporting on some transitions) that corrupt
per-run coordinates for a simple absolute-positioning content stream like
ours. `visitor_operand_before` gives the raw operator stream instead (`Tf`,
`Tm`, `Tj`) — this module walks that stream itself and reads position
(`Tm`'s translation), font size (`Tf`), and text (`Tj`'s operand) directly,
which is exact for the fixture PDFs' one-`Tj`-per-`BT`/`ET`-block layout
(see `fixtures/pdfs/generate_pdfs.py`) and safe (just doesn't merge runs) for
denser layouts.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from pypdf import PdfReader

from adapters.fingerprint._timeout import BoundedTimeoutError, run_bounded


@dataclass(frozen=True)
class RawLine:
    """One text run's un-quantized geometry, as extracted from a PDF page."""

    x0: float
    y0: float
    text: str
    font_size: float


@dataclass(frozen=True)
class RawPage:
    width: float
    height: float
    lines: tuple[RawLine, ...]


class PdfExtractionError(RuntimeError):
    """Raised when `pdf_bytes` cannot be parsed, or parsing exceeds its time budget."""


def extract_raw_pages(pdf_bytes: bytes, *, timeout_s: float = 5.0) -> tuple[RawPage, ...]:
    """Extract per-page text-line geometry from raw PDF bytes.

    Hostile-file safe: bounded by `timeout_s`; never shells out; wraps
    library parse errors in `PdfExtractionError` rather than letting pypdf's
    internal exception types leak to callers.
    """
    try:
        return run_bounded(_extract_raw_pages, pdf_bytes, timeout_s=timeout_s)
    except BoundedTimeoutError as exc:
        raise PdfExtractionError(f"pdf extraction exceeded {timeout_s}s budget") from exc


def _extract_raw_pages(pdf_bytes: bytes) -> tuple[RawPage, ...]:
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        return tuple(_extract_page(page) for page in reader.pages)
    except PdfExtractionError:
        raise
    except Exception as exc:  # noqa: BLE001 - hostile input: any pypdf failure becomes a typed error
        raise PdfExtractionError(f"failed to parse PDF: {type(exc).__name__}") from exc


def _extract_page(page: Any) -> RawPage:
    state: dict[str, float | None] = {"font_size": None, "x": None, "y": None}
    lines: list[RawLine] = []

    def visitor_operand_before(op: bytes, args: Sequence[Any], cm: Any, tm: Any) -> None:
        if op == b"Tf" and len(args) >= 2:
            state["font_size"] = float(args[1])
        elif op == b"Tm" and len(args) >= 6:
            state["x"] = float(args[4])
            state["y"] = float(args[5])
        elif op == b"Tj" and args:
            _record_line(state, args[0], lines)

    page.extract_text(visitor_operand_before=visitor_operand_before)
    width = float(page.mediabox.width)
    height = float(page.mediabox.height)
    return RawPage(width=width, height=height, lines=tuple(lines))


def _record_line(state: dict[str, float | None], raw_operand: Any, lines: list[RawLine]) -> None:
    x0, y0, font_size = state["x"], state["y"], state["font_size"]
    if x0 is None or y0 is None or font_size is None:
        return
    text = raw_operand.decode("latin-1") if isinstance(raw_operand, bytes) else str(raw_operand)
    if not text.strip():
        return
    lines.append(RawLine(x0=x0, y0=y0, text=text, font_size=font_size))
