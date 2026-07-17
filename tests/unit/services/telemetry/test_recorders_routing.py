"""record_routing_decision (epic E12): consumes E04's real `RoutingDecision`
(src/services/routing/, per the epic's instrumentation-points list — decision
records already carry candidate-hit, verification result, and latency) and
emits latency/decision/candidate-hit/verification-result metrics. Exercised
against REAL router decisions over the fixture corpus, not synthetic shapes."""

from __future__ import annotations

from typing import Any

from domain.artifacts.template import TemplateArtifact
from services.routing.factory import build_default_router
from services.routing.memory import candidate_from_template_body
from services.telemetry.fake import InMemoryMetricsSink
from services.telemetry.metrics import (
    ROUTING_CANDIDATE_HITS_TOTAL,
    ROUTING_DECISIONS_TOTAL,
    ROUTING_LATENCY_MS,
    ROUTING_VERIFICATION_RESULTS_TOTAL,
)
from services.telemetry.recorders import record_routing_decision


def test_fast_path_decision_emits_latency_decision_and_candidate_hit_and_accepted_verification(
    load_fixture_artifact: Any, fixture_pdf_path: Any
) -> None:
    artifact = TemplateArtifact.model_validate(load_fixture_artifact("tmpl_nvinv.v1"))
    candidate = candidate_from_template_body(artifact.body)
    router = build_default_router([candidate])
    pdf_bytes = fixture_pdf_path("nv_invoice_20260043").read_bytes()
    decision = router.route(pdf_bytes)
    assert decision.routed_to == "fast_path"  # sanity: this is the real fast-path fixture flow

    sink = InMemoryMetricsSink()
    record_routing_decision(sink, decision, tenant_id="t-nordvik", doc_class="invoice")

    latency = [h for h in sink.histograms if h.name == ROUTING_LATENCY_MS]
    assert len(latency) == 1
    assert latency[0].value == decision.latency_ms
    assert latency[0].dimensions["tenant"] == "t-nordvik"
    assert latency[0].dimensions["path"] == "fast_path"
    assert latency[0].dimensions["doc_class"] == "invoice"
    assert latency[0].dimensions["component_version"]

    decisions = [c for c in sink.counters if c.name == ROUTING_DECISIONS_TOTAL]
    assert len(decisions) == 1
    assert decisions[0].dimensions["path"] == "fast_path"

    candidate_hits = [c for c in sink.counters if c.name == ROUTING_CANDIDATE_HITS_TOTAL]
    assert len(candidate_hits) == 1
    assert candidate_hits[0].dimensions["tenant"] == "t-nordvik"

    verification_results = [c for c in sink.counters if c.name == ROUTING_VERIFICATION_RESULTS_TOTAL]
    assert len(verification_results) == 1
    assert verification_results[0].dimensions["result"] == "accepted"


def test_decoy_decision_emits_rejected_verification_and_no_fast_path_candidate_hit_undercounted(
    load_fixture_artifact: Any,
) -> None:
    from benchmarks.routing.decoys import generate_decoy_corpus

    artifact = TemplateArtifact.model_validate(load_fixture_artifact("tmpl_nvinv.v1"))
    candidate = candidate_from_template_body(artifact.body)
    router = build_default_router([candidate])
    decoy_pdf_bytes = generate_decoy_corpus(rotations=(1,))["decoy_nv20260042_rot1"]
    decision = router.route(decoy_pdf_bytes)
    assert decision.routed_to == "full_analysis"  # sanity

    sink = InMemoryMetricsSink()
    record_routing_decision(sink, decision, tenant_id="t-nordvik", doc_class="invoice")

    decisions = [c for c in sink.counters if c.name == ROUTING_DECISIONS_TOTAL]
    assert decisions[0].dimensions["path"] == "full_analysis"

    # The decoy DOES get a candidate hit (cheap extractor) even though it's
    # rejected by verification — candidate-hit and slow-path are counted
    # independently so their rates can diverge (this is exactly criterion 2's
    # scenario: hit + reject).
    candidate_hits = [c for c in sink.counters if c.name == ROUTING_CANDIDATE_HITS_TOTAL]
    assert len(candidate_hits) == 1

    verification_results = [c for c in sink.counters if c.name == ROUTING_VERIFICATION_RESULTS_TOTAL]
    assert verification_results[0].dimensions["result"] == "rejected"


def test_zero_candidate_hit_decision_emits_no_candidate_hit_or_verification_counter(
    load_fixture_artifact: Any, fixture_pdf_path: Any
) -> None:
    router = build_default_router([])  # empty index: zero candidates for any document
    pdf_bytes = fixture_pdf_path("mbr_report_001").read_bytes()
    decision = router.route(pdf_bytes)
    assert decision.candidate is None
    assert decision.verification is None

    sink = InMemoryMetricsSink()
    record_routing_decision(sink, decision, tenant_id="t-nordvik", doc_class="maintenance_report")

    assert [c for c in sink.counters if c.name == ROUTING_CANDIDATE_HITS_TOTAL] == []
    assert [c for c in sink.counters if c.name == ROUTING_VERIFICATION_RESULTS_TOTAL] == []
    assert len([c for c in sink.counters if c.name == ROUTING_DECISIONS_TOTAL]) == 1
