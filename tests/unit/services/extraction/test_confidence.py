"""ConfidenceGate: per-region raw + calibrated scores, three-way routing
(accept / vlm_fallback / review), calibrated confidence drives the routing.
"""

from __future__ import annotations

import pytest

from domain.extraction import Region
from services.extraction.confidence import ConfidenceGate, RegionScore


def _region(score: float, kind: str = "text") -> Region:
    return Region(page=1, bbox=[206.0, 636.0, 346.0, 648.0], coordinate_space="page-1", kind=kind, score=score)  # type: ignore[arg-type]


def _gate(**overrides: object) -> ConfidenceGate:
    defaults: dict[str, object] = {"accept_threshold": 0.9, "review_threshold": 0.35}
    defaults.update(overrides)
    return ConfidenceGate(**defaults)  # type: ignore[arg-type]


def test_regions_route_three_ways_by_calibrated_confidence() -> None:
    gate = _gate()
    scores = [
        RegionScore(region=_region(0.95), raw_score=0.95),
        RegionScore(region=_region(0.55), raw_score=0.55),
        RegionScore(region=_region(0.10), raw_score=0.10),
    ]

    decision = gate.evaluate(scores)

    assert [assessment.route for assessment in decision.assessments] == ["accept", "vlm_fallback", "review"]


def test_every_assessment_records_both_raw_and_calibrated_scores() -> None:
    gate = _gate(calibrator=lambda raw: raw * 0.8)

    decision = gate.evaluate([RegionScore(region=_region(0.95), raw_score=0.95)])

    assessment = decision.assessments[0]
    assert assessment.raw_score == 0.95
    assert assessment.calibrated_confidence == pytest.approx(0.76)
    assert assessment.route == "vlm_fallback", "routing must follow the CALIBRATED score, not the raw one"


def test_gate_decision_exposes_routed_subsets() -> None:
    gate = _gate()
    scores = [
        RegionScore(region=_region(0.95), raw_score=0.95),
        RegionScore(region=_region(0.55), raw_score=0.55),
        RegionScore(region=_region(0.10), raw_score=0.10),
    ]

    decision = gate.evaluate(scores)

    assert len(decision.routed("accept")) == 1
    assert len(decision.routed("vlm_fallback")) == 1
    assert len(decision.routed("review")) == 1


def test_thresholds_must_be_ordered_within_the_unit_interval() -> None:
    with pytest.raises(ValueError, match="threshold"):
        ConfidenceGate(accept_threshold=0.3, review_threshold=0.9)
    with pytest.raises(ValueError, match="threshold"):
        ConfidenceGate(accept_threshold=1.5, review_threshold=0.2)


def test_calibrator_output_outside_unit_interval_is_rejected() -> None:
    gate = _gate(calibrator=lambda raw: raw * 2.0)

    with pytest.raises(ValueError, match="calibrat"):
        gate.evaluate([RegionScore(region=_region(0.9), raw_score=0.9)])


def test_empty_score_list_yields_empty_decision() -> None:
    assert _gate().evaluate([]).assessments == ()
