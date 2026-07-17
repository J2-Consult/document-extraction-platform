"""E00's own harness test: the acceptance-test backlog must exist and be
collectible before any epic can start unskipping criteria.

test_all_16_acceptance_scaffolds_are_collected_and_skipped — from E00's
"Tests first" list (specs/epics/E00-repo-bootstrap.md).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

ACCEPTANCE_DIR = Path(__file__).resolve().parent.parent / "acceptance"
EXPECTED_SCAFFOLD_COUNT = 16


class _ResultsCollector:
    """Minimal pytest plugin that records collected items."""

    def __init__(self) -> None:
        self.collected: list[Any] = []

    def pytest_collection_modifyitems(self, items: list[Any]) -> None:
        self.collected = list(items)


def test_all_16_acceptance_criteria_are_selected_under_acceptance_marker() -> None:
    """Collects (collect-only, no execution — acceptance tests may need a DB once
    epics unskip them) exactly the way `make test-acceptance` selects (`-m acceptance`)
    so a missing `acceptance` marker can never silently deselect the backlog:
    deselection would collect 0 items here and fail this gate. The skip-count
    assertion from E00's original scaffold state was dropped when epics began
    unskipping criteria; the invariant is 16 criteria selected, forever."""
    collector = _ResultsCollector()

    exit_code = pytest.main(
        [
            "-q",
            "--no-header",
            "--collect-only",
            "-p",
            "no:cacheprovider",
            "-m",
            "acceptance",
            str(ACCEPTANCE_DIR),
        ],
        plugins=[collector],
    )

    assert exit_code == pytest.ExitCode.OK
    selected = [item for item in collector.collected if item.get_closest_marker("acceptance")]
    assert len(selected) == EXPECTED_SCAFFOLD_COUNT, (
        f"expected {EXPECTED_SCAFFOLD_COUNT} criteria selected under -m acceptance, "
        f"got {len(selected)} (of {len(collector.collected)} collected) — "
        "did tests/acceptance lose its module-level acceptance pytestmark?"
    )

    for item in selected:
        epic_marker = item.get_closest_marker("epic")
        assert epic_marker is not None, f"{item.nodeid} is missing @pytest.mark.epic(...)"
        assert item.obj.__doc__, f"{item.nodeid} is missing a docstring quoting its criterion"
