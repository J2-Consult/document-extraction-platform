"""Mapping outcome vocabulary (E09 design doc — public shapes BINDING).

`MappingResult` is the pipeline's only output: an outcome, at most one whole
record (NO partial records, ever — `record` is the full mapped record or
None), itemized review items, the contract-validation verdict, and an error
category distinguishing the four failure families. Deterministic by
construction: no timestamps, no ids minted here — same inputs, byte-identical
`model_dump_json()`.

Pure domain vocabulary: no I/O, no framework imports, no adapter imports.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from domain.artifacts.provenance import Provenance

MappingOutcome = Literal[
    "completed",
    "pending_review",
    "pending_template_review",
    "rejected",
    "failed",
]

ContractValidation = Literal["passed", "failed", "not_evaluated"]

# The four failure families, asserted distinct in tests:
#   business_rule          - the external Validation Service's verdict
#   contract               - the mapped record violates the target schema
#   extraction_uncertainty - a value's confidence is below threshold
#   technical              - an adapter/provider failure, nothing wrong with the data
ErrorCategory = Literal["business_rule", "contract", "extraction_uncertainty", "technical"]


class ReviewItem(BaseModel):
    """One element needing a human: what, why, how unsure, and where it came from."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    element: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    provenance: Provenance


class MappingResult(BaseModel):
    """The mapping pipeline's complete, deterministic output."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    outcome: MappingOutcome
    # JSON-shaped data; its real contract is the versioned target schema the
    # BindTargetSchema step validated it against, not a Python type.
    record: dict[str, Any] | None = None
    review_items: tuple[ReviewItem, ...] = ()
    contract_validation: ContractValidation
    error_category: ErrorCategory | None = None
    component_versions: dict[str, str] = Field(default_factory=dict)


class BusinessRuleViolation(BaseModel):
    """One rule violation as reported by the EXTERNAL Validation Service.

    Rule evaluation (totals, cross-field arithmetic, plausibility) never
    happens in this codebase — this shape only carries the external verdict
    so it can be categorized. Identifiers and rule text only, never document
    values.
    """

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    rule_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    fields: tuple[str, ...] = ()


class RulesetVerdict(BaseModel):
    """The external Validation Service's verdict over one mapped record."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    ok: bool
    violations: tuple[BusinessRuleViolation, ...] = ()


def apply_ruleset_verdict(result: MappingResult, verdict: RulesetVerdict) -> MappingResult:
    """Fold the external Validation Service's verdict into a mapping result.

    Pure function of its inputs. Only a `completed` result was ever handed to
    the ruleset (anything else never produced a record to validate), and only
    a failing verdict changes it: outcome `rejected` with the distinct
    `business_rule` category. The record stays — it is whole and
    contract-valid; the business objection is the reviewer's context.
    """
    if verdict.ok or result.outcome != "completed":
        return result
    return result.model_copy(update={"outcome": "rejected", "error_category": "business_rule"})
