"""MappingOutcome/MappingResult shapes (E09 design doc, binding).

Pure-data tests only: these types carry no behavior of their own, but their
shape (fields, literals, JSON determinism) is the contract every mapping
step and the acceptance criterion depend on.
"""

from __future__ import annotations

import json

from domain.artifacts.provenance import Provenance, SourceRef, WorkingRef
from services.mapping.outcome import MappingResult, ReviewItem


def _provenance() -> Provenance:
    return Provenance(
        source=SourceRef(artifact_sha256="0" * 64, page=1),
        working=WorkingRef(artifact_sha256="0" * 64, coordinate_space="page-1"),
        bbox=[0, 0, 10, 10],
        method="pdf_text",
        component_version="fixture-1.0.0",
        transform_to_source=[1, 0, 0, 1, 0, 0],
    )


def test_pending_review_result_carries_null_record_and_itemized_review_items() -> None:
    item = ReviewItem(
        element="el_total_amount",
        reason="low_confidence",
        confidence=0.61,
        provenance=_provenance(),
    )

    result = MappingResult(
        outcome="pending_review",
        record=None,
        review_items=(item,),
        contract_validation="not_evaluated",
        error_category="extraction_uncertainty",
        component_versions={"mapping_pipeline": "1.0.0"},
    )

    assert result.outcome == "pending_review"
    assert result.record is None
    assert result.review_items == (item,)
    assert result.contract_validation == "not_evaluated"
    assert result.error_category == "extraction_uncertainty"


def test_completed_result_defaults_review_items_empty_and_error_category_none() -> None:
    result = MappingResult(
        outcome="completed",
        record={"invoice_number": "2026-0043"},
        contract_validation="passed",
        component_versions={"mapping_pipeline": "1.0.0"},
    )

    assert result.review_items == ()
    assert result.error_category is None


def test_mapping_result_serializes_to_byte_identical_json_for_equal_construction() -> None:
    kwargs = {
        "outcome": "completed",
        "record": {"a": 1, "b": [1, 2, 3]},
        "contract_validation": "passed",
        "component_versions": {"mapping_pipeline": "1.0.0"},
    }

    first = MappingResult(**kwargs)  # type: ignore[arg-type]
    second = MappingResult(**kwargs)  # type: ignore[arg-type]

    first_json = first.model_dump_json()
    second_json = second.model_dump_json()
    assert first_json == second_json
    # And it is genuinely JSON, not just an equal Python string.
    assert json.loads(first_json) == json.loads(second_json)
