"""Typed contracts for the three versioned artifacts (template, content,
decoder-mask) plus their shared envelope and provenance shapes.

Pure domain: Pydantic v2 models only, no I/O, no framework imports. The
InvariantValidator (src/services/validation/) enforces the cross-field and
cross-artifact rules these models cannot express on their own.
"""

from __future__ import annotations

from domain.artifacts.canonical import JsonCanonicalSerializer
from domain.artifacts.content import (
    Confidence,
    ContentArtifact,
    ContentBody,
    CoordinateSpace,
    Observation,
    SourceDescriptor,
    UnmappedContent,
    ValueState,
)
from domain.artifacts.envelope import ArtifactEnvelope
from domain.artifacts.errors import InvariantViolation, ValidationReport
from domain.artifacts.mask import (
    DecoderMaskArtifact,
    DecoderMaskBody,
    EntryAttribution,
    MaskEntry,
    MaskRef,
    MaskScope,
    TargetBinding,
    TargetDatatype,
)
from domain.artifacts.provenance import ExtractionMethod, Provenance, SourceRef, WorkingRef
from domain.artifacts.template import (
    FINGERPRINT_PATTERN,
    Anchor,
    ElementKind,
    PageGeometry,
    TableColumn,
    TemplateArtifact,
    TemplateBody,
    TemplateElement,
    TemplateRef,
)

__all__ = [
    "FINGERPRINT_PATTERN",
    "Anchor",
    "ArtifactEnvelope",
    "Confidence",
    "ContentArtifact",
    "ContentBody",
    "CoordinateSpace",
    "DecoderMaskArtifact",
    "DecoderMaskBody",
    "ElementKind",
    "EntryAttribution",
    "ExtractionMethod",
    "InvariantViolation",
    "JsonCanonicalSerializer",
    "MaskEntry",
    "MaskRef",
    "MaskScope",
    "Observation",
    "PageGeometry",
    "Provenance",
    "SourceDescriptor",
    "SourceRef",
    "TableColumn",
    "TargetBinding",
    "TargetDatatype",
    "TemplateArtifact",
    "TemplateBody",
    "TemplateElement",
    "TemplateRef",
    "UnmappedContent",
    "ValidationReport",
    "ValueState",
    "WorkingRef",
]
