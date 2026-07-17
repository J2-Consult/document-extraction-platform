"""`ArtifactBundle`: the pure-data input to every InvariantCheck.

Assembled by the caller (whichever service is validating an artifact) — the
bundle carries the artifact under validation plus whatever resolution context
(e.g. the referenced template) a check needs to do cross-artifact validation.
The validator and its checks do no I/O and never fetch context themselves.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from domain.artifacts.content import ContentArtifact
from domain.artifacts.errors import InvariantViolation
from domain.artifacts.mask import DecoderMaskArtifact
from domain.artifacts.template import TemplateArtifact


@dataclass(frozen=True, slots=True)
class ArtifactBundle:
    """One artifact under validation, plus optional resolution context.

    Exactly one of `template`/`content`/`mask` is typically the artifact under
    test; `template` may additionally be supplied as context when validating a
    `content` or `mask` artifact that references it (element resolution).
    """

    template: TemplateArtifact | None = None
    content: ContentArtifact | None = None
    mask: DecoderMaskArtifact | None = None


class InvariantCheck(Protocol):
    """One invariant (or tightly related group) evaluated over a bundle.

    Never raises; returns the violations found (empty if none). New invariant
    = new module implementing this protocol + registration in
    `validator.default_validator()` — existing checks are never edited
    (open/closed).
    """

    def check(self, bundle: ArtifactBundle) -> list[InvariantViolation]: ...
