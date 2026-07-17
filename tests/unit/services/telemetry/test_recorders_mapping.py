"""record_mapping_result (epic E12): consumes E09's real `MappingResult`
(src/services/mapping/outcome.py, the epic's named instrumentation point for
outcomes + error categories) and emits target-schema failure categories +
per-review-item correction counts by extraction method."""

from __future__ import annotations

from typing import Any

from services.mapping.outcome import MappingResult, ReviewItem
from services.telemetry.fake import InMemoryMetricsSink
from services.telemetry.metrics import MAPPING_OUTCOMES_TOTAL, MAPPING_REVIEW_ITEMS_TOTAL
from services.telemetry.recorders import record_mapping_result


def _review_item(provenance: Any, *, reason: str) -> ReviewItem:
    return ReviewItem(element="el_total_amount", reason=reason, confidence=0.61, provenance=provenance)


def test_completed_result_emits_one_outcome_counter_with_none_error_category(load_fixture_artifact: Any) -> None:
    content = load_fixture_artifact("content_nv20260042.v1")
    provenance = content["body"]["observations"][0]["provenance"]

    result = MappingResult(
        outcome="completed",
        record={"total_amount": 13750.0},
        review_items=(),
        contract_validation="passed",
        error_category=None,
        component_versions={"mapping_pipeline": "1"},
    )
    sink = InMemoryMetricsSink()

    record_mapping_result(sink, result, tenant_id="t-nordvik", doc_class="invoice")

    outcomes = [c for c in sink.counters if c.name == MAPPING_OUTCOMES_TOTAL]
    assert len(outcomes) == 1
    assert outcomes[0].dimensions["outcome"] == "completed"
    assert outcomes[0].dimensions["error_category"] == "none"
    assert outcomes[0].dimensions["tenant"] == "t-nordvik"
    assert outcomes[0].dimensions["doc_class"] == "invoice"
    assert [c for c in sink.counters if c.name == MAPPING_REVIEW_ITEMS_TOTAL] == []
    assert provenance  # sanity: the fixture provenance we loaded is non-empty (used in the next test)


def test_pending_review_result_emits_target_schema_failure_category_and_review_items_by_method(
    load_fixture_artifact: Any,
) -> None:
    content = load_fixture_artifact("content_nv20260042.v1")
    provenance = content["body"]["observations"][0]["provenance"]

    result = MappingResult(
        outcome="pending_review",
        record=None,
        review_items=(_review_item(provenance, reason="below_confidence_threshold"),),
        contract_validation="not_evaluated",
        error_category="extraction_uncertainty",
        component_versions={"mapping_pipeline": "1"},
    )
    sink = InMemoryMetricsSink()

    record_mapping_result(sink, result, tenant_id="t-nordvik", doc_class="invoice")

    outcomes = [c for c in sink.counters if c.name == MAPPING_OUTCOMES_TOTAL]
    assert outcomes[0].dimensions["error_category"] == "extraction_uncertainty"

    review_items = [c for c in sink.counters if c.name == MAPPING_REVIEW_ITEMS_TOTAL]
    assert len(review_items) == 1
    assert review_items[0].dimensions["reason"] == "below_confidence_threshold"
    assert review_items[0].dimensions["method"] == provenance["method"]
    assert review_items[0].dimensions["tenant"] == "t-nordvik"


def test_rejected_result_emits_contract_failure_category(load_fixture_artifact: Any) -> None:
    result = MappingResult(
        outcome="rejected",
        record=None,
        review_items=(),
        contract_validation="failed",
        error_category="contract",
        component_versions={"mapping_pipeline": "1"},
    )
    sink = InMemoryMetricsSink()

    record_mapping_result(sink, result, tenant_id="t-nordvik", doc_class="invoice")

    outcomes = [c for c in sink.counters if c.name == MAPPING_OUTCOMES_TOTAL]
    assert outcomes[0].dimensions["outcome"] == "rejected"
    assert outcomes[0].dimensions["error_category"] == "contract"
