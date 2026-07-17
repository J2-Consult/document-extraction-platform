"""ConfidenceGate (epic E05): per-region scores and three-way routing.

Every region is assessed with BOTH its raw recognizer score and a calibrated
routing confidence (v0.2 §6.2); routing follows the CALIBRATED value:

    calibrated >= accept_threshold  -> accept
    calibrated <  review_threshold  -> review
    otherwise                       -> vlm_fallback (one region, one model call)

The calibrator is injected (identity by default) so a learned calibration
curve is a constructor argument, never an edit to the routing logic.

Pure service: no I/O, no framework imports.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from domain.extraction import Region

Route = Literal["accept", "vlm_fallback", "review"]

# raw score -> calibrated routing confidence, both in [0, 1].
Calibrator = Callable[[float], float]


def _identity_calibration(raw_score: float) -> float:
    return raw_score


@dataclass(frozen=True)
class RegionScore:
    """One region's raw recognizer score, as handed to the gate."""

    region: Region
    raw_score: float


@dataclass(frozen=True)
class RegionAssessment:
    """The gate's verdict for one region: both scores, one route."""

    region: Region
    raw_score: float
    calibrated_confidence: float
    route: Route


@dataclass(frozen=True)
class GateDecision:
    assessments: tuple[RegionAssessment, ...]

    def routed(self, route: Route) -> tuple[RegionAssessment, ...]:
        return tuple(assessment for assessment in self.assessments if assessment.route == route)


class ConfidenceGate:
    def __init__(
        self,
        accept_threshold: float,
        review_threshold: float,
        calibrator: Calibrator | None = None,
    ) -> None:
        if not 0.0 <= review_threshold < accept_threshold <= 1.0:
            raise ValueError(
                "thresholds must satisfy 0 <= review_threshold < accept_threshold <= 1, "
                f"got review_threshold={review_threshold}, accept_threshold={accept_threshold}"
            )
        self._accept_threshold = accept_threshold
        self._review_threshold = review_threshold
        self._calibrator = calibrator if calibrator is not None else _identity_calibration

    def evaluate(self, scores: Sequence[RegionScore]) -> GateDecision:
        return GateDecision(assessments=tuple(self._assess(score) for score in scores))

    def _assess(self, score: RegionScore) -> RegionAssessment:
        calibrated = self._calibrator(score.raw_score)
        if not 0.0 <= calibrated <= 1.0:
            raise ValueError(f"calibrator returned {calibrated}, outside [0, 1] — calibrated confidence is invalid")
        return RegionAssessment(
            region=score.region,
            raw_score=score.raw_score,
            calibrated_confidence=calibrated,
            route=self._route(calibrated),
        )

    def _route(self, calibrated: float) -> Route:
        if calibrated >= self._accept_threshold:
            return "accept"
        if calibrated < self._review_threshold:
            return "review"
        return "vlm_fallback"
