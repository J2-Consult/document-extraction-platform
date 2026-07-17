"""`RegionalVlmFallback` adapter: REAL wiring from a validated provider
response to a provenance-stamped `PassOutput`.

The model itself lives behind a `ValidatedModelProvider` (in production:
`GuardedProvider` wrapping a real transport); this adapter's job is the part
that must be correct locally — one region in, one stamped output out, with a
component version naming BOTH this wiring and the model that answered.
A null `text` (model could not read the region) yields no spans but still a
stamped output, so the caller can tell "asked and unreadable" from "never
asked".
"""

from __future__ import annotations

from domain.extraction import PageImage, PassOutput, Region, TextSpan
from ports.providers import ProviderResponse, ValidatedModelProvider

VLM_REGIONAL_COMPONENT_VERSION = "vlm-regional/1.0.0"


class ProviderBackedRegionalVlmFallback:
    def __init__(self, provider: ValidatedModelProvider) -> None:
        self._provider = provider

    def read_region(self, image: PageImage, region: Region, job_ref: str) -> PassOutput:
        response = self._provider.read_region(image, region, job_ref)
        return PassOutput(
            method="vlm_region",
            component_version=f"{VLM_REGIONAL_COMPONENT_VERSION}+{response.model_version}",
            transform_to_source=list(image.transform_to_source),
            spans=self._spans(response, image, region),
        )

    @staticmethod
    def _spans(response: ProviderResponse, image: PageImage, region: Region) -> tuple[TextSpan, ...]:
        if response.text is None:
            return ()
        return (
            TextSpan(
                text=response.text,
                page=image.page,
                bbox=list(region.bbox),
                coordinate_space=image.coordinate_space,
                confidence=response.raw_confidence,
            ),
        )
