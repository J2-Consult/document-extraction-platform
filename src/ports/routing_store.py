"""Routing-store ports: candidate lookup (read) and routing-decision
persistence (append-only) — epic E04.

Only in-memory implementations exist as of E04
(`src/services/routing/memory.py`); the Postgres adapter lands with E07's
query surface, not here.

DEVIATION from the architect draft (specs/design/E04-interfaces.md): the
draft has `TemplateCandidateIndex.find_by_key(...) -> Sequence[TemplateRef]`.
`TemplateVerifier.verify(...)` — specified in the same design doc — requires
the candidate's `TemplateBody`, and no template-body-fetch port exists yet
(E07 owns the real query surface). Rather than invent a second port for a
single-field lookup, `TemplateCandidate` below bundles `template_ref` +
`fingerprint_key` + `body`; `find_by_key` returns those. Flagged in the PR
description.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from domain.artifacts.template import TemplateBody, TemplateRef
from ports.verification import VerificationResult

RoutedTo = Literal["fast_path", "full_analysis"]


class TemplateCandidate(BaseModel):
    """A cheap-lookup hit: identity + enough body geometry to verify against.
    Never contextual/business meaning — that stays in masks, per CLAUDE.md."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    template_ref: TemplateRef
    fingerprint_key: str = Field(min_length=1)
    body: TemplateBody


class RoutingDecision(BaseModel):
    """Append-only routing-decision record: one per routed document.

    `candidate` and `verification` are both `None` when the candidate index
    returned zero hits (nothing to verify) — `routed_to` is `full_analysis`
    in that case too. `decided_at` uses the same epoch-seconds convention as
    `ports.clock.Clock.now()` (E03), which produced it.
    """

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    fpv_version: int = Field(ge=1)
    fingerprint_key: str = Field(min_length=1)
    candidate: TemplateRef | None
    verification: VerificationResult | None
    routed_to: RoutedTo
    latency_ms: float = Field(ge=0)
    component_versions: dict[str, str]
    decided_at: float


@runtime_checkable
class TemplateCandidateIndex(Protocol):
    def find_by_key(self, fingerprint_key: str) -> Sequence[TemplateCandidate]:
        """Look up candidates by fingerprint key. Empty sequence = no hit."""
        ...


@runtime_checkable
class RoutingDecisionStore(Protocol):
    def append(self, decision: RoutingDecision) -> None:
        """Persist one routing decision. Append-only: never mutates or
        deletes a previously stored decision (CLAUDE.md: never mutate a
        versioned/append-only record)."""
        ...
