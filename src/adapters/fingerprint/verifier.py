"""Default `TemplateVerifier`: bounded discriminating checks over native PDF
text (page geometry, label anchors, major regions, table boundaries).

Placement note (flagged per the task brief): this lives under
`src/adapters/fingerprint/` rather than `src/services/routing/`. Every check
here re-parses `pdf_bytes` via the same pypdf primitive `born_digital.py`
uses (`adapters.fingerprint._pdftext`), so keeping it in this package means
the "no OCR/VLM/provider imports" architecture test covers it for free,
instead of needing a parallel test under `services/`.

Checks (each bounded by its own hard time budget):
  - `page_geometry`: PDF page count/dimensions (quantized) vs the
    candidate's declared pages.
  - `label_anchors`: for every element with an `anchor`, is the expected
    label text actually present at (approximately) the anchor's bbox? This
    is what a decoy with moved/rotated labels fails.
  - `major_regions`: for non-table, non-optional elements, is *some* text
    present within the element's own bbox (the region is populated, not
    blank)?
  - `table_boundaries` (only emitted when the candidate has table
    elements): does each table's bbox contain at least as many text runs as
    it has declared columns (a header row is present)?
  - Negative anchors are optional and NOT emitted: the template contract
    (`domain.artifacts.template.TemplateElement`) carries no negative-anchor
    data to check against, so there is nothing to evaluate. A future
    template shape that adds negative anchors would add a new bounded check
    here, not modify the ones above (open/closed).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from adapters.fingerprint import fpv
from adapters.fingerprint._pdftext import PdfExtractionError, RawLine, RawPage, extract_raw_pages
from adapters.fingerprint._timeout import BoundedTimeoutError, run_bounded
from domain.artifacts.template import TemplateBody, TemplateElement
from ports.fingerprint import FingerprintFeatures
from ports.verification import VerificationCheck, VerificationResult, VerificationStatus

_LABEL_ANCHOR_MATCH_THRESHOLD = 1.0
_MAJOR_REGION_MATCH_THRESHOLD = 0.7
_ANCHOR_POSITION_TOLERANCE_PT = 6.0
_REGION_MATCH_MARGIN_PT = 4.0
_DEFAULT_CHECK_TIMEOUT_S = 2.0


class NativePdfTemplateVerifier:
    """`TemplateVerifier` backed by native PDF text extraction (no OCR/VLM)."""

    def __init__(self, *, timeout_s: float = 5.0, check_timeout_s: float = _DEFAULT_CHECK_TIMEOUT_S) -> None:
        self._timeout_s = timeout_s
        self._check_timeout_s = check_timeout_s

    def verify(self, features: FingerprintFeatures, pdf_bytes: bytes, candidate: TemplateBody) -> VerificationResult:
        try:
            pages = extract_raw_pages(pdf_bytes, timeout_s=self._timeout_s)
        except PdfExtractionError as exc:
            check = VerificationCheck(check_id="pdf_parse", passed=None, detail=f"unparseable: {type(exc).__name__}")
            return VerificationResult(status="inconclusive", checks=(check,))

        checks: list[VerificationCheck] = [
            self._bounded("page_geometry", _check_page_geometry, features, pages, candidate),
            self._bounded("label_anchors", _check_label_anchors, pages, candidate),
            self._bounded("major_regions", _check_major_regions, pages, candidate),
        ]
        table_check = self._bounded("table_boundaries", _check_table_boundaries, pages, candidate)
        if table_check.detail != _NOT_APPLICABLE:
            checks.append(table_check)

        return VerificationResult(status=_aggregate(checks), checks=tuple(checks))

    def _bounded(self, check_id: str, fn: Callable[..., VerificationCheck], *args: object) -> VerificationCheck:
        try:
            return run_bounded(fn, check_id, *args, timeout_s=self._check_timeout_s)
        except BoundedTimeoutError:
            return VerificationCheck(check_id=check_id, passed=None, detail=f"exceeded {self._check_timeout_s}s budget")


_NOT_APPLICABLE = "__not_applicable__"


def _aggregate(checks: Sequence[VerificationCheck]) -> VerificationStatus:
    if any(check.passed is False for check in checks):
        return "rejected"
    if any(check.passed is None for check in checks):
        return "inconclusive"
    return "accepted"


def _page_at(pages: Sequence[RawPage], page_number: int) -> RawPage | None:
    index = page_number - 1
    if 0 <= index < len(pages):
        return pages[index]
    return None


def _check_page_geometry(
    check_id: str, features: FingerprintFeatures, pages: Sequence[RawPage], candidate: TemplateBody
) -> VerificationCheck:
    if features.page_count != candidate.page_count or len(pages) != candidate.page_count:
        return VerificationCheck(
            check_id=check_id,
            passed=False,
            detail=f"page count mismatch: pdf={len(pages)} candidate={candidate.page_count}",
        )
    algorithm = fpv.get_algorithm(features.fpv)
    candidate_pages = {page.page: page for page in candidate.pages}
    for index, page in enumerate(pages):
        candidate_page = candidate_pages.get(index + 1)
        if candidate_page is None:
            return VerificationCheck(check_id=check_id, passed=False, detail=f"no candidate page {index + 1}")
        pdf_dims = algorithm.quantize_dims(page.width, page.height)
        candidate_dims = algorithm.quantize_dims(candidate_page.width, candidate_page.height)
        if pdf_dims != candidate_dims:
            return VerificationCheck(check_id=check_id, passed=False, detail=f"page {index + 1} dims mismatch")
    return VerificationCheck(check_id=check_id, passed=True, detail=f"{len(pages)} page(s) match")


def _anchor_matches(element: TemplateElement, lines: Sequence[RawLine]) -> bool:
    assert element.anchor is not None  # guarded by caller
    label_x0, label_y0, _, _ = element.anchor.label_bbox
    for line in lines:
        close_x = abs(line.x0 - label_x0) <= _ANCHOR_POSITION_TOLERANCE_PT
        close_y = abs(line.y0 - label_y0) <= _ANCHOR_POSITION_TOLERANCE_PT
        if close_x and close_y:
            return line.text.strip() == element.anchor.label_text.strip()
    return False


def _check_label_anchors(check_id: str, pages: Sequence[RawPage], candidate: TemplateBody) -> VerificationCheck:
    anchored = [element for element in candidate.elements if element.anchor is not None]
    if not anchored:
        return VerificationCheck(check_id=check_id, passed=True, detail="no anchored elements")
    matched = 0
    for element in anchored:
        page = _page_at(pages, element.page)
        lines = page.lines if page is not None else ()
        if _anchor_matches(element, lines):
            matched += 1
    fraction = matched / len(anchored)
    passed = fraction >= _LABEL_ANCHOR_MATCH_THRESHOLD
    return VerificationCheck(check_id=check_id, passed=passed, detail=f"{matched}/{len(anchored)} anchors matched")


def _bbox_has_content(bbox: Sequence[float], lines: Sequence[RawLine]) -> bool:
    x0, y0, x1, y1 = bbox
    for line in lines:
        within_x = (x0 - _REGION_MATCH_MARGIN_PT) <= line.x0 <= (x1 + _REGION_MATCH_MARGIN_PT)
        within_y = (y0 - _REGION_MATCH_MARGIN_PT) <= line.y0 <= (y1 + _REGION_MATCH_MARGIN_PT)
        if within_x and within_y:
            return True
    return False


def _check_major_regions(check_id: str, pages: Sequence[RawPage], candidate: TemplateBody) -> VerificationCheck:
    required = [
        element for element in candidate.elements if element.kind != "table" and not (element.optional or False)
    ]
    if not required:
        return VerificationCheck(check_id=check_id, passed=True, detail="no required non-table elements")
    present = 0
    for element in required:
        page = _page_at(pages, element.page)
        lines = page.lines if page is not None else ()
        if _bbox_has_content(element.bbox, lines):
            present += 1
    fraction = present / len(required)
    passed = fraction >= _MAJOR_REGION_MATCH_THRESHOLD
    return VerificationCheck(check_id=check_id, passed=passed, detail=f"{present}/{len(required)} regions populated")


def _check_table_boundaries(check_id: str, pages: Sequence[RawPage], candidate: TemplateBody) -> VerificationCheck:
    tables = [element for element in candidate.elements if element.kind == "table"]
    if not tables:
        return VerificationCheck(check_id=check_id, passed=None, detail=_NOT_APPLICABLE)
    present = 0
    for table in tables:
        page = _page_at(pages, table.page)
        lines = page.lines if page is not None else ()
        x0, y0, x1, y1 = table.bbox
        count = sum(
            1
            for line in lines
            if (x0 - _REGION_MATCH_MARGIN_PT) <= line.x0 <= (x1 + _REGION_MATCH_MARGIN_PT)
            and (y0 - _REGION_MATCH_MARGIN_PT) <= line.y0 <= (y1 + _REGION_MATCH_MARGIN_PT)
        )
        min_expected = len(table.columns or [])
        if count >= min_expected:
            present += 1
    passed = present == len(tables)
    detail = f"{present}/{len(tables)} tables with header row present"
    return VerificationCheck(check_id=check_id, passed=passed, detail=detail)
