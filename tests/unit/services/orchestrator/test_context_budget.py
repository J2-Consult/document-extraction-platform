"""E10 token budget: assembled context is measured with an injected estimator;
over budget => REFUSE-AND-REFINE (narrower query or per-section summary),
NEVER widen; the context never exceeds the configured ceiling (property test
with oversized sections).
"""

from __future__ import annotations

import random

from services.orchestrator.context import (
    NARROWING_REFINEMENTS,
    AssembledContext,
    BudgetRefusal,
    LenTokenEstimator,
    assemble_context,
)
from services.orchestrator.prompt import ContextFragment

INSTRUCTIONS = "Answer using only the retrieved data blocks."


def _fragment(source_id: str, size: int) -> ContextFragment:
    return ContextFragment(source_id=source_id, text="x" * size, provenance=None)


def test_len_estimator_rounds_chars_up_to_tokens() -> None:
    estimator = LenTokenEstimator()

    assert estimator.estimate("") == 0
    assert estimator.estimate("abcd") == 1
    assert estimator.estimate("abcde") == 2


def test_under_budget_context_assembles_with_estimate_and_fragment_ids() -> None:
    result = assemble_context(
        INSTRUCTIONS,
        (_fragment("doc/1.1", 40),),
        estimator=LenTokenEstimator(),
        budget=500,
    )

    assert isinstance(result, AssembledContext)
    assert result.fragment_ids == ("doc/1.1",)
    assert 0 < result.token_estimate <= 500
    assert "x" * 40 in result.prompt


def test_over_budget_refuses_with_narrowing_refinements_only() -> None:
    result = assemble_context(
        INSTRUCTIONS,
        (_fragment("doc/1.1", 10_000),),
        estimator=LenTokenEstimator(),
        budget=100,
    )

    assert isinstance(result, BudgetRefusal)
    assert result.budget == 100
    assert result.token_estimate > 100
    assert result.refinements, "a refusal must propose a refinement path"
    assert set(result.refinements) <= set(NARROWING_REFINEMENTS)
    assert all("widen" not in refinement for refinement in result.refinements)
    assert not hasattr(result, "prompt"), "a refusal carries no assembled context"


def test_measurement_covers_the_whole_assembled_context_not_just_the_data() -> None:
    """Markers, rule line, and citations count against the budget too: a
    budget big enough for the raw text alone but not the assembled prompt
    must refuse."""
    fragment = _fragment("doc/1.1", 80)
    raw_tokens = LenTokenEstimator().estimate(fragment.text)

    result = assemble_context(INSTRUCTIONS, (fragment,), estimator=LenTokenEstimator(), budget=raw_tokens)

    assert isinstance(result, BudgetRefusal)


def test_injected_estimator_is_honored() -> None:
    class WordCountEstimator:
        def estimate(self, text: str) -> int:
            return len(text.split())

    result = assemble_context(
        INSTRUCTIONS,
        (_fragment("doc/1.1", 4),),
        estimator=WordCountEstimator(),
        budget=10_000,
    )

    assert isinstance(result, AssembledContext)
    assert result.token_estimate == len(result.prompt.split())


def test_context_never_exceeds_the_configured_ceiling_property() -> None:
    """Property: for ANY mix of fragments — including grossly oversized
    sections — the outcome is either a refusal or an assembled context whose
    measured size is within the ceiling. There is no third state."""
    rng = random.Random(20260716)
    estimator = LenTokenEstimator()
    assembled_count = 0
    refused_count = 0

    for case in range(300):
        budget = rng.randint(1, 400)
        fragments = tuple(
            _fragment(f"doc_{case}/{index}", rng.choice([1, 10, 100, 5_000, 50_000]))
            for index in range(rng.randint(1, 6))
        )

        result = assemble_context(INSTRUCTIONS, fragments, estimator=estimator, budget=budget)

        if isinstance(result, AssembledContext):
            assembled_count += 1
            assert result.token_estimate <= budget
            assert estimator.estimate(result.prompt) <= budget, "assembled context exceeded the ceiling"
        else:
            refused_count += 1
            assert isinstance(result, BudgetRefusal)
            assert result.token_estimate > budget
            assert set(result.refinements) <= set(NARROWING_REFINEMENTS)

    assert refused_count > 0, "the property run must exercise the refuse path"
