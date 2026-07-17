"""ReleaseService (epic E08): publication + atomic release-unit activation.

Every mutation is an APPEND through the LifecycleRepository port with actor
identity (`ChangeRecord`); vendor-mask publication requires the admin scope —
enforced here at the service boundary, not as a UI convention. Activation
validates each mask against the unit's template first: an old mask NEVER
implicitly applies to an incompatible template version (rejected, not
guessed), and a draft that fails referential validation cannot go live.
The repository then activates the whole unit atomically.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from domain.artifacts.mask import DecoderMaskArtifact
from domain.artifacts.template import TemplateArtifact
from ports.clock import Clock
from ports.lifecycle import ChangeRecord, LifecycleRepository, ReleaseUnit
from services.lifecycle.errors import (
    AdminScopeRequiredError,
    DraftValidationError,
    IncompatibleReleaseError,
    UnknownArtifactError,
)
from services.lifecycle.migration import MaskMigrator
from services.validation.validator import InvariantValidator

ADMIN_SCOPE = "admin"


class Principal(BaseModel):
    """The authenticated caller of a lifecycle operation."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    actor: str = Field(min_length=1)
    scopes: frozenset[str]


class ReleaseService:
    def __init__(self, repository: LifecycleRepository, validator: InvariantValidator, clock: Clock) -> None:
        self._repository = repository
        self._migrator = MaskMigrator(validator)
        self._clock = clock

    def publish_template_version(self, artifact: TemplateArtifact, principal: Principal, reason: str) -> None:
        self._repository.append_template_version(artifact, self._change(principal, reason))

    def publish_mask_version(self, artifact: DecoderMaskArtifact, principal: Principal, reason: str) -> None:
        if artifact.body.scope == "vendor" and ADMIN_SCOPE not in principal.scopes:
            raise AdminScopeRequiredError(
                f"vendor-mask publication requires the '{ADMIN_SCOPE}' scope (mask {artifact.artifact_id})"
            )
        self._repository.append_mask_version(artifact, self._change(principal, reason))

    def activate(self, unit: ReleaseUnit, principal: Principal, reason: str) -> None:
        """Validate compatibility, then activate template + masks atomically."""
        template = self._repository.get_template(unit.template_ref)
        if template is None:
            raise UnknownArtifactError(
                f"release unit references unknown template {unit.template_ref.template_id} v{unit.template_ref.version}"
            )
        for ref in unit.mask_refs:
            mask = self._repository.get_mask(ref)
            if mask is None:
                raise UnknownArtifactError(f"release unit references unknown mask {ref.mask_id} v{ref.version}")
            self._require_compatible(mask, unit, template)
        self._repository.activate_release_unit(unit, self._change(principal, reason))

    def _require_compatible(self, mask: DecoderMaskArtifact, unit: ReleaseUnit, template: TemplateArtifact) -> None:
        if mask.body.template_ref != unit.template_ref:
            raise IncompatibleReleaseError(
                f"mask {mask.artifact_id} v{mask.version} references template "
                f"v{mask.body.template_ref.version}, not the release unit's "
                f"v{unit.template_ref.version} — refusing to guess a mapping"
            )
        report = self._migrator.validate_for_activation(mask.body, template.body)
        if not report.ok:
            raise DraftValidationError(
                f"mask {mask.artifact_id} v{mask.version} failed validation against "
                f"template v{template.version} ({len(report.violations)} violations)",
                report,
            )

    def _change(self, principal: Principal, reason: str) -> ChangeRecord:
        return ChangeRecord(actor=principal.actor, reason=reason, at=self._clock.now())
