"""Unit tests for `CandidateRouter` against fakes only — no PDF parsing, no
real Postgres. Covers the routing contract: fast path only on
`status == "accepted"`; `inconclusive` and `rejected` (and zero candidates)
all fall through to `full_analysis`; the decision record is always appended
exactly once and carries every required field.
"""

from __future__ import annotations

from adapters.fingerprint import fpv
from domain.artifacts.template import (
    Anchor,
    PageGeometry,
    TemplateBody,
    TemplateElement,
    TemplateRef,
)
from ports.fingerprint import FingerprintFeatures, FingerprintPage
from ports.routing_store import TemplateCandidate
from ports.verification import VerificationCheck, VerificationResult, VerificationStatus
from services.routing.memory import InMemoryRoutingDecisionStore, InMemoryTemplateCandidateIndex
from services.routing.router import CandidateRouter

_FEATURES = FingerprintFeatures(fpv=1, page_count=1, pages=(FingerprintPage(w_bucket=596, h_bucket=840),))


class _FakeSerializer:
    def canonical_bytes(self, obj: object) -> bytes:
        return repr(obj).encode()


# The router computes the fingerprint key from `_FEATURES` itself (extract ->
# key), so a candidate must be registered under that SAME computed key, not
# an arbitrary placeholder, or `find_by_key` legitimately returns nothing.
_EXPECTED_KEY = fpv.fingerprint_key(_FEATURES, _FakeSerializer())


class _FakeExtractor:
    def __init__(self, features: FingerprintFeatures = _FEATURES) -> None:
        self._features = features
        self.calls: list[bytes] = []

    def extract(self, pdf_bytes: bytes) -> FingerprintFeatures:
        self.calls.append(pdf_bytes)
        return self._features


class _FakeVerifier:
    def __init__(self, status: VerificationStatus) -> None:
        self._status = status
        self.calls = 0

    def verify(self, features: object, pdf_bytes: object, candidate: object) -> VerificationResult:
        self.calls += 1
        return VerificationResult(
            status=self._status,
            checks=(VerificationCheck(check_id="fake", passed=_status_to_passed(self._status), detail="fake check"),),
        )


def _status_to_passed(status: VerificationStatus) -> bool | None:
    return {"accepted": True, "rejected": False, "inconclusive": None}[status]


class _FakeClock:
    def __init__(self, values: list[float]) -> None:
        self._values = list(values)

    def now(self) -> float:
        return self._values.pop(0)


def _template_body() -> TemplateBody:
    return TemplateBody(
        template_id="tmpl_test",
        version=1,
        doc_class="invoice",
        fingerprint=_EXPECTED_KEY,
        page_count=1,
        pages=[PageGeometry(page=1, width=595, height=842, unit="pt", rotation=0)],
        elements=[
            TemplateElement(
                element_id="el_a",
                kind="value_region",
                page=1,
                bbox=[206, 780, 346, 792],
                anchor=Anchor(label_text="A:", label_bbox=[56, 780, 196, 792]),
            )
        ],
    )


def _candidate(key: str = _EXPECTED_KEY) -> TemplateCandidate:
    return TemplateCandidate(
        template_ref=TemplateRef(template_id="tmpl_test", version=1), fingerprint_key=key, body=_template_body()
    )


def _router(
    *, candidates: list[TemplateCandidate], verifier_status: VerificationStatus, clock_values: list[float]
) -> tuple[CandidateRouter, InMemoryRoutingDecisionStore, _FakeExtractor, _FakeVerifier]:
    index = InMemoryTemplateCandidateIndex(candidates)
    store = InMemoryRoutingDecisionStore()
    extractor = _FakeExtractor()
    verifier = _FakeVerifier(verifier_status)
    router = CandidateRouter(
        extractor=extractor,
        serializer=_FakeSerializer(),
        index=index,
        verifier=verifier,
        store=store,
        clock=_FakeClock(clock_values),
        component_versions={"fpv": "1", "verifier": "fake"},
    )
    return router, store, extractor, verifier


def test_zero_candidates_routes_to_full_analysis_with_no_verification() -> None:
    router, store, _, verifier = _router(candidates=[], verifier_status="accepted", clock_values=[0.0, 0.1])

    decision = router.route(b"pdf-bytes")

    assert decision.routed_to == "full_analysis"
    assert decision.candidate is None
    assert decision.verification is None
    assert verifier.calls == 0
    assert store.decisions == (decision,)


def test_accepted_verification_routes_to_fast_path() -> None:
    candidate = _candidate()
    router, store, _, verifier = _router(candidates=[candidate], verifier_status="accepted", clock_values=[0.0, 0.05])

    decision = router.route(b"pdf-bytes")

    assert decision.routed_to == "fast_path"
    assert decision.candidate == candidate.template_ref
    assert decision.verification is not None
    assert decision.verification.status == "accepted"
    assert verifier.calls == 1
    assert store.decisions == (decision,)


def test_rejected_verification_routes_to_full_analysis_never_fast_path() -> None:
    candidate = _candidate()
    router, store, _, _ = _router(candidates=[candidate], verifier_status="rejected", clock_values=[0.0, 0.02])

    decision = router.route(b"pdf-bytes")

    assert decision.routed_to == "full_analysis"
    assert decision.candidate == candidate.template_ref
    assert decision.verification is not None
    assert decision.verification.status == "rejected"


def test_inconclusive_verification_is_never_force_matched_to_fast_path() -> None:
    candidate = _candidate()
    router, store, _, _ = _router(candidates=[candidate], verifier_status="inconclusive", clock_values=[0.0, 0.02])

    decision = router.route(b"pdf-bytes")

    assert decision.routed_to == "full_analysis"
    assert decision.verification is not None
    assert decision.verification.status == "inconclusive"


def test_decision_record_carries_fpv_version_key_latency_and_component_versions() -> None:
    candidate = _candidate()
    router, _, _, _ = _router(candidates=[candidate], verifier_status="accepted", clock_values=[10.0, 10.25])

    decision = router.route(b"pdf-bytes")

    assert decision.fpv_version == 1
    assert decision.fingerprint_key
    assert decision.latency_ms == 250.0
    assert decision.component_versions == {"fpv": "1", "verifier": "fake"}
    assert decision.decided_at == 10.0


def test_extractor_is_called_exactly_once_per_route_call() -> None:
    candidate = _candidate()
    router, _, extractor, _ = _router(candidates=[candidate], verifier_status="accepted", clock_values=[0.0, 0.01])

    router.route(b"pdf-bytes")

    assert extractor.calls == [b"pdf-bytes"]
