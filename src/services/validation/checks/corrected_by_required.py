"""`provenance.method == "human" => provenance.corrected_by is not None`.

E09's narrow addition (CLAUDE.md PROVENANCE MODEL NOTE): a human correction
without an identified corrector is exactly the "correction without
provenance" pattern CLAUDE.md forbids. `Provenance.corrected_by` is typed as
optional (see provenance.py's docstring) so this cross-field rule — like
state_legality.py's — belongs to the InvariantValidator, not a Pydantic
model_validator.
"""

from __future__ import annotations

from domain.artifacts.content import Observation
from domain.artifacts.errors import InvariantViolation
from services.validation.bundle import ArtifactBundle

CODE = "corrected-by-required-for-human-method"


class CorrectedByRequiredCheck:
    def check(self, bundle: ArtifactBundle) -> list[InvariantViolation]:
        if bundle.content is None:
            return []
        return self._check_observations(bundle.content.body.observations)

    def _check_observations(self, observations: list[Observation]) -> list[InvariantViolation]:
        return [
            InvariantViolation(
                path=f"/body/observations/{index}/provenance/corrected_by",
                code=CODE,
                message=(
                    f"observation for element_id '{observation.element_id}' has "
                    "provenance.method 'human' but no corrected_by identity"
                ),
            )
            for index, observation in enumerate(observations)
            if observation.provenance is not None
            and observation.provenance.method == "human"
            and observation.provenance.corrected_by is None
        ]
