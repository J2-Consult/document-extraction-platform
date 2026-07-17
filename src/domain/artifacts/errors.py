"""Itemized, machine-readable validation results.

`InvariantViolation`/`ValidationReport` are the InvariantValidator's output
shape (src/services/validation/). They carry structural identifiers only
(paths, codes, short messages) — never raw document content, per CLAUDE.md's
security rules.

Pure domain: no I/O, no framework imports.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class InvariantViolation(BaseModel):
    """One rejected invariant: a JSON-pointer-ish path, a kebab-case code, and
    a human-readable message that never quotes extracted document content."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    path: str = Field(min_length=1)
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)


class ValidationReport(BaseModel):
    """Result of running the InvariantValidator over one `ArtifactBundle`.

    Never raised — the validator always returns a report, valid or not.
    """

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    ok: bool
    violations: tuple[InvariantViolation, ...] = Field(default_factory=tuple)
