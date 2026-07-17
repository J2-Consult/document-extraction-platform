"""Unit tests for the in-memory routing-port implementations."""

from __future__ import annotations

from domain.artifacts.template import PageGeometry, TemplateBody, TemplateElement, TemplateRef
from ports.routing_store import RoutingDecision, TemplateCandidate
from services.routing.memory import (
    InMemoryRoutingDecisionStore,
    InMemoryTemplateCandidateIndex,
    candidate_from_template_body,
)


def _body(template_id: str = "tmpl_test", fingerprint: str = "fpv1:sha256:" + "b" * 64) -> TemplateBody:
    return TemplateBody(
        template_id=template_id,
        version=1,
        doc_class="invoice",
        fingerprint=fingerprint,
        page_count=1,
        pages=[PageGeometry(page=1, width=595, height=842, unit="pt", rotation=0)],
        elements=[TemplateElement(element_id="el_a", kind="value_region", page=1, bbox=[0, 0, 10, 10])],
    )


def test_find_by_key_returns_empty_sequence_when_no_candidate_registered() -> None:
    index = InMemoryTemplateCandidateIndex()
    assert index.find_by_key("fpv1:sha256:" + "0" * 64) == ()


def test_find_by_key_returns_registered_candidates_for_matching_key() -> None:
    body = _body()
    candidate = TemplateCandidate(
        template_ref=TemplateRef(template_id="tmpl_test", version=1), fingerprint_key=body.fingerprint, body=body
    )
    index = InMemoryTemplateCandidateIndex([candidate])

    assert index.find_by_key(body.fingerprint) == (candidate,)
    assert index.find_by_key("some-other-key") == ()


def test_candidate_from_template_body_builds_a_matching_ref_and_key() -> None:
    body = _body(template_id="tmpl_x")

    candidate = candidate_from_template_body(body)

    assert candidate.template_ref == TemplateRef(template_id="tmpl_x", version=1)
    assert candidate.fingerprint_key == body.fingerprint
    assert candidate.body == body


def test_decision_store_append_is_ordered_and_read_only_via_the_decisions_property() -> None:
    store = InMemoryRoutingDecisionStore()
    decision = RoutingDecision(
        fpv_version=1,
        fingerprint_key="fpv1:sha256:" + "c" * 64,
        candidate=None,
        verification=None,
        routed_to="full_analysis",
        latency_ms=1.0,
        component_versions={},
        decided_at=0.0,
    )

    store.append(decision)

    assert store.decisions == (decision,)
