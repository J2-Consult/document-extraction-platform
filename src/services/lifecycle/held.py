"""Held first-document policy (v0.2 §5.4, epic E08).

The first document of an unknown template is held in
`pending_template_review` until a consultant registers the template and its
mask activates as a release unit. After activation the held document's
already-extracted content is mapped WITHOUT re-extraction when it is
compatible with the activated template (every observed element resolves);
otherwise re-extraction is required — the mapping is never guessed.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from domain.artifacts.content import ContentBody
from domain.artifacts.template import TemplateBody, TemplateRef

PENDING_TEMPLATE_REVIEW: Literal["pending_template_review"] = "pending_template_review"


class HeldDocument(BaseModel):
    """A document parked until its template/mask release unit activates."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    document_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    fingerprint: str = Field(min_length=1)
    state: Literal["pending_template_review"] = PENDING_TEMPLATE_REVIEW
    held_at: float


class PostActivationDecision(BaseModel):
    """What happens to a held document once the release unit is live."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    document_id: str = Field(min_length=1)
    action: Literal["map_without_reextraction", "reextract"]
    template_ref: TemplateRef
    reason: str = Field(min_length=1)


class HeldDocumentPolicy:
    def hold(self, *, document_id: str, tenant_id: str, fingerprint: str, at: float) -> HeldDocument:
        """Park the first document of an unknown template for review."""
        return HeldDocument(document_id=document_id, tenant_id=tenant_id, fingerprint=fingerprint, held_at=at)

    def release_decision(
        self, held: HeldDocument, content: ContentBody, template: TemplateBody
    ) -> PostActivationDecision:
        """Map without re-extraction iff the held content resolves in the template."""
        template_ref = TemplateRef(template_id=template.template_id, version=template.version)
        known_ids = {element.element_id for element in template.elements}
        unresolved = sorted({observation.element_id for observation in content.observations} - known_ids)
        if unresolved:
            return PostActivationDecision(
                document_id=held.document_id,
                action="reextract",
                template_ref=template_ref,
                reason=f"content observes elements the activated template lacks: {', '.join(unresolved)}",
            )
        return PostActivationDecision(
            document_id=held.document_id,
            action="map_without_reextraction",
            template_ref=template_ref,
            reason="every observed element resolves in the activated template",
        )
