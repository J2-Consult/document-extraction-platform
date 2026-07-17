"""Every observation and unmapped-content note must carry provenance.

`Observation.provenance`/`UnmappedContent.provenance` are typed as required,
non-optional fields, so JSON Schema (and Pydantic parsing) already reject a
`content.json` that omits the key entirely. This check exists as the
InvariantValidator's own defense-in-depth for artifacts assembled in-process
outside the JSON boundary (e.g. by a later epic's pipeline) where a
`None` could otherwise slip through unvalidated — CLAUDE.md forbids "a value,
chunk, or correction without provenance" as a runtime invariant, not just a
parse-time one.
"""

from __future__ import annotations

from domain.artifacts.content import Observation, UnmappedContent
from domain.artifacts.errors import InvariantViolation
from services.validation.bundle import ArtifactBundle

CODE = "missing-provenance"


class ProvenanceRequiredCheck:
    def check(self, bundle: ArtifactBundle) -> list[InvariantViolation]:
        if bundle.content is None:
            return []
        body = bundle.content.body
        return [
            *self._check_observations(body.observations),
            *self._check_unmapped_content(body.unmapped_content),
        ]

    def _check_observations(self, observations: list[Observation]) -> list[InvariantViolation]:
        return [
            InvariantViolation(
                path=f"/body/observations/{index}/provenance",
                code=CODE,
                message=f"observation for element_id '{observation.element_id}' has no provenance",
            )
            for index, observation in enumerate(observations)
            if observation.provenance is None
        ]

    def _check_unmapped_content(self, notes: list[UnmappedContent]) -> list[InvariantViolation]:
        return [
            InvariantViolation(
                path=f"/body/unmapped_content/{index}/provenance",
                code=CODE,
                message=f"unmapped_content note '{note.note_id}' has no provenance",
            )
            for index, note in enumerate(notes)
            if note.provenance is None
        ]
