"""ValidationServiceClient Protocol (E09) — interface only.

The external Validation Service evaluates BUSINESS rules (totals,
cross-field arithmetic, plausibility); this codebase never does. This module
defines only the wire request shape and the client Protocol; a concrete HTTP
client is future work and MUST implement exactly this interface (Liskov:
substitutable with the recording fake used in the contract test).

`ValidationRequest.bboxes` maps to the wire key "_bboxes" via alias — a
leading-underscore Python field would collide with Pydantic's private-
attribute convention, same idiom as `TargetBinding.target_schema`/"schema".
The recorded wire form is PINNED by
tests/contracts/validation_service_request.schema.json.
"""

from __future__ import annotations

from typing import Protocol, TypedDict, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from services.mapping.outcome import RulesetVerdict

# One flattened record value: scalar-only, per the pinned contract schema.
FlatValue = str | float | int | bool


class FieldBox(TypedDict):
    """Where one top-level target field was read: source page + bbox."""

    page: int
    bbox: list[float]


class ValidationRequest(BaseModel):
    """The preparator's hand-off to the external ruleset (wire form pinned)."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, populate_by_name=True)

    ruleset_id: str = Field(min_length=1)
    target_schema: str = Field(min_length=1)
    target_schema_version: int = Field(ge=1)
    record: dict[str, FlatValue]
    bboxes: dict[str, FieldBox] = Field(alias="_bboxes")


@runtime_checkable
class ValidationServiceClient(Protocol):
    def evaluate(self, request: ValidationRequest) -> RulesetVerdict:
        """Run the ruleset over one prepared record; never raises for a rule
        violation — that is a verdict, not an error."""
        ...
