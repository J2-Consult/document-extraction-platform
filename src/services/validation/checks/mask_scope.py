"""`scope == "vendor" <=> tenant_id is null` (FIXTURES-SPEC.md, decoder-mask body).

Both directions of the biconditional are checked: a vendor mask carrying a
tenant_id is a leak of tenant scoping into a shared vendor artifact; a
customer mask missing a tenant_id cannot be tenant-isolated at all.
"""

from __future__ import annotations

from domain.artifacts.errors import InvariantViolation
from services.validation.bundle import ArtifactBundle

VENDOR_WITH_TENANT_CODE = "vendor-mask-with-tenant"
CUSTOMER_MISSING_TENANT_CODE = "customer-mask-missing-tenant"


class MaskScopeCheck:
    def check(self, bundle: ArtifactBundle) -> list[InvariantViolation]:
        if bundle.mask is None:
            return []
        body = bundle.mask.body
        if body.scope == "vendor" and body.tenant_id is not None:
            return [
                InvariantViolation(
                    path="/body/tenant_id",
                    code=VENDOR_WITH_TENANT_CODE,
                    message=f"vendor-scope mask '{body.mask_id}' must have a null tenant_id",
                )
            ]
        if body.scope == "customer" and body.tenant_id is None:
            return [
                InvariantViolation(
                    path="/body/tenant_id",
                    code=CUSTOMER_MISSING_TENANT_CODE,
                    message=f"customer-scope mask '{body.mask_id}' requires a non-null tenant_id",
                )
            ]
        return []
