"""TargetedExtractor (epic E05): the anchor-based fast path.

Label-TEXT-first matching: each anchored template element is located by
finding its label text in the document's native text layer and reading the
value region at the label's measured offset — a re-render whose layout
shifted by a few points still resolves every element, because the offset
moves with the label. Anchorless elements (tables) follow the MEDIAN shift of
the matched anchors. Value states follow E01 legality:

    present    - legible spans in the region; `value` is the joined text
    empty      - region located, confidently nothing in it; `value` null
    unreadable - spans in the region but below the legibility threshold
    not_found  - the label text is absent from the document

Every observation carries full provenance (source hash, page, the bbox that
was actually read, method, component version, transform) — including the
absence states: "we looked HERE and found nothing" is part of the record.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from statistics import median

from domain.artifacts.content import Confidence, Observation, ValueState
from domain.artifacts.provenance import Provenance, SourceRef, WorkingRef
from domain.artifacts.template import TemplateBody, TemplateElement
from domain.extraction import PassOutput, TextSpan
from ports.extraction_passes import NativeTextPass

# A recognized span below this confidence is illegible: the region was
# located, but its content cannot be trusted as a value (-> `unreadable`).
LEGIBILITY_THRESHOLD = 0.5

# Calibrated routing confidence is deliberately more conservative than the
# recognizer's raw score (deterministic native text: raw 1.0 -> 0.97).
_CALIBRATION_FACTOR = 0.97

_Shift = tuple[float, float]

# The recognizer is deterministic about absence: an assertion made from the
# whole text layer (label absent, region blank) starts from full raw score.
_FULL_RAW_SCORE = 1.0


class TargetedExtractor:
    """Fast path: one native-text read, anchor-matched value regions."""

    def __init__(self, native_text: NativeTextPass) -> None:
        self._native_text = native_text

    def extract(self, pdf_bytes: bytes, template: TemplateBody) -> list[Observation]:
        output = self._native_text.extract_text(pdf_bytes)
        if not output.pages:
            raise ValueError("native text output carries no page dimensions")
        source_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
        labels = {
            element.element_id: _match_label(element, output.spans)
            for element in template.elements
            if element.anchor is not None
        }
        fallback_shift = _median_shift(template, labels)
        return [
            _observe(element, labels.get(element.element_id), fallback_shift, output, source_sha256)
            for element in template.elements
        ]


def _observe(
    element: TemplateElement,
    label: TextSpan | None,
    fallback_shift: _Shift,
    output: PassOutput,
    source_sha256: str,
) -> Observation:
    region = _read_region(element, label, fallback_shift)
    provenance = _provenance(element.page, region, output, source_sha256)
    if element.anchor is not None and label is None:
        return _observation(element, None, "not_found", _FULL_RAW_SCORE, provenance)
    spans = _spans_in_region(output.spans, element.page, region)
    if not spans:
        blank_raw = label.confidence if label is not None else _FULL_RAW_SCORE
        return _observation(element, None, "empty", blank_raw, provenance)
    raw = min(span.confidence for span in spans)
    if raw < LEGIBILITY_THRESHOLD:
        return _observation(element, None, "unreadable", raw, provenance)
    return _observation(element, _joined_text(spans), "present", raw, provenance)


def _observation(
    element: TemplateElement,
    value: str | None,
    state: ValueState,
    raw: float,
    provenance: Provenance,
) -> Observation:
    return Observation(
        element_id=element.element_id,
        value=value,
        state=state,
        confidence=Confidence(raw=raw, calibrated=raw * _CALIBRATION_FACTOR),
        provenance=provenance,
    )


def _match_label(element: TemplateElement, spans: Sequence[TextSpan]) -> TextSpan | None:
    """The span carrying the anchor's label text, nearest its expected spot."""
    anchor = element.anchor
    if anchor is None:
        return None
    candidates = [span for span in spans if span.page == element.page and span.text == anchor.label_text]
    if not candidates:
        return None
    expected_x, expected_y = anchor.label_bbox[0], anchor.label_bbox[1]
    return min(candidates, key=lambda span: (span.bbox[0] - expected_x) ** 2 + (span.bbox[1] - expected_y) ** 2)


def _median_shift(template: TemplateBody, labels: dict[str, TextSpan | None]) -> _Shift:
    """The document-level shift anchorless elements follow: the median of the
    matched anchors' individual offsets (robust to a single mismatch)."""
    shifts = _anchor_shifts(template, labels)
    if not shifts:
        return (0.0, 0.0)
    return (median(dx for dx, _ in shifts), median(dy for _, dy in shifts))


def _anchor_shifts(template: TemplateBody, labels: dict[str, TextSpan | None]) -> list[_Shift]:
    shifts: list[_Shift] = []
    for element in template.elements:
        anchor = element.anchor
        span = labels.get(element.element_id)
        if anchor is None or span is None:
            continue
        shifts.append((span.bbox[0] - anchor.label_bbox[0], span.bbox[1] - anchor.label_bbox[1]))
    return shifts


def _read_region(element: TemplateElement, label: TextSpan | None, fallback_shift: _Shift) -> list[float]:
    """Where to look for this element's value: the template bbox, moved by
    the element's own anchor offset when its label matched, by the document's
    median anchor shift otherwise."""
    anchor = element.anchor
    if anchor is not None and label is not None:
        return _shifted(element.bbox, label.bbox[0] - anchor.label_bbox[0], label.bbox[1] - anchor.label_bbox[1])
    return _shifted(element.bbox, *fallback_shift)


def _shifted(bbox: Sequence[float], dx: float, dy: float) -> list[float]:
    return [bbox[0] + dx, bbox[1] + dy, bbox[2] + dx, bbox[3] + dy]


def _spans_in_region(spans: Sequence[TextSpan], page: int, region: Sequence[float]) -> list[TextSpan]:
    """Spans whose center lies inside the region, on the element's page."""
    x0, y0, x1, y1 = region
    selected: list[TextSpan] = []
    for span in spans:
        if span.page != page:
            continue
        center_x = (span.bbox[0] + span.bbox[2]) / 2
        center_y = (span.bbox[1] + span.bbox[3]) / 2
        if x0 <= center_x <= x1 and y0 <= center_y <= y1:
            selected.append(span)
    return selected


def _joined_text(spans: Sequence[TextSpan]) -> str:
    """Region text, reading order: rows top to bottom joined by newlines,
    spans within a row left to right joined by spaces."""
    ordered = sorted(spans, key=lambda span: (-span.bbox[1], span.bbox[0]))
    rows: list[list[TextSpan]] = []
    for span in ordered:
        if rows and _same_row(rows[-1][0], span):
            rows[-1].append(span)
        else:
            rows.append([span])
    return "\n".join(" ".join(span.text for span in row) for row in rows)


def _same_row(a: TextSpan, b: TextSpan) -> bool:
    return a.bbox[1] < b.bbox[3] and b.bbox[1] < a.bbox[3]


def _provenance(page: int, region: Sequence[float], output: PassOutput, source_sha256: str) -> Provenance:
    return Provenance(
        source=SourceRef(artifact_sha256=source_sha256, page=page),
        working=WorkingRef(artifact_sha256=source_sha256, coordinate_space=f"page-{page}"),
        bbox=list(region),
        method=output.method,
        component_version=output.component_version,
        transform_to_source=list(output.transform_to_source),
    )
