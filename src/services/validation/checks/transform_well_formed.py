"""`provenance.transform_to_source` must be exactly 6 finite floats — the
affine 6-tuple `domain.provenance.transform` utilities require. A NaN or
Infinity component would silently poison every downstream bbox mapping
instead of failing loudly at validation time.

Silently passes when there is no content artifact under validation.
"""

from __future__ import annotations

from domain.artifacts.content import Observation, UnmappedContent
from domain.artifacts.errors import InvariantViolation
from domain.provenance.transform import is_well_formed_transform
from services.validation.bundle import ArtifactBundle

CODE = "malformed-transform"


class TransformWellFormedCheck:
    def check(self, bundle: ArtifactBundle) -> list[InvariantViolation]:
        if bundle.content is None:
            return []
        body = bundle.content.body
        return [
            *self._check_observations(body.observations),
            *self._check_unmapped_content(body.unmapped_content),
        ]

    def _check_observations(self, observations: list[Observation]) -> list[InvariantViolation]:
        violations = []
        for index, observation in enumerate(observations):
            if observation.provenance is None:
                continue
            if is_well_formed_transform(observation.provenance.transform_to_source):
                continue
            violations.append(
                InvariantViolation(
                    path=f"/body/observations/{index}/provenance/transform_to_source",
                    code=CODE,
                    message=(f"transform_to_source for element_id '{observation.element_id}' is not 6 finite floats"),
                )
            )
        return violations

    def _check_unmapped_content(self, notes: list[UnmappedContent]) -> list[InvariantViolation]:
        violations = []
        for index, note in enumerate(notes):
            if note.provenance is None:
                continue
            if is_well_formed_transform(note.provenance.transform_to_source):
                continue
            violations.append(
                InvariantViolation(
                    path=f"/body/unmapped_content/{index}/provenance/transform_to_source",
                    code=CODE,
                    message=f"transform_to_source for note '{note.note_id}' is not 6 finite floats",
                )
            )
        return violations
