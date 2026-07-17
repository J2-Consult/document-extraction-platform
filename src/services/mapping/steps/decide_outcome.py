"""Step 5 — DecideOutcome: the strict outcome state machine (v0.2 §6.3).

Priority order, tested exactly:

1. A REQUIRED element below the confidence threshold (or unreadable)
   => `pending_review`, `record: null` (NO partial records, ever), itemized
   review items, `contract_validation: "not_evaluated"`,
   category `extraction_uncertainty`.
2. Any contract issue (enum miss, datatype mismatch, schema violation)
   => `rejected`, `record: null`, contract `failed`, category `contract`.
3. Otherwise `completed`: optional low-confidence values are EXCLUDED from
   the record only because the target schema permits their absence — each
   exclusion is still reported as a review item.

The threshold is an explicit constructor parameter; the default lives in
services/mapping/constants.py. No clock, no randomness: same inputs, same
result bytes.
"""

from __future__ import annotations

from collections.abc import Mapping

from services.mapping.outcome import MappingResult, ReviewItem
from services.mapping.steps.shapes import BoundRecord, CoercionResult, MaskApplication

BELOW_THRESHOLD_REASON = "below_confidence_threshold"
UNREADABLE_REASON = "unreadable"


class DecideOutcome:
    def __init__(self, confidence_threshold: float, component_versions: Mapping[str, str]) -> None:
        if not 0.0 <= confidence_threshold <= 1.0:
            raise ValueError(f"confidence threshold must be within [0, 1], got {confidence_threshold}")
        self._threshold = confidence_threshold
        self._component_versions = dict(component_versions)

    def decide(self, application: MaskApplication, coercion: CoercionResult, bound: BoundRecord) -> MappingResult:
        uncertain = self._uncertain_items(application)
        if any(field in bound.required_fields for field, _ in uncertain):
            return self._pending_review(uncertain)
        if application.issues or coercion.issues or bound.issues:
            return self._rejected()
        return self._completed(bound, uncertain)

    def _uncertain_items(self, application: MaskApplication) -> list[tuple[str, ReviewItem]]:
        """(target field, review item) for every element a human must confirm."""
        items = [
            (
                decoded.entry.target.field,
                ReviewItem(
                    element=decoded.entry.element_id,
                    reason=BELOW_THRESHOLD_REASON,
                    confidence=decoded.observation.confidence.calibrated,
                    provenance=decoded.observation.provenance,
                ),
            )
            for decoded in application.decoded
            if decoded.observation.confidence.calibrated < self._threshold
        ]
        items.extend(
            (
                resolved.entry.target.field,
                ReviewItem(
                    element=resolved.entry.element_id,
                    reason=UNREADABLE_REASON,
                    confidence=resolved.observation.confidence.calibrated,
                    provenance=resolved.observation.provenance,
                ),
            )
            for resolved in application.unreadable
            if resolved.observation is not None
        )
        return items

    def _pending_review(self, uncertain: list[tuple[str, ReviewItem]]) -> MappingResult:
        return MappingResult(
            outcome="pending_review",
            record=None,
            review_items=tuple(item for _, item in uncertain),
            contract_validation="not_evaluated",
            error_category="extraction_uncertainty",
            component_versions=self._component_versions,
        )

    def _rejected(self) -> MappingResult:
        return MappingResult(
            outcome="rejected",
            record=None,
            review_items=(),
            contract_validation="failed",
            error_category="contract",
            component_versions=self._component_versions,
        )

    def _completed(self, bound: BoundRecord, uncertain: list[tuple[str, ReviewItem]]) -> MappingResult:
        excluded_fields = {field for field, _ in uncertain}  # all optional here, by priority 1
        record = {field: value for field, value in bound.record.items() if field not in excluded_fields}
        return MappingResult(
            outcome="completed",
            record=record,
            review_items=tuple(item for _, item in uncertain),
            contract_validation="passed",
            error_category=None,
            component_versions=self._component_versions,
        )
