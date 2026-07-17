"""Convenience factory wiring E04's default adapters into a `CandidateRouter`.

Not part of the architect's binding module layout — added for callers
(acceptance tests, the benchmark harness) that don't need custom port
implementations and would otherwise repeat this five-argument constructor
call verbatim. Flagged as a minor addition beyond the design doc's listed
modules.

Reuses `adapters.clock.SystemClock` (E03) rather than defining a second
`Clock` implementation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from adapters.clock import SystemClock
from adapters.fingerprint.born_digital import BornDigitalFingerprintExtractor
from adapters.fingerprint.verifier import NativePdfTemplateVerifier
from domain.artifacts.canonical import JsonCanonicalSerializer
from ports.routing_store import RoutingDecisionStore, TemplateCandidate
from services.routing.memory import InMemoryRoutingDecisionStore, InMemoryTemplateCandidateIndex
from services.routing.router import CandidateRouter

DEFAULT_COMPONENT_VERSIONS: Mapping[str, str] = {
    "fpv": "1",
    "extractor": "born-digital-v1",
    "verifier": "native-pdf-v1",
}


def build_default_router(
    candidates: Sequence[TemplateCandidate] = (),
    *,
    store: RoutingDecisionStore | None = None,
    component_versions: Mapping[str, str] | None = None,
) -> CandidateRouter:
    """Wire the default born-digital extractor + native-PDF verifier +
    in-memory index/clock into a `CandidateRouter`, pre-populated with
    `candidates`."""
    return CandidateRouter(
        extractor=BornDigitalFingerprintExtractor(),
        serializer=JsonCanonicalSerializer(),
        index=InMemoryTemplateCandidateIndex(candidates),
        verifier=NativePdfTemplateVerifier(),
        store=store if store is not None else InMemoryRoutingDecisionStore(),
        clock=SystemClock(),
        component_versions=component_versions if component_versions is not None else DEFAULT_COMPONENT_VERSIONS,
    )
