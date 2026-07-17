"""fpv (fingerprint version) registry: version -> algorithm (quantization
grid + feature-building rules). Bump machinery + a stored-template re-keying
helper live here so a fpv version change never means editing fpv1's behavior
in place (open/closed) — see `Fpv1Algorithm`'s docstring for what "bump"
means in practice.

Does NOT import `fixtures/fpv1.py`: `src/` never depends on the `fixtures/`
test-data tree at runtime (the same rule `src/domain/registry.py` follows for
packaged target schemas). fpv1's formulas are reimplemented here from
`specs/FIXTURES-SPEC.md`'s frozen spec; byte-parity with `fixtures/fpv1.py`
is proven by a pinned test
(`tests/unit/adapters/fingerprint/test_born_digital_fpv1_parity.py`), not by
sharing code with it.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Protocol

from adapters.fingerprint._pdftext import RawPage
from ports.canonical import CanonicalSerializer
from ports.fingerprint import FingerprintFeatures, FingerprintPage

BBox = tuple[float, float, float, float]
# (width, height, raw un-quantized bboxes) for one page — the shape
# `rekey_template_fingerprint` builds directly from a stored template body's
# element/anchor bboxes, bypassing PDF re-parsing entirely.
PageBBoxes = tuple[float, float, Sequence[BBox]]


class UnknownFpvVersionError(KeyError):
    """No algorithm is registered for the requested fpv version."""


class FpvAlgorithmAlreadyRegisteredError(ValueError):
    """`register_algorithm` refuses to overwrite an already-registered version."""


class FpvAlgorithm(Protocol):
    version: int
    grid_bbox_pt: int
    grid_dim_pt: int

    def build_features(self, page_count: int, pages: Sequence[RawPage]) -> FingerprintFeatures: ...

    def features_from_bboxes(self, page_count: int, pages: Sequence[PageBBoxes]) -> FingerprintFeatures: ...

    def quantize_dims(self, width: float, height: float) -> tuple[int, int]: ...


def _quantize(value: float, grid: int) -> int:
    return int(round(value / grid)) * grid


class Fpv1Algorithm:
    """fpv1: reproduces `fixtures/fpv1.py`'s `build_features`/`fingerprint`
    exactly (8pt bbox grid, 4pt page-dimension grid, nominal
    length*font_size-driven line width — text content never enters the
    algorithm beyond that length). A genuine algorithm change (new grid, new
    feature shape, ...) is registered as a NEW `FpvAlgorithm` + `register_algorithm`
    call, never an edit to this class.
    """

    version = 1
    grid_bbox_pt = 8
    grid_dim_pt = 4
    _line_height_factor = 1.2
    _char_width_factor = 0.5

    def _line_bbox(self, x0: float, y0: float, text: str, font_size: float) -> BBox:
        width = len(text) * font_size * self._char_width_factor
        height = font_size * self._line_height_factor
        return (x0, y0, x0 + width, y0 + height)

    def build_features(self, page_count: int, pages: Sequence[RawPage]) -> FingerprintFeatures:
        bbox_pages: list[PageBBoxes] = [
            (
                page.width,
                page.height,
                [self._line_bbox(line.x0, line.y0, line.text, line.font_size) for line in page.lines],
            )
            for page in pages
        ]
        return self.features_from_bboxes(page_count, bbox_pages)

    def features_from_bboxes(self, page_count: int, pages: Sequence[PageBBoxes]) -> FingerprintFeatures:
        out_pages = []
        for width, height, bboxes in pages:
            w_bucket, h_bucket = self.quantize_dims(width, height)
            quantized = sorted(
                (self._quantize_bbox(bbox) for bbox in bboxes),
                key=lambda b: (-b[1], b[0], -b[3], b[2]),
            )
            out_pages.append(FingerprintPage(w_bucket=w_bucket, h_bucket=h_bucket, lines=tuple(quantized)))
        return FingerprintFeatures(fpv=self.version, page_count=page_count, pages=tuple(out_pages))

    def quantize_dims(self, width: float, height: float) -> tuple[int, int]:
        return (_quantize(width, self.grid_dim_pt), _quantize(height, self.grid_dim_pt))

    def _quantize_bbox(self, bbox: Sequence[float]) -> tuple[int, int, int, int]:
        q = [_quantize(v, self.grid_bbox_pt) for v in bbox]
        return (q[0], q[1], q[2], q[3])


_ALGORITHMS: dict[int, FpvAlgorithm] = {1: Fpv1Algorithm()}


def current_version() -> int:
    return max(_ALGORITHMS)


def get_algorithm(version: int) -> FpvAlgorithm:
    try:
        return _ALGORITHMS[version]
    except KeyError as exc:
        raise UnknownFpvVersionError(f"no fpv algorithm registered for version {version}") from exc


def register_algorithm(algorithm: FpvAlgorithm) -> None:
    """Bump machinery: register a new fpv version. Refuses to overwrite an
    already-registered version — a genuine algorithm change is a NEW version
    number, never a behavior edit to an existing one (open/closed)."""
    if algorithm.version in _ALGORITHMS:
        raise FpvAlgorithmAlreadyRegisteredError(f"fpv{algorithm.version} is already registered")
    _ALGORITHMS[algorithm.version] = algorithm


def fingerprint_key(features: FingerprintFeatures, serializer: CanonicalSerializer) -> str:
    canonical = serializer.canonical_bytes(features.model_dump(mode="json"))
    digest = hashlib.sha256(canonical).hexdigest()
    return f"fpv{features.fpv}:sha256:{digest}"


def rekey_template_fingerprint(
    *,
    page_count: int,
    pages: Sequence[PageBBoxes],
    fpv_version: int,
    serializer: CanonicalSerializer,
) -> str:
    """Recompute a stored template's fingerprint under `fpv_version` from its
    OWN body geometry (page dims + element/anchor bboxes) instead of
    re-parsing its original source PDF.

    Used when bumping the fpv algorithm (new grid, new feature shape, ...):
    existing candidate-index entries must be re-keyed, and the source PDF
    may not be cheaply available at that point. This is a documented
    approximation — element bboxes are template geometry, not raw per-run
    text bboxes — so it is used only to migrate the routing candidate index,
    never asserted byte-identical to a fresh from-PDF extraction (that parity
    is fpv1's pinned test's job).
    """
    algorithm = get_algorithm(fpv_version)
    return fingerprint_key(algorithm.features_from_bboxes(page_count, pages), serializer)
