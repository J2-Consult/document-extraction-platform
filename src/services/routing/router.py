"""`CandidateRouter`: extract -> key -> candidates -> verify -> decision.

Pure orchestration over ports; constructor injection; no I/O beyond what the
injected ports perform. `inconclusive` is NEVER force-matched: the fast path
is taken if and only if verification `status == "accepted"` (principle 5,
CLAUDE.md) — every other outcome (rejected, inconclusive, or zero candidates)
routes to `full_analysis`, and that fallback is the loop's default, not a
special case.
"""

from __future__ import annotations

from collections.abc import Mapping

from adapters.fingerprint import fpv
from domain.artifacts.template import TemplateRef
from ports.canonical import CanonicalSerializer
from ports.clock import Clock
from ports.fingerprint import FingerprintFeatureExtractor
from ports.routing_store import RoutedTo, RoutingDecision, RoutingDecisionStore, TemplateCandidateIndex
from ports.verification import TemplateVerifier, VerificationResult


class CandidateRouter:
    def __init__(
        self,
        *,
        extractor: FingerprintFeatureExtractor,
        serializer: CanonicalSerializer,
        index: TemplateCandidateIndex,
        verifier: TemplateVerifier,
        store: RoutingDecisionStore,
        clock: Clock,
        component_versions: Mapping[str, str],
    ) -> None:
        self._extractor = extractor
        self._serializer = serializer
        self._index = index
        self._verifier = verifier
        self._store = store
        self._clock = clock
        self._component_versions = dict(component_versions)

    def route(self, pdf_bytes: bytes) -> RoutingDecision:
        started_at = self._clock.now()

        features = self._extractor.extract(pdf_bytes)
        key = fpv.fingerprint_key(features, self._serializer)
        candidates = self._index.find_by_key(key)

        candidate_ref: TemplateRef | None = None
        verification: VerificationResult | None = None
        routed_to: RoutedTo = "full_analysis"

        for candidate in candidates:
            verification = self._verifier.verify(features, pdf_bytes, candidate.body)
            candidate_ref = candidate.template_ref
            if verification.status == "accepted":
                routed_to = "fast_path"
                break

        latency_ms = (self._clock.now() - started_at) * 1000

        decision = RoutingDecision(
            fpv_version=features.fpv,
            fingerprint_key=key,
            candidate=candidate_ref,
            verification=verification,
            routed_to=routed_to,
            latency_ms=latency_ms,
            component_versions=dict(self._component_versions),
            decided_at=started_at,
        )
        self._store.append(decision)
        return decision
