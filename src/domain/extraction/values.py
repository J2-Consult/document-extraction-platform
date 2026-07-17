"""Extraction-cascade value objects (epic E05): what passes exchange.

`PageImage` is a preprocessed working raster of ONE page; `Region` and
`TextSpan` are geometric findings; `PassOutput` is what every pass returns.
Every geometric item names the coordinate space its bbox lives in, and every
`PassOutput` carries method + component_version + transform_to_source, so
`provenance_fragments()` can hand E06 everything a `Provenance` needs
(method, component_version, bbox, coordinate_space, transform) without any
pass-specific glue.

Placement note (flagged per the design doc's "or extend design's
suggestion"): these live in `src/domain/extraction/` — a dedicated module,
one reason to change (SRP), mirroring `src/domain/provenance/`.

Pure domain: no I/O, no framework imports beyond Pydantic.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from domain.artifacts.provenance import ExtractionMethod

# The affine identity, in `Provenance.transform_to_source` order [a,b,c,d,e,f].
IDENTITY_TRANSFORM: tuple[float, float, float, float, float, float] = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

RegionKind = Literal["text", "kv", "table", "checkbox", "mark", "signature", "figure", "unknown"]


class PageImage(BaseModel):
    """One page's preprocessed working raster + the bookkeeping needed to map
    findings on it back to source space."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    page: int = Field(ge=1)
    image_bytes: bytes = Field(min_length=1)
    coordinate_space: str = Field(min_length=1)
    dpi: float = Field(gt=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    transform_to_source: list[float] = Field(min_length=6, max_length=6)


class Region(BaseModel):
    """One detected region: where (page, bbox, space), what kind, how sure."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    page: int = Field(ge=1)
    bbox: list[float] = Field(min_length=4, max_length=4)
    coordinate_space: str = Field(min_length=1)
    kind: RegionKind
    score: float = Field(ge=0, le=1)


class TextSpan(BaseModel):
    """One recognized text run. `confidence` is the recognizer's own raw
    score for the run (native PDF text is deterministic: 1.0)."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    text: str = Field(min_length=1)
    page: int = Field(ge=1)
    bbox: list[float] = Field(min_length=4, max_length=4)
    coordinate_space: str = Field(min_length=1)
    confidence: float = Field(default=1.0, ge=0, le=1)


class PageDims(BaseModel):
    """Source-space page dimensions, carried so downstream consumers
    (assembler, fingerprinting) never re-parse the PDF for geometry."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    page: int = Field(ge=1)
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class ProvenanceFragment(BaseModel):
    """Everything E06 needs to build one `Provenance` from one finding."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    method: ExtractionMethod
    component_version: str = Field(min_length=1)
    page: int = Field(ge=1)
    bbox: list[float] = Field(min_length=4, max_length=4)
    coordinate_space: str = Field(min_length=1)
    transform_to_source: list[float] = Field(min_length=6, max_length=6)


class PassOutput(BaseModel):
    """What every extraction pass returns: findings plus the provenance
    stamping (method, component_version, transform) they were made under."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    method: ExtractionMethod
    component_version: str = Field(min_length=1)
    transform_to_source: list[float] = Field(min_length=6, max_length=6)
    pages: tuple[PageDims, ...] = Field(default_factory=tuple)
    regions: tuple[Region, ...] = Field(default_factory=tuple)
    spans: tuple[TextSpan, ...] = Field(default_factory=tuple)

    def provenance_fragments(self) -> tuple[ProvenanceFragment, ...]:
        """One fragment per finding (regions first, then spans), each carrying
        method, component_version, bbox, coordinate_space, and transform."""
        findings: tuple[Region | TextSpan, ...] = (*self.regions, *self.spans)
        return tuple(
            ProvenanceFragment(
                method=self.method,
                component_version=self.component_version,
                page=item.page,
                bbox=list(item.bbox),
                coordinate_space=item.coordinate_space,
                transform_to_source=list(self.transform_to_source),
            )
            for item in findings
        )
