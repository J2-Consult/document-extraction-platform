"""Verification port: the gate between a cheap candidate hit and the fast
extraction path (epic E04).

`TemplateVerifier` implementations run bounded, discriminating checks (page
count/geometry, stable label anchors, major regions, table boundaries,
optional negative anchors) comparing a candidate template's body against the
actual PDF. `inconclusive` is NEVER force-matched: `VerificationResult`
carries a status the router can only read, never coerce — the router's fast
path is taken if and only if `status == "accepted"` (principle 5, CLAUDE.md).

Pure interface: no I/O here, no framework imports beyond the domain
vocabulary (`TemplateBody`) verification checks are expressed against.
"""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from domain.artifacts.template import TemplateBody
from ports.fingerprint import FingerprintFeatures

VerificationStatus = Literal["accepted", "rejected", "inconclusive"]


class VerificationCheck(BaseModel):
    """One bounded discriminating check's outcome.

    `passed is None` means the check could not be evaluated (e.g. it hit its
    own time budget, or a prerequisite was unparseable) — never treated as a
    pass; it is what pushes an otherwise-clean result to `inconclusive`
    rather than `accepted`.
    """

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    check_id: str = Field(min_length=1)
    passed: bool | None
    detail: str = Field(min_length=1)


class VerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    status: VerificationStatus
    checks: tuple[VerificationCheck, ...] = Field(default_factory=tuple)


@runtime_checkable
class TemplateVerifier(Protocol):
    def verify(self, features: FingerprintFeatures, pdf_bytes: bytes, candidate: TemplateBody) -> VerificationResult:
        """Run bounded discriminating checks against one candidate template.

        Implementations enforce their own hard per-check time budget; a
        check that cannot complete in time reports `passed=None`, not a
        default pass or fail.
        """
        ...
