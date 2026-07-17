"""`SpecializedDetector` adapters: deterministic detector stand-ins.

STUBBED: no real table/kv/mark/signature modeling — `EchoSpecializedDetector`
re-emits the region it was given (real specialized models are provider-side).

REAL and load-bearing: the single-region interface, the kind guard (a
detector registered for tables must never be handed a kv region — that would
be a cascade dispatch bug, so it fails loudly), and provenance stamping.
"""

from __future__ import annotations

from domain.extraction import PageImage, PassOutput, Region, RegionKind

DETECTOR_STUB_COMPONENT_VERSION = "specialized-detector-stub/1.0.0"


class EchoSpecializedDetector:
    def __init__(self, *, kind: RegionKind) -> None:
        self._kind = kind

    def detect(self, image: PageImage, region: Region) -> PassOutput:
        if region.kind != self._kind:
            raise ValueError(f"detector for kind {self._kind!r} was dispatched a {region.kind!r} region")
        return PassOutput(
            method="detector",
            component_version=DETECTOR_STUB_COMPONENT_VERSION,
            transform_to_source=list(image.transform_to_source),
            regions=(region,),
        )
