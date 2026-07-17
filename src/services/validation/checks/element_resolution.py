"""Every `element_id` in content observations and mask entries must resolve
against the referenced template's elements — something JSON Schema cannot
express because it requires looking across two artifacts.

Silently passes (no violations) when the referencing artifact has no
`template_ref` (e.g. an unmasked document) or when the caller did not supply
`bundle.template` — this check does no I/O, so an absent template in the
bundle means "nothing to resolve against", not "resolution failed".
"""

from __future__ import annotations

from domain.artifacts.errors import InvariantViolation
from domain.artifacts.template import TemplateArtifact
from services.validation.bundle import ArtifactBundle

CODE = "unknown-element-id"


class ElementResolutionCheck:
    def check(self, bundle: ArtifactBundle) -> list[InvariantViolation]:
        template = bundle.template
        if template is None:
            return []
        known_ids = {element.element_id for element in template.body.elements}
        return [
            *self._check_content(bundle, template, known_ids),
            *self._check_mask(bundle, template, known_ids),
        ]

    def _check_content(
        self, bundle: ArtifactBundle, template: TemplateArtifact, known_ids: set[str]
    ) -> list[InvariantViolation]:
        if bundle.content is None or bundle.content.body.template_ref is None:
            return []
        return [
            InvariantViolation(
                path=f"/body/observations/{index}/element_id",
                code=CODE,
                message=(
                    f"element_id '{observation.element_id}' does not resolve against "
                    f"template '{template.body.template_id}' v{template.body.version}"
                ),
            )
            for index, observation in enumerate(bundle.content.body.observations)
            if observation.element_id not in known_ids
        ]

    def _check_mask(
        self, bundle: ArtifactBundle, template: TemplateArtifact, known_ids: set[str]
    ) -> list[InvariantViolation]:
        if bundle.mask is None:
            return []
        return [
            InvariantViolation(
                path=f"/body/entries/{index}/element_id",
                code=CODE,
                message=(
                    f"element_id '{entry.element_id}' does not resolve against "
                    f"template '{template.body.template_id}' v{template.body.version}"
                ),
            )
            for index, entry in enumerate(bundle.mask.body.entries)
            if entry.element_id not in known_ids
        ]
