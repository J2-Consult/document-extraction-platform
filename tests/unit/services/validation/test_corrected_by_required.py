"""E09's narrow addition to the InvariantValidator (CLAUDE.md PROVENANCE MODEL
NOTE, disclosed in the E09 report): `provenance.method == "human"` requires
`provenance.corrected_by` to be set — a human correction without an
identified corrector is exactly the "correction without provenance" pattern
CLAUDE.md forbids. New check module, registered in `default_validator()`;
E01's existing check modules are untouched.
"""

from __future__ import annotations

from domain.artifacts.content import (
    Confidence,
    ContentArtifact,
    ContentBody,
    CoordinateSpace,
    Observation,
    SourceDescriptor,
)
from domain.artifacts.provenance import Provenance, SourceRef, WorkingRef
from services.validation.bundle import ArtifactBundle
from services.validation.checks.corrected_by_required import CODE, CorrectedByRequiredCheck
from services.validation.validator import default_validator


def _provenance(*, method: str, corrected_by: str | None) -> Provenance:
    return Provenance(
        source=SourceRef(artifact_sha256="0" * 64, page=1),
        working=WorkingRef(artifact_sha256="0" * 64, coordinate_space="page-1"),
        bbox=[0, 0, 10, 10],
        method=method,  # type: ignore[arg-type]
        component_version="fixture-1.0.0",
        transform_to_source=[1, 0, 0, 1, 0, 0],
        corrected_by=corrected_by,
    )


def _content_bundle(provenance: Provenance) -> ArtifactBundle:
    body = ContentBody(
        content_id="content_x",
        document_id="doc_x",
        version=1,
        template_ref=None,
        source=SourceDescriptor(sha256="0" * 64, media_type="application/pdf", page_count=1),
        coordinate_spaces=[CoordinateSpace(id="page-1", page=1, width=10, height=10, unit="pt")],
        observations=[
            Observation(
                element_id="el_x",
                value="corrected value",
                state="present",
                confidence=Confidence(raw=1.0, calibrated=1.0),
                provenance=provenance,
            )
        ],
    )
    content = ContentArtifact(
        artifact_id="content_x",
        version=1,
        tenant_id=None,
        created_at="2026-07-01T00:00:00Z",  # type: ignore[arg-type]
        body=body,
    )
    return ArtifactBundle(content=content)


def test_human_provenance_without_corrected_by_is_rejected() -> None:
    bundle = _content_bundle(_provenance(method="human", corrected_by=None))

    violations = CorrectedByRequiredCheck().check(bundle)

    assert len(violations) == 1
    assert violations[0].code == CODE
    assert violations[0].path == "/body/observations/0/provenance/corrected_by"


def test_human_provenance_with_corrected_by_passes() -> None:
    bundle = _content_bundle(_provenance(method="human", corrected_by="reviewer-1"))

    assert CorrectedByRequiredCheck().check(bundle) == []


def test_non_human_provenance_never_requires_corrected_by() -> None:
    bundle = _content_bundle(_provenance(method="pdf_text", corrected_by=None))

    assert CorrectedByRequiredCheck().check(bundle) == []


def test_default_validator_rejects_human_correction_missing_corrector_identity() -> None:
    bundle = _content_bundle(_provenance(method="human", corrected_by=None))

    report = default_validator().validate(bundle)

    assert report.ok is False
    assert any(violation.code == CODE for violation in report.violations)
