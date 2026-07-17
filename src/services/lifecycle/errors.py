"""Lifecycle service errors (epic E08).

Messages carry structural identifiers only (artifact ids, versions, element
ids) — never document content or values, per CLAUDE.md's logging rules.
"""

from __future__ import annotations

from domain.artifacts.errors import ValidationReport


class LifecycleError(Exception):
    """Base for every lifecycle service failure."""


class AdminScopeRequiredError(LifecycleError):
    """The caller lacks the admin scope required for this lifecycle mutation."""


class IncompatibleReleaseError(LifecycleError):
    """A mask in the release unit does not reference the unit's template
    version — an old mask never implicitly applies to an incompatible
    template version (rejected, not guessed)."""


class UnknownArtifactError(LifecycleError):
    """The release unit referenced a template or mask version that does not exist."""


class DraftValidationError(LifecycleError):
    """A mask failed referential/target-mapping validation at activation time."""

    def __init__(self, message: str, report: ValidationReport) -> None:
        super().__init__(message)
        self.report = report
