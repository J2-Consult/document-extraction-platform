"""fpv1 - reference "fingerprint version 1" implementation.

Stdlib only. This module is the single source of truth for how a born-digital
document's page geometry is turned into a routing fingerprint. Both the fixture
builder (`build_bundle.py`, which stamps `tmpl_nvinv.v1.json`'s fingerprint from
known layout data) and any independent verification tooling (which re-extracts
geometry from the rendered PDF bytes) MUST call these functions rather than
reimplementing the algorithm, so that "same geometry -> same fingerprint" holds
by construction rather than by coincidence.

Design notes
------------
- Text CONTENT is excluded from the fingerprint by construction: only bounding
  boxes go into the hashed structure, never glyph strings.
- Coordinates are quantized to a coarse grid so that trivial rendering noise
  (sub-pixel differences, minor glyph-width variance) collapses to the same
  bucket instead of producing spurious fingerprint mismatches.
- `line_width_pt` is a *nominal* text-run width heuristic (not a real font
  metrics table). It only depends on character count and font size, so two
  runs with equal length and font size always produce byte-identical bboxes
  pre-quantization - which is what lets the two fixture invoices (identical
  layout, different digits) fingerprint identically.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

GRID_BBOX_PT = 8
GRID_DIM_PT = 4
LINE_HEIGHT_FACTOR = 1.2
CHAR_WIDTH_FACTOR = 0.5

BBox = tuple[float, float, float, float]


def canonical_json(obj: Any) -> bytes:
    """Deterministic JSON encoding: sorted keys, compact separators, UTF-8, no NaN."""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _quantize(value: float, grid: int) -> int:
    return int(round(value / grid)) * grid


def line_width_pt(text: str, font_size: float) -> float:
    """Nominal rendered width of a text run. Content-length driven, not glyph-driven."""
    return len(text) * font_size * CHAR_WIDTH_FACTOR


def line_bbox(x0: float, y0: float, text: str, font_size: float) -> BBox:
    """Nominal bbox for a single text run starting at (x0, y0) with the given font size."""
    width = line_width_pt(text, font_size)
    height = font_size * LINE_HEIGHT_FACTOR
    return (x0, y0, x0 + width, y0 + height)


def quantize_bbox(bbox: Sequence[float]) -> list[int]:
    return [_quantize(v, GRID_BBOX_PT) for v in bbox]


def build_features(page_count: int, pages: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Build the fpv1 feature structure from raw (unquantized) page geometry.

    `pages` is an iterable of {"width": float, "height": float, "lines": [bbox, ...]}.
    Lines are quantized and then sorted into a canonical order so that the
    feature structure - and therefore the fingerprint - does not depend on the
    order text was drawn or extracted in.
    """
    out_pages = []
    for page in pages:
        w_bucket = _quantize(page["width"], GRID_DIM_PT)
        h_bucket = _quantize(page["height"], GRID_DIM_PT)
        quantized_lines = [quantize_bbox(b) for b in page["lines"]]
        quantized_lines.sort(key=lambda b: (-b[1], b[0], -b[3], b[2]))
        out_pages.append({"w_bucket": w_bucket, "h_bucket": h_bucket, "lines": quantized_lines})
    return {"fpv": 1, "page_count": page_count, "pages": out_pages}


def fingerprint(features: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(canonical_json(features)).hexdigest()
    return f"fpv1:sha256:{digest}"
