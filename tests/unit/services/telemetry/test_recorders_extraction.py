"""record_gate_decision + record_extraction_cost (epic E12): consume E05's
real ConfidenceGate output (src/services/extraction/confidence.py) and E05's
CostLedger categories (src/ports/cost.py) — the epic's "confidence
distributions" and "processing ... cost" instrumentation points."""

from __future__ import annotations

from domain.extraction import Region
from ports.cost import COST_CATEGORIES
from services.extraction.confidence import ConfidenceGate, RegionScore
from services.telemetry.fake import InMemoryMetricsSink
from services.telemetry.metrics import EXTRACTION_CONFIDENCE, EXTRACTION_COST_UNITS
from services.telemetry.recorders import record_extraction_cost, record_gate_decision


def _region(score: float) -> RegionScore:
    return RegionScore(
        region=Region(page=1, bbox=[0.0, 0.0, 10.0, 10.0], coordinate_space="page-1", kind="text", score=score),
        raw_score=score,
    )


def test_gate_decision_emits_one_confidence_observation_per_region_with_its_route() -> None:
    gate = ConfidenceGate(accept_threshold=0.8, review_threshold=0.4)
    decision = gate.evaluate([_region(0.95), _region(0.5), _region(0.1)])
    sink = InMemoryMetricsSink()

    record_gate_decision(sink, decision, tenant_id="t-nordvik", doc_class="invoice", component_version="gate-v1")

    observations = [h for h in sink.histograms if h.name == EXTRACTION_CONFIDENCE]
    assert len(observations) == 3
    by_route = {o.dimensions["route"]: o.value for o in observations}
    assert by_route == {"accept": 0.95, "vlm_fallback": 0.5, "review": 0.1}
    for observation in observations:
        assert observation.dimensions["tenant"] == "t-nordvik"
        assert observation.dimensions["doc_class"] == "invoice"
        assert observation.dimensions["component_version"] == "gate-v1"


def test_extraction_cost_emits_histogram_dimensioned_by_cost_category() -> None:
    sink = InMemoryMetricsSink()
    for category in COST_CATEGORIES:
        record_extraction_cost(
            sink,
            tenant_id="t-nordvik",
            doc_class="invoice",
            component_version="cascade-v1",
            category=category,
            cost=1.5,
        )

    costs = [h for h in sink.histograms if h.name == EXTRACTION_COST_UNITS]
    assert len(costs) == len(COST_CATEGORIES)
    assert {c.dimensions["category"] for c in costs} == set(COST_CATEGORIES)
    assert all(c.value == 1.5 for c in costs)
