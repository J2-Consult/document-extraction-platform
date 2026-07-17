"""Mask entry attribution rules (FIXTURES-SPEC.md, decoder-mask body):

- `overridden == True` implies `inherited_from` is non-null (an override has
  to be an override of something).
- Every entry in a vendor-scope mask carries `validated_by` (a vendor
  baseline has no inheritance chain to fall back on for accountability).
"""

from __future__ import annotations

from domain.artifacts.errors import InvariantViolation
from services.validation.bundle import ArtifactBundle

OVERRIDDEN_WITHOUT_INHERITED_FROM_CODE = "overridden-without-inherited-from"
VENDOR_ENTRY_MISSING_VALIDATED_BY_CODE = "vendor-entry-missing-validated-by"


class MaskAttributionCheck:
    def check(self, bundle: ArtifactBundle) -> list[InvariantViolation]:
        if bundle.mask is None:
            return []
        body = bundle.mask.body
        violations: list[InvariantViolation] = []
        for index, entry in enumerate(body.entries):
            attribution = entry.attribution
            if attribution.overridden and attribution.inherited_from is None:
                violations.append(
                    InvariantViolation(
                        path=f"/body/entries/{index}/attribution/inherited_from",
                        code=OVERRIDDEN_WITHOUT_INHERITED_FROM_CODE,
                        message=f"entry '{entry.element_id}' is overridden but has no inherited_from",
                    )
                )
            if body.scope == "vendor" and attribution.validated_by is None:
                violations.append(
                    InvariantViolation(
                        path=f"/body/entries/{index}/attribution/validated_by",
                        code=VENDOR_ENTRY_MISSING_VALIDATED_BY_CODE,
                        message=f"vendor-scope entry '{entry.element_id}' has no validated_by",
                    )
                )
        return violations
