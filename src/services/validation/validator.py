"""InvariantValidator: composition root for the invariant-check pipeline.

Enforces what JSON Schema cannot — cross-field and cross-artifact business
rules — over an `ArtifactBundle`. Never raises: always returns a
`ValidationReport`. Pure domain: no I/O, no framework imports.
"""

from __future__ import annotations

from collections.abc import Sequence

from domain.artifacts.errors import ValidationReport
from services.validation.bundle import ArtifactBundle, InvariantCheck
from services.validation.checks.coordinate_space_resolution import CoordinateSpaceResolutionCheck
from services.validation.checks.corrected_by_required import CorrectedByRequiredCheck
from services.validation.checks.element_resolution import ElementResolutionCheck
from services.validation.checks.envelope_agreement import EnvelopeAgreementCheck
from services.validation.checks.fingerprint_format import FingerprintFormatCheck
from services.validation.checks.mask_attribution import MaskAttributionCheck
from services.validation.checks.mask_scope import MaskScopeCheck
from services.validation.checks.page_range import PageRangeCheck
from services.validation.checks.provenance_required import ProvenanceRequiredCheck
from services.validation.checks.state_legality import StateLegalityCheck
from services.validation.checks.transform_well_formed import TransformWellFormedCheck


class InvariantValidator:
    """Runs a fixed sequence of `InvariantCheck`s over one `ArtifactBundle`."""

    def __init__(self, checks: Sequence[InvariantCheck]) -> None:
        self._checks = tuple(checks)

    def validate(self, bundle: ArtifactBundle) -> ValidationReport:
        violations = [violation for check in self._checks for violation in check.check(bundle)]
        return ValidationReport(ok=not violations, violations=tuple(violations))


def default_validator() -> InvariantValidator:
    """Wires every registered invariant check. New invariant = new entry here."""
    return InvariantValidator(
        checks=[
            ElementResolutionCheck(),
            EnvelopeAgreementCheck(),
            ProvenanceRequiredCheck(),
            MaskScopeCheck(),
            MaskAttributionCheck(),
            FingerprintFormatCheck(),
            StateLegalityCheck(),
            CoordinateSpaceResolutionCheck(),
            PageRangeCheck(),
            TransformWellFormedCheck(),
            CorrectedByRequiredCheck(),
        ]
    )
