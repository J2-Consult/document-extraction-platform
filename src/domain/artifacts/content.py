"""Content artifact: observations extracted from a document, plus provenance.

An observation binds one template element to a decoded value (or the absence
of one) with a state, confidence, and provenance. Business meaning is not
recorded here — a content artifact never resolves what a value MEANS to a
system; masks do that at resolution time (later epics).

Pure domain: no I/O, no framework imports.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from domain.artifacts.envelope import ArtifactEnvelope
from domain.artifacts.provenance import Provenance
from domain.artifacts.template import TemplateRef

# Legal value/state combinations (checks/state_legality.py enforces the
# cross-field rule at the InvariantValidator level, not here — see that
# module's docstring for why this is not also a Pydantic model_validator).
ValueState = Literal["present", "empty", "not_applicable", "unreadable", "not_found"]


class Confidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    raw: float = Field(ge=0, le=1)
    calibrated: float = Field(ge=0, le=1)


class Observation(BaseModel):
    """One decoded (or explicitly absent) value for a single template element."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    element_id: str = Field(min_length=1)
    value: str | None
    state: ValueState
    confidence: Confidence
    provenance: Provenance


class UnmappedContent(BaseModel):
    """A note about document content that was not mapped to any template element."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    note_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    provenance: Provenance


class CoordinateSpace(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    id: str = Field(min_length=1)
    page: int = Field(ge=1)
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    unit: Literal["pt"]
    dpi: float | None = Field(default=None, gt=0)


class SourceDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    media_type: Literal["application/pdf"]
    page_count: int = Field(ge=1)


class ContentBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    content_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    template_ref: TemplateRef | None
    source: SourceDescriptor
    coordinate_spaces: list[CoordinateSpace] = Field(min_length=1)
    observations: list[Observation] = Field(default_factory=list)
    unmapped_content: list[UnmappedContent] = Field(default_factory=list)


class ContentArtifact(ArtifactEnvelope[ContentBody]):
    """`content.json`: envelope + `ContentBody`."""

    artifact_type: Literal["content"] = "content"
