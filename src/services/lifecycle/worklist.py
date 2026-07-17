"""Consultant worklist (epic E08): template elements the vendor baseline mask
does not cover yet.

Pure computation over SHARED artifacts only — a vendor template body and a
vendor-scope mask body. The integration suite executes it under the E02
`synthesis` role, whose row-level security shows it exactly those shared rows
and nothing customer-scoped (customer masks and private templates are
invisible by policy, not by this code's politeness).

Labels are anchors for other elements, not extraction targets, so they are
never "uncovered".
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from domain.artifacts.mask import DecoderMaskBody
from domain.artifacts.template import ElementKind, TemplateBody, TemplateRef
from services.lifecycle.errors import LifecycleError


class UncoveredElement(BaseModel):
    """One extraction-relevant template element with no vendor-mask entry."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    element_id: str = Field(min_length=1)
    kind: ElementKind
    page: int = Field(ge=1)


def uncovered_elements(template: TemplateBody, vendor_mask: DecoderMaskBody) -> tuple[UncoveredElement, ...]:
    """Extraction-target elements of `template` without an entry in `vendor_mask`."""
    if vendor_mask.scope != "vendor":
        raise LifecycleError("the consultant worklist baseline must be a vendor-scope mask")
    template_ref = TemplateRef(template_id=template.template_id, version=template.version)
    if vendor_mask.template_ref != template_ref:
        raise LifecycleError(
            f"mask {vendor_mask.mask_id} v{vendor_mask.version} references template "
            f"v{vendor_mask.template_ref.version}, not v{template.version}"
        )
    covered = {entry.element_id for entry in vendor_mask.entries}
    return tuple(
        UncoveredElement(element_id=element.element_id, kind=element.kind, page=element.page)
        for element in sorted(template.elements, key=lambda element: element.element_id)
        if element.kind != "label" and element.element_id not in covered
    )
