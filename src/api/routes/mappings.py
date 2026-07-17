"""POST /mappings/records (epic E09).

Thin by design (CLAUDE.md): parse -> authorize -> call the injected executor
-> shape response. Two authorization layers, both explicit:

1. WHO: the `Authorizer` seam (E03) yields the authenticated tenant or 401.
2. WHAT: a per-TARGET-SCHEMA policy — not every caller may bind every target
   schema; an unauthorized binding is 403 before any mapping work happens.

Response discipline: the response carries the shaped `MappingResult` fields
only — the mapped record and review-item provenance (ids, hashes, bboxes),
never raw document content beyond the mapped record. Errors to the client
are generic; the itemized detail is logged server-side with ids only.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from api.authorization import Authorizer, NotAuthorizedError
from services.mapping.outcome import ContractValidation, ErrorCategory, MappingOutcome, MappingResult, ReviewItem

logger = logging.getLogger(__name__)


@runtime_checkable
class MappingExecutor(Protocol):
    """Loads the pinned artifacts for a document and runs the mapping pipeline.

    The route stays thin: artifact loading + pipeline wiring live behind this
    seam (constructor-injected), never in the router.
    """

    def execute(
        self,
        *,
        tenant_id: str,
        document_id: str,
        system_context: str,
        target_schema: str,
        target_schema_version: int,
    ) -> MappingResult: ...


@runtime_checkable
class TargetSchemaPolicy(Protocol):
    """Per-target-schema authorization: may this caller bind this schema?"""

    def allows(self, tenant_id: str, target_schema: str) -> bool: ...


class AllowListSchemaPolicy:
    """Explicit caller -> allowed-target-schemas allow-list (deny by default)."""

    def __init__(self, allowed: Mapping[str, frozenset[str]]) -> None:
        self._allowed = dict(allowed)

    def allows(self, tenant_id: str, target_schema: str) -> bool:
        return target_schema in self._allowed.get(tenant_id, frozenset())


class MappingRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    document_id: str = Field(min_length=1)
    system_context: str = Field(min_length=1)
    target_schema: str = Field(min_length=1)
    target_schema_version: int = Field(ge=1)


class MappingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    outcome: MappingOutcome
    record: dict[str, Any] | None
    review_items: tuple[ReviewItem, ...]
    contract_validation: ContractValidation
    error_category: ErrorCategory | None
    component_versions: dict[str, str]


def build_mappings_router(
    executor: MappingExecutor,
    *,
    authorizer: Authorizer,
    schema_policy: TargetSchemaPolicy,
) -> APIRouter:
    """Constructor-injected route factory — no globals, no service locator."""
    router = APIRouter(prefix="/mappings", tags=["mappings"])

    @router.post("/records", response_model=MappingResponse)
    def map_record(request: Request, body: MappingRequestBody) -> MappingResponse:
        try:
            tenant_id = authorizer.authorize(request)
        except NotAuthorizedError:
            raise HTTPException(status_code=401, detail="not authorized") from None

        if not schema_policy.allows(tenant_id, body.target_schema):
            raise HTTPException(status_code=403, detail="not authorized for this target schema")

        try:
            result = executor.execute(
                tenant_id=tenant_id,
                document_id=body.document_id,
                system_context=body.system_context,
                target_schema=body.target_schema,
                target_schema_version=body.target_schema_version,
            )
        except Exception:
            logger.exception(
                "mapping failed",
                extra={"tenant_id": tenant_id, "document_id": body.document_id},
            )
            raise HTTPException(status_code=500, detail="mapping failed") from None

        return MappingResponse(
            outcome=result.outcome,
            record=result.record,
            review_items=result.review_items,
            contract_validation=result.contract_validation,
            error_category=result.error_category,
            component_versions=result.component_versions,
        )

    return router
