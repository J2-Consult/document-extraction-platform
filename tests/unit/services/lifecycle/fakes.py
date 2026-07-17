"""In-memory LifecycleRepository fake (a pure test double, never shipped).

Mirrors the port contract exactly:

- appends are append-only — a duplicate (artifact_id, version) raises
  `DuplicateVersionError`, there is no update method at all;
- every mutation records the caller's `ChangeRecord` (actor identity);
- `activate_release_unit` is ATOMIC: every ref is resolved before any
  activation state changes, so a bad unit leaves the store untouched.
"""

from __future__ import annotations

from domain.artifacts.mask import DecoderMaskArtifact, MaskRef
from domain.artifacts.template import TemplateArtifact, TemplateRef
from ports.lifecycle import ChangeRecord, DuplicateVersionError, ReleaseUnit, UnknownReleaseRefError


class InMemoryLifecycleRepository:
    def __init__(self) -> None:
        self._templates: dict[tuple[str, int], tuple[TemplateArtifact, ChangeRecord]] = {}
        self._masks: dict[tuple[str, int], tuple[DecoderMaskArtifact, ChangeRecord]] = {}
        # Activation pointer mirrors the DB's one-active-per-context index:
        # (tenant_id, template_id, system_context) -> active mask ref.
        self._active: dict[tuple[str | None, str, str], MaskRef] = {}
        self.activations: list[tuple[ReleaseUnit, ChangeRecord]] = []

    def append_template_version(self, artifact: TemplateArtifact, change: ChangeRecord) -> None:
        key = (artifact.artifact_id, artifact.version)
        if key in self._templates:
            raise DuplicateVersionError(f"template {key[0]} v{key[1]} already exists (append-only)")
        self._templates[key] = (artifact, change)

    def append_mask_version(self, artifact: DecoderMaskArtifact, change: ChangeRecord) -> None:
        key = (artifact.artifact_id, artifact.version)
        if key in self._masks:
            raise DuplicateVersionError(f"mask {key[0]} v{key[1]} already exists (append-only)")
        self._masks[key] = (artifact, change)

    def activate_release_unit(self, unit: ReleaseUnit, change: ChangeRecord) -> None:
        template_key = (unit.template_ref.template_id, unit.template_ref.version)
        if template_key not in self._templates:
            raise UnknownReleaseRefError(f"template {template_key[0]} v{template_key[1]} not found")
        masks = []
        for ref in unit.mask_refs:  # resolve EVERY ref before touching any state (atomicity)
            stored = self._masks.get((ref.mask_id, ref.version))
            if stored is None:
                raise UnknownReleaseRefError(f"mask {ref.mask_id} v{ref.version} not found")
            masks.append(stored[0])
        for mask in masks:
            body = mask.body
            context_key = (mask.tenant_id, body.template_ref.template_id, body.system_context)
            self._active[context_key] = MaskRef(mask_id=body.mask_id, version=body.version)
        self.activations.append((unit, change))

    def get_template(self, ref: TemplateRef) -> TemplateArtifact | None:
        stored = self._templates.get((ref.template_id, ref.version))
        return stored[0] if stored else None

    def get_mask(self, ref: MaskRef) -> DecoderMaskArtifact | None:
        stored = self._masks.get((ref.mask_id, ref.version))
        return stored[0] if stored else None

    def get_active_mask(
        self, template_id: str, system_context: str, tenant_id: str | None
    ) -> DecoderMaskArtifact | None:
        ref = self._active.get((tenant_id, template_id, system_context))
        return self.get_mask(ref) if ref else None

    def list_template_versions(self, template_id: str) -> tuple[int, ...]:
        return tuple(sorted(version for identifier, version in self._templates if identifier == template_id))

    def list_mask_versions(self, mask_id: str) -> tuple[int, ...]:
        return tuple(sorted(version for identifier, version in self._masks if identifier == mask_id))

    # Test-inspection helpers (not part of the port).

    def template_change(self, template_id: str, version: int) -> ChangeRecord:
        return self._templates[(template_id, version)][1]

    def mask_change(self, mask_id: str, version: int) -> ChangeRecord:
        return self._masks[(mask_id, version)][1]
