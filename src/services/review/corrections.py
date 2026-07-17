"""Review corrections (E09): the human half of the pending_review loop.

A correction never edits an observation in place — it produces a NEW
observation whose provenance says exactly what happened: `method="human"`,
`corrected_by=<actor>`, while `source`/`working`/`bbox`/`transform` keep
pointing at where the uncertain value was READ (the human confirmed what the
document says there; the location is unchanged). The corrected observations
land in an APPENDED content-body version (CLAUDE.md: never mutate a
versioned artifact), which re-enters the mapping pipeline.

Authenticated + audited: the caller passes a `Corrector` (an authenticated
actor identity — authentication itself happens at the API edge), and the
service records a `CorrectionAudit` with the actor, the structural ids, and
the injected clock's timestamp. Identifiers only in the audit — never the
corrected value.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from domain.artifacts.content import Confidence, ContentBody, Observation
from domain.artifacts.provenance import Provenance
from ports.clock import Clock
from services.mapping.outcome import MappingResult, ReviewItem
from services.mapping.pipeline import MappingPipeline, MappingRequest

# A human read the region and asserted the value: deterministic full score,
# same convention as the extractor's whole-text-layer absence assertions.
_HUMAN_CONFIDENCE = 1.0

CORRECTION_COMPONENT_VERSION = "review-correction-1.0.0"


class UnknownReviewElementError(Exception):
    """The review item names an element the content never observed."""


class Corrector(BaseModel):
    """The authenticated actor applying a correction (identity, not a claim —
    the API edge authenticated it)."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    actor: str = Field(min_length=1)


class CorrectionAudit(BaseModel):
    """Who corrected what, where, when. Structural identifiers only."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    actor: str = Field(min_length=1)
    element_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    content_id: str = Field(min_length=1)
    content_version: int = Field(ge=1)
    at: float


class CorrectionOutcome(BaseModel):
    """Everything one correction produced: the new observation, the appended
    content version carrying it, the re-mapping result, and the audit record."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    observation: Observation
    content: ContentBody
    result: MappingResult
    audit: CorrectionAudit


class CorrectionService:
    def __init__(self, pipeline: MappingPipeline, clock: Clock) -> None:
        self._pipeline = pipeline
        self._clock = clock

    def apply_correction(
        self,
        *,
        review_item: ReviewItem,
        corrected_value: str,
        corrector: Corrector,
        request: MappingRequest,
    ) -> CorrectionOutcome:
        original = self._observed(request.content, review_item.element)
        observation = _corrected_observation(original, corrected_value, corrector.actor)
        content = _appended_version(request.content, observation)
        result = self._pipeline.run(
            MappingRequest(
                content=content,
                mask=request.mask,
                template=request.template,
                target_schema_version=request.target_schema_version,
            )
        )
        audit = CorrectionAudit(
            actor=corrector.actor,
            element_id=observation.element_id,
            document_id=content.document_id,
            content_id=content.content_id,
            content_version=content.version,
            at=self._clock.now(),
        )
        return CorrectionOutcome(observation=observation, content=content, result=result, audit=audit)

    def _observed(self, content: ContentBody, element_id: str) -> Observation:
        for observation in content.observations:
            if observation.element_id == element_id:
                return observation
        raise UnknownReviewElementError(f"content '{content.content_id}' has no observation for '{element_id}'")


def _corrected_observation(original: Observation, corrected_value: str, actor: str) -> Observation:
    provenance = Provenance(
        source=original.provenance.source,
        working=original.provenance.working,
        bbox=list(original.provenance.bbox),
        method="human",
        component_version=CORRECTION_COMPONENT_VERSION,
        transform_to_source=list(original.provenance.transform_to_source),
        corrected_by=actor,
    )
    return Observation(
        element_id=original.element_id,
        value=corrected_value,
        state="present",
        confidence=Confidence(raw=_HUMAN_CONFIDENCE, calibrated=_HUMAN_CONFIDENCE),
        provenance=provenance,
    )


def _appended_version(content: ContentBody, corrected: Observation) -> ContentBody:
    observations = [
        corrected if observation.element_id == corrected.element_id else observation
        for observation in content.observations
    ]
    return content.model_copy(update={"version": content.version + 1, "observations": observations})
