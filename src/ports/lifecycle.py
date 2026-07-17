"""LifecycleRepository port (epic E08): append-only artifact lifecycle.

Templates and decoder masks are versioned artifacts — every lifecycle
mutation is an APPEND of a new version carrying actor identity (who/when/why
via `ChangeRecord`); there is deliberately no update method on this port, so
"mutate a versioned artifact" is unrepresentable. `activate_release_unit` is
the one activation-state transition and it is atomic: either the whole
release unit (template + its required masks) becomes active or nothing does.

Concrete implementations: `adapters/postgres/lifecycle_repo.py` (real, against
E02's `templates`/`decoder_masks` tables) and an in-memory fake for unit tests
(`tests/unit/services/lifecycle/fakes.py` — a pure test double, never shipped).

Pure interface + data shapes: no I/O here, no framework imports.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from domain.artifacts.mask import DecoderMaskArtifact, MaskRef
from domain.artifacts.template import TemplateArtifact, TemplateRef


class ChangeRecord(BaseModel):
    """Actor identity for one lifecycle mutation: who, when (epoch seconds), why."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    actor: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    at: float


class ReleaseUnit(BaseModel):
    """A template version plus the mask versions that must go live with it."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    template_ref: TemplateRef
    mask_refs: tuple[MaskRef, ...] = Field(min_length=1)


class DuplicateVersionError(Exception):
    """Appending an (artifact_id, version) that already exists — versions are immutable."""


class UnknownReleaseRefError(Exception):
    """A release unit referenced a template/mask version that does not exist."""


@runtime_checkable
class LifecycleRepository(Protocol):
    def append_template_version(self, artifact: TemplateArtifact, change: ChangeRecord) -> None:
        """Append a new template version. Raises `DuplicateVersionError` if it exists."""
        ...

    def append_mask_version(self, artifact: DecoderMaskArtifact, change: ChangeRecord) -> None:
        """Append a new (inactive) mask version. Raises `DuplicateVersionError` if it exists."""
        ...

    def activate_release_unit(self, unit: ReleaseUnit, change: ChangeRecord) -> None:
        """Atomically make the unit's masks the active ones for their
        (tenant, template, system_context). All-or-nothing: raises
        `UnknownReleaseRefError` (state untouched) when any ref is missing."""
        ...

    def get_template(self, ref: TemplateRef) -> TemplateArtifact | None: ...

    def get_mask(self, ref: MaskRef) -> DecoderMaskArtifact | None: ...

    def get_active_mask(
        self, template_id: str, system_context: str, tenant_id: str | None
    ) -> DecoderMaskArtifact | None:
        """The single active mask for (tenant, template, context), if any —
        resolution is selection of ONE materialized mask, never a merge."""
        ...

    def list_template_versions(self, template_id: str) -> tuple[int, ...]: ...

    def list_mask_versions(self, mask_id: str) -> tuple[int, ...]: ...
