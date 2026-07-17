"""Every observation/unmapped-content note's `provenance.working.coordinate_space`
must resolve against one of the content artifact's recorded `coordinate_spaces`
(FIXTURES-SPEC.md content body) — citing a coordinate space that was never
recorded leaves a bbox with no page/size/DPI to interpret it against, which
makes "provenance to pixels" not mechanically true (E06 epic objective).

Silently passes when there is no content artifact under validation, matching
the other content-scoped checks in this package.
"""

from __future__ import annotations

from domain.artifacts.content import Observation, UnmappedContent
from domain.artifacts.errors import InvariantViolation
from services.validation.bundle import ArtifactBundle

CODE = "unknown-coordinate-space"


class CoordinateSpaceResolutionCheck:
    def check(self, bundle: ArtifactBundle) -> list[InvariantViolation]:
        if bundle.content is None:
            return []
        body = bundle.content.body
        known_ids = {space.id for space in body.coordinate_spaces}
        return [
            *self._check_observations(body.observations, known_ids),
            *self._check_unmapped_content(body.unmapped_content, known_ids),
        ]

    def _check_observations(self, observations: list[Observation], known_ids: set[str]) -> list[InvariantViolation]:
        violations = []
        for index, observation in enumerate(observations):
            if observation.provenance is None:
                continue
            space_id = observation.provenance.working.coordinate_space
            if space_id in known_ids:
                continue
            violations.append(
                InvariantViolation(
                    path=f"/body/observations/{index}/provenance/working/coordinate_space",
                    code=CODE,
                    message=(
                        f"coordinate space '{space_id}' for element_id "
                        f"'{observation.element_id}' is not recorded in coordinate_spaces"
                    ),
                )
            )
        return violations

    def _check_unmapped_content(self, notes: list[UnmappedContent], known_ids: set[str]) -> list[InvariantViolation]:
        violations = []
        for index, note in enumerate(notes):
            if note.provenance is None:
                continue
            space_id = note.provenance.working.coordinate_space
            if space_id in known_ids:
                continue
            violations.append(
                InvariantViolation(
                    path=f"/body/unmapped_content/{index}/provenance/working/coordinate_space",
                    code=CODE,
                    message=(
                        f"coordinate space '{space_id}' for note '{note.note_id}' is not recorded in coordinate_spaces"
                    ),
                )
            )
        return violations
