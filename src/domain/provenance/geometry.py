"""Per-page source geometry recorded for provenance.

Distinct from `domain.artifacts.template.PageGeometry` (E01, template-authoring
concern: "where things are on a page for extraction purposes") — this is the
provenance side's record of a document's actual page geometry, used to bound
`Provenance.source.page` and to prove mixed-page-size documents (e.g. an A4
page followed by a Letter page) are legal, per FIXTURES-SPEC.md / the E06
epic. Each page's dimensions are validated independently, never against its
neighbors.

Pure Python: no I/O, no framework imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RotationDegrees = Literal[0, 90, 180, 270]


@dataclass(frozen=True, slots=True)
class PageGeometry:
    """One page's physical geometry: 1-indexed page number, size, unit, and
    structural (multiple-of-90) rotation."""

    page: int
    width: float
    height: float
    unit: Literal["pt"]
    rotation: RotationDegrees

    def __post_init__(self) -> None:
        if self.page < 1:
            raise ValueError("page must be >= 1")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("page width and height must both be > 0")


@dataclass(frozen=True, slots=True)
class DocumentGeometry:
    """A document's full page geometry. Mixed page sizes are legal — the
    invariant enforced here is only that page numbers are exactly
    `1..len(pages)` (no gaps, no duplicates), which is what lets the
    validator bound a `Provenance.source.page` against a known range.
    """

    pages: tuple[PageGeometry, ...]

    def __post_init__(self) -> None:
        if not self.pages:
            raise ValueError("a document must have at least one page")
        page_numbers = sorted(page.page for page in self.pages)
        expected = list(range(1, len(self.pages) + 1))
        if page_numbers != expected:
            raise ValueError(f"page numbers must be exactly 1..{len(self.pages)}, got {page_numbers}")

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def contains_page(self, page: int) -> bool:
        return 1 <= page <= self.page_count

    def page_geometry(self, page: int) -> PageGeometry:
        for geometry in self.pages:
            if geometry.page == page:
                return geometry
        raise KeyError(f"no geometry recorded for page {page}")
