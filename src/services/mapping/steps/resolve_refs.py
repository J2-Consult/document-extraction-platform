"""Step 1 — ResolveRefs: join mask entries to content observations.

Refuses to guess: the content, the mask, and the template must all agree on
one template version, or the document belongs in `pending_template_review`
(the mapping is never forced — E08's held-document policy pairs with this).
"""

from __future__ import annotations

from domain.artifacts.content import ContentBody
from domain.artifacts.mask import DecoderMaskBody
from domain.artifacts.template import TemplateBody, TemplateRef
from services.mapping.steps.shapes import ResolvedEntry, ResolvedRefs


class TemplateMismatchError(Exception):
    """Content/mask/template do not agree on one template version."""


class ResolveRefs:
    def resolve(self, content: ContentBody, mask: DecoderMaskBody, template: TemplateBody) -> ResolvedRefs:
        template_ref = TemplateRef(template_id=template.template_id, version=template.version)
        if content.template_ref is None:
            raise TemplateMismatchError("content has no template_ref; first-of-template documents are held")
        if content.template_ref != template_ref or mask.template_ref != template_ref:
            raise TemplateMismatchError(
                f"content (v{content.template_ref.version}), mask (v{mask.template_ref.version}) and "
                f"template (v{template.version}) must agree on one template version"
            )
        observations = {observation.element_id: observation for observation in content.observations}
        return ResolvedRefs(
            entries=tuple(
                ResolvedEntry(entry=entry, observation=observations.get(entry.element_id)) for entry in mask.entries
            )
        )
