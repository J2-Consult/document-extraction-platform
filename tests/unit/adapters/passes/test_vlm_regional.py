"""ProviderBackedRegionalVlmFallback: the REAL wiring from a validated
provider response to a provenance-stamped PassOutput — one region per call,
component version combining wrapper and model.
"""

from __future__ import annotations

from adapters.passes.vlm_regional import VLM_REGIONAL_COMPONENT_VERSION, ProviderBackedRegionalVlmFallback
from domain.extraction import PageImage, Region
from ports.providers import ProviderResponse


class _StaticValidatedProvider:
    def __init__(self, response: ProviderResponse) -> None:
        self.response = response
        self.calls: list[tuple[PageImage, Region, str]] = []

    def read_region(self, image: PageImage, region: Region, job_ref: str) -> ProviderResponse:
        self.calls.append((image, region, job_ref))
        return self.response


def _image() -> PageImage:
    return PageImage(
        page=1,
        image_bytes=b"raster",
        coordinate_space="page-1@300dpi",
        dpi=300.0,
        width=2479.0,
        height=3508.0,
        transform_to_source=[0.24, 0.0, 0.0, 0.24, 0.0, 0.0],
    )


def _region(score: float = 0.4) -> Region:
    return Region(
        page=1, bbox=[858.0, 2650.0, 1442.0, 2700.0], coordinate_space="page-1@300dpi", kind="text", score=score
    )


def test_readable_region_becomes_one_vlm_region_span_with_combined_component_version() -> None:
    provider = _StaticValidatedProvider(
        ProviderResponse(text="Net 30 days", raw_confidence=0.88, cost=0.02, model_version="vlm-x/2.1")
    )
    fallback = ProviderBackedRegionalVlmFallback(provider)

    output = fallback.read_region(_image(), _region(), "job-7f3a")

    assert output.method == "vlm_region"
    assert VLM_REGIONAL_COMPONENT_VERSION in output.component_version
    assert "vlm-x/2.1" in output.component_version
    assert output.transform_to_source == _image().transform_to_source
    assert len(output.spans) == 1
    span = output.spans[0]
    assert span.text == "Net 30 days"
    assert span.confidence == 0.88
    assert span.bbox == _region().bbox
    assert span.coordinate_space == "page-1@300dpi"
    assert provider.calls == [(_image(), _region(), "job-7f3a")]


def test_unreadable_region_yields_no_spans_but_still_a_stamped_output() -> None:
    provider = _StaticValidatedProvider(
        ProviderResponse(text=None, raw_confidence=0.15, cost=0.02, model_version="vlm-x/2.1")
    )

    output = ProviderBackedRegionalVlmFallback(provider).read_region(_image(), _region(), "job-7f3a")

    assert output.spans == ()
    assert output.method == "vlm_region"
    assert VLM_REGIONAL_COMPONENT_VERSION in output.component_version
