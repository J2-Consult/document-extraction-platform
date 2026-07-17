"""EffectiveMaskMaterializer (ADR 20, epic E08).

A customer's mask is never a runtime merge of arrays: this service turns a
vendor baseline + the customer's deltas into ONE complete, materialized
effective mask — full baseline coverage, every entry attributed (`origin`,
`inherited_from`, `overridden`). Resolution later SELECTS this mask.

Re-materialization when the customer adopts a newer vendor baseline is an
explicit, reviewable event: `adopt_baseline` returns the appended-version
draft together with a `MaterializationEvent` naming the trigger and actor —
it never silently applies anything.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from domain.artifacts.mask import DecoderMaskBody, EntryAttribution, MaskEntry, MaskRef, TargetBinding
from services.lifecycle.errors import LifecycleError


class CustomerOverride(BaseModel):
    """One customer-authored delta over a vendor baseline entry."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    element_id: str = Field(min_length=1)
    semantic_role: str = Field(min_length=1)
    target: TargetBinding
    enum_map: dict[str, str | bool] | None = None
    section_path: str | None = None
    validated_by: str | None = None


class MaterializationEvent(BaseModel):
    """The reviewable record of WHY a materialized mask version was produced."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    trigger: Literal["baseline_adoption"]
    baseline_ref: MaskRef
    actor: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class BaselineAdoption(BaseModel):
    """An appended mask version + the explicit event that produced it."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    mask_body: DecoderMaskBody
    event: MaterializationEvent


class EffectiveMaskMaterializer:
    def materialize(
        self,
        baseline: DecoderMaskBody,
        *,
        mask_id: str,
        version: int,
        tenant_id: str,
        overrides: Sequence[CustomerOverride],
    ) -> DecoderMaskBody:
        """Vendor baseline + customer deltas -> one complete attributed customer mask."""
        if baseline.scope != "vendor":
            raise LifecycleError(f"materialization baseline must be vendor-scope, got '{baseline.scope}'")
        override_by_element = _index_overrides(overrides, baseline)
        baseline_ref = MaskRef(mask_id=baseline.mask_id, version=baseline.version)
        entries = [
            _materialized_entry(entry, override_by_element.get(entry.element_id), baseline_ref)
            for entry in baseline.entries
        ]
        return DecoderMaskBody(
            mask_id=mask_id,
            version=version,
            scope="customer",
            tenant_id=tenant_id,
            template_ref=baseline.template_ref,
            system_context=baseline.system_context,
            entries=entries,
        )

    def adopt_baseline(
        self, new_baseline: DecoderMaskBody, current: DecoderMaskBody, *, actor: str, reason: str
    ) -> BaselineAdoption:
        """Re-materialize `current` over a newer vendor baseline — explicitly.

        The customer's own overrides are carried over; the result is a NEW
        appended version plus the event a reviewer signs off on. This method
        persists nothing: adoption without review is unrepresentable.
        """
        if current.tenant_id is None:
            raise LifecycleError("baseline adoption re-materializes a customer mask, not a vendor one")
        overrides = tuple(_as_override(entry) for entry in current.entries if entry.attribution.overridden)
        mask_body = self.materialize(
            new_baseline,
            mask_id=current.mask_id,
            version=current.version + 1,
            tenant_id=current.tenant_id,
            overrides=overrides,
        )
        event = MaterializationEvent(
            trigger="baseline_adoption",
            baseline_ref=MaskRef(mask_id=new_baseline.mask_id, version=new_baseline.version),
            actor=actor,
            reason=reason,
        )
        return BaselineAdoption(mask_body=mask_body, event=event)


def _index_overrides(overrides: Sequence[CustomerOverride], baseline: DecoderMaskBody) -> dict[str, CustomerOverride]:
    baseline_elements = {entry.element_id for entry in baseline.entries}
    indexed: dict[str, CustomerOverride] = {}
    for override in overrides:
        if override.element_id not in baseline_elements:
            raise LifecycleError(f"override targets '{override.element_id}', which the baseline does not cover")
        if override.element_id in indexed:
            raise LifecycleError(f"duplicate override for element '{override.element_id}'")
        indexed[override.element_id] = override
    return indexed


def _materialized_entry(
    baseline_entry: MaskEntry, override: CustomerOverride | None, baseline_ref: MaskRef
) -> MaskEntry:
    if override is None:
        return baseline_entry.model_copy(
            update={
                "attribution": EntryAttribution(
                    origin="vendor", inherited_from=baseline_ref, overridden=False, validated_by=None
                )
            }
        )
    return MaskEntry(
        element_id=override.element_id,
        semantic_role=override.semantic_role,
        target=override.target,
        enum_map=override.enum_map,
        section_path=override.section_path,
        attribution=EntryAttribution(
            origin="customer",
            inherited_from=baseline_ref,
            overridden=True,
            validated_by=override.validated_by,
        ),
    )


def _as_override(entry: MaskEntry) -> CustomerOverride:
    return CustomerOverride(
        element_id=entry.element_id,
        semantic_role=entry.semantic_role,
        target=entry.target,
        enum_map=entry.enum_map,
        section_path=entry.section_path,
        validated_by=entry.attribution.validated_by,
    )
