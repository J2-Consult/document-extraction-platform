"""Token-budgeted context assembly (epic E10): refuse-and-refine, never widen.

The WHOLE assembled context (instructions, rule line, citations, markers,
data) is measured with an injected `TokenEstimator`; if the measure exceeds
the configured budget the orchestrator returns a `BudgetRefusal` proposing
only NARROWING refinements (a narrower query, or a per-section summary
request) — it never widens the retrieval, and it never returns a context
above the ceiling. There is no third state (property-tested).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from services.orchestrator.prompt import ContextFragment, assemble_prompt

REFINE_NARROW_QUERY = "narrow_query"
REFINE_SECTION_SUMMARY = "request_section_summary"
#: The complete refinement vocabulary — narrowing only, by construction.
NARROWING_REFINEMENTS: tuple[str, ...] = (REFINE_NARROW_QUERY, REFINE_SECTION_SUMMARY)


@runtime_checkable
class TokenEstimator(Protocol):
    """Measures assembled context size in tokens (injected, swappable)."""

    def estimate(self, text: str) -> int: ...


@dataclass(frozen=True, slots=True)
class LenTokenEstimator:
    """Simple length-based estimate: ceil(len(text) / chars_per_token)."""

    chars_per_token: int = 4

    def estimate(self, text: str) -> int:
        return -(-len(text) // self.chars_per_token)


@dataclass(frozen=True, slots=True)
class AssembledContext:
    """A within-budget context ready to serve; carries its own measure."""

    prompt: str
    token_estimate: int
    fragment_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BudgetRefusal:
    """Over budget: no context is produced; the caller must refine, never widen."""

    token_estimate: int
    budget: int
    refinements: tuple[str, ...]


def assemble_context(
    instructions: str,
    fragments: Sequence[ContextFragment],
    *,
    estimator: TokenEstimator,
    budget: int,
) -> AssembledContext | BudgetRefusal:
    """Assemble and measure; over budget => refuse-and-refine (never widen)."""
    if budget < 1:
        raise ValueError(f"token budget must be positive, got {budget}")
    prompt = assemble_prompt(instructions, fragments)
    token_estimate = estimator.estimate(prompt)
    if token_estimate > budget:
        return BudgetRefusal(token_estimate=token_estimate, budget=budget, refinements=NARROWING_REFINEMENTS)
    return AssembledContext(
        prompt=prompt,
        token_estimate=token_estimate,
        fragment_ids=tuple(fragment.source_id for fragment in fragments),
    )
