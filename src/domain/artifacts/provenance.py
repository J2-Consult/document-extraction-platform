"""Provenance shapes: where a value or note came from and how it was derived.

E01 owns the shape; E06 extends it (coordinate-space transforms, correction
provenance) without editing these classes — new fields arrive as additive,
backward-compatible changes in a later epic's PR, not a rewrite here.

Pure domain: no I/O, no framework imports.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ExtractionMethod = Literal["pdf_text", "ocr", "vlm_region", "detector", "human"]

_SHA256_HEX_PATTERN = r"^[0-9a-f]{64}$"


class SourceRef(BaseModel):
    """Reference into the original, immutable source document."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    artifact_sha256: str = Field(pattern=_SHA256_HEX_PATTERN)
    page: int = Field(ge=1)


class WorkingRef(BaseModel):
    """Reference into the (possibly preprocessed) working artifact used for extraction."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    artifact_sha256: str = Field(pattern=_SHA256_HEX_PATTERN)
    coordinate_space: str = Field(min_length=1)


class Provenance(BaseModel):
    """Provenance required on every observation, unmapped-content note, and correction.

    `corrected_by` (E09, disclosed addition — CLAUDE.md PROVENANCE MODEL NOTE):
    the identity of the human who made a `method == "human"` correction.
    Additive and optional so every pre-existing provenance construction
    (method != "human") is unaffected; `services.validation.checks
    .corrected_by_required` enforces the cross-field rule that it must be set
    when `method == "human"` — the same "no value/correction without
    provenance" invariant CLAUDE.md requires for every other value.
    """

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    source: SourceRef
    working: WorkingRef
    bbox: list[float] = Field(min_length=4, max_length=4)
    method: ExtractionMethod
    component_version: str = Field(min_length=1)
    transform_to_source: list[float] = Field(min_length=6, max_length=6)
    corrected_by: str | None = Field(default=None, min_length=1)
