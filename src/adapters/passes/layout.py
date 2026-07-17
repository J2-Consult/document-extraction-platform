"""`LayoutDetector` adapter: deterministic layout stand-in.

STUBBED: no real layout analysis — candidate regions are supplied at
construction, keyed by page (real layout ML is provider-side).

REAL and load-bearing: the interface, region restamping into the working
image's coordinate space, and provenance stamping (method='detector').
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from domain.extraction import PageImage, PassOutput, Region

LAYOUT_STUB_COMPONENT_VERSION = "layout-detector-stub/1.0.0"


class ScriptedLayoutDetector:
    def __init__(self, *, regions_by_page: Mapping[int, Sequence[Region]]) -> None:
        self._regions_by_page = {page: tuple(regions) for page, regions in regions_by_page.items()}

    def detect_regions(self, image: PageImage) -> PassOutput:
        regions = tuple(
            region.model_copy(update={"coordinate_space": image.coordinate_space, "page": image.page})
            for region in self._regions_by_page.get(image.page, ())
        )
        return PassOutput(
            method="detector",
            component_version=LAYOUT_STUB_COMPONENT_VERSION,
            transform_to_source=list(image.transform_to_source),
            regions=regions,
        )
