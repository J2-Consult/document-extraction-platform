"""Pilot scorecard runner (epic E12): evaluates the walking-skeleton's 16
exit criteria (specs/SKELETON-CRITERIA.md — the §12.1-style table the
original v0.2 doc is absent, per that file's reconstruction note) against
`targets.json` and renders a pass/fail table + overall pilot verdict.

targets.json, not targets.yaml (epic-text filename): PyYAML is not a
pyproject.toml dependency (see `pip show pyyaml` — it's present in some
environments only as pre-commit's own transitive dependency, not something
this codebase can rely on). CLAUDE.md's "no new dependency without
justification" rule outranks the epic text's filename; JSON needs zero new
dependencies and the stdlib `json` module already anchors every other
artifact writer in this repo (`benchmarks/routing/harness.py`). Disclosed
per the epic's instruction to flag this choice.

Two things compose here, deliberately kept separate:
  - `evaluate_scorecard` / `write_report` / `render_markdown`: PURE functions
    over an already-computed `acceptance_results` mapping. Unit-tested with
    injected results (fast, no Postgres, no nested pytest).
  - `execute_acceptance_corpus`: the one function that actually drives
    `pytest tests/acceptance -m acceptance` in-process. It ALWAYS deselects
    criterion 16's own acceptance-test node
    (`CRITERION_16_TEST_NODEID`) — that test is this module's caller, and
    without the deselect it would recursively re-invoke itself. Criterion
    16's own pass/fail is therefore never "did re-running myself pass" but
    "did the runner execute the OTHER 15 criteria and render a complete,
    correctly-shaped table" — self-evidencing rather than self-invoking.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import pytest
from pydantic import BaseModel, ConfigDict, Field

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TARGETS_PATH = Path(__file__).resolve().parent / "targets.json"
SCORECARD_DIR = Path(__file__).resolve().parent
ACCEPTANCE_DIR = REPO_ROOT / "tests" / "acceptance"
E04_REPORT_PATH = REPO_ROOT / "benchmarks" / "routing" / "report.json"

EXPECTED_CRITERION_COUNT = 16
Comparator = Literal["gte", "lte"]

# Criterion number -> the acceptance test's function name, IN THE ORDER
# specs/SKELETON-CRITERIA.md lists them (tests/acceptance/test_skeleton_criteria.py
# mirrors that order 1:1). Hardcoded rather than inferred from collection
# order so a future reorder of the test file can't silently relabel criteria.
CRITERION_TEST_NAMES: dict[int, str] = {
    1: "test_fingerprint_routed_fast_path_skips_full_layout_and_whole_document_vlm_calls",
    2: "test_decoy_with_moved_labels_is_rejected_by_verification_gate_and_routed_to_full_analysis",
    3: "test_benchmark_harness_reports_candidate_hit_and_verification_rates_with_zero_false_accept",
    4: "test_tenant_a_cannot_access_tenant_b_data_under_restricted_roles_with_rls_enforced",
    5: "test_template_v2_registration_yields_lineage_and_auto_migrates_compatible_mask_entries",
    6: "test_release_unit_activates_atomically_and_v1_documents_remain_reproducible",
    7: "test_resolution_selects_customer_mask_and_pending_review_completes_after_human_correction",
    8: "test_confidently_blank_optional_field_recorded_as_empty_state_with_provenance",
    9: "test_every_observation_and_unmapped_content_note_carries_valid_provenance",
    10: "test_bbox_round_trip_through_preprocessing_transforms_lands_within_tolerance",
    11: "test_fixture_artifacts_validate_against_contracts_and_invariant_mutations_are_rejected",
    12: "test_document_values_projection_matches_json_artifacts_and_is_idempotent_without_cartesian_expansion",
    13: "test_orchestrator_answers_payment_terms_question_via_get_document_value_with_injection_inert",
    14: "test_replayed_upload_is_idempotent_and_masquerading_file_rejected_by_magic_bytes",
    15: "test_unmasked_document_gets_structural_embeddings_and_mask_activation_builds_semantic_set_async",
    16: "test_scorecard_runner_renders_pilot_exit_criteria_pass_fail_table",
}
CRITERION_16 = 16
CRITERION_16_TEST_NODEID = f"tests/acceptance/test_skeleton_criteria.py::{CRITERION_TEST_NAMES[CRITERION_16]}"


class NumericTarget(BaseModel):
    """One numeric check against a benchmark-report metric (currently only
    `benchmarks/routing/report.json`, the E04 artifact)."""

    # Not `strict=True` (unlike the domain/artifact models elsewhere in this
    # repo): these are config-file parsing shapes, not invariant-bearing
    # domain contracts, and pydantic's strict Python-mode validation rejects
    # a plain JSON-decoded `list` for a `tuple[...]` field. `extra="forbid"`
    # still catches typos in targets.json; `frozen=True` still makes
    # `.model_copy(update=...)` the only mutation path (used by the
    # tighten-one-target test).
    model_config = ConfigDict(extra="forbid", frozen=True)

    metric: str = Field(min_length=1)  # dotted path, e.g. "latency_ms.p95"
    comparator: Comparator
    value: float
    source: Literal["e04_benchmark_report"]
    todo: str = "client-agreed value"


class CriterionTarget(BaseModel):
    """One exit criterion's target: whether its acceptance test must pass,
    plus any additional numeric checks."""

    # Not `strict=True` (unlike the domain/artifact models elsewhere in this
    # repo): these are config-file parsing shapes, not invariant-bearing
    # domain contracts, and pydantic's strict Python-mode validation rejects
    # a plain JSON-decoded `list` for a `tuple[...]` field. `extra="forbid"`
    # still catches typos in targets.json; `frozen=True` still makes
    # `.model_copy(update=...)` the only mutation path (used by the
    # tighten-one-target test).
    model_config = ConfigDict(extra="forbid", frozen=True)

    criterion: int = Field(ge=1, le=EXPECTED_CRITERION_COUNT)
    name: str = Field(min_length=1)
    requires_acceptance_pass: bool
    numeric_targets: tuple[NumericTarget, ...] = ()
    todo: str = "client-agreed value"


def load_targets(path: Path) -> tuple[CriterionTarget, ...]:
    """Parse and validate `targets.json`: exactly one entry per criterion
    1..EXPECTED_CRITERION_COUNT, no duplicates, no gaps."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    targets = tuple(CriterionTarget.model_validate(entry) for entry in raw["criteria"])
    seen = sorted(target.criterion for target in targets)
    expected = list(range(1, EXPECTED_CRITERION_COUNT + 1))
    if seen != expected:
        raise ValueError(
            f"targets file must define exactly criteria 1..{EXPECTED_CRITERION_COUNT}, got {seen} ({path})"
        )
    return tuple(sorted(targets, key=lambda target: target.criterion))


def _lookup_metric(report: Mapping[str, Any], dotted_path: str) -> float:
    value: Any = report
    for part in dotted_path.split("."):
        if not isinstance(value, Mapping) or part not in value:
            raise KeyError(f"metric {dotted_path!r} not found in benchmark report")
        value = value[part]
    return float(value)


def _compare(actual: float, comparator: Comparator, target: float) -> bool:
    return actual >= target if comparator == "gte" else actual <= target


@dataclass(frozen=True, slots=True)
class CriterionResult:
    criterion: int
    name: str
    acceptance_passed: bool
    numeric_failures: tuple[str, ...]
    passed: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "criterion": self.criterion,
            "name": self.name,
            "acceptance_passed": self.acceptance_passed,
            "numeric_failures": list(self.numeric_failures),
            "passed": self.passed,
        }


@dataclass(frozen=True, slots=True)
class ScorecardReport:
    criteria: tuple[CriterionResult, ...]
    overall_pass: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "criteria": [row.as_dict() for row in self.criteria],
            "overall_pass": self.overall_pass,
        }


def _evaluate_one(
    target: CriterionTarget,
    acceptance_passed: bool,
    benchmark_report: Mapping[str, Any] | None,
) -> CriterionResult:
    numeric_failures: list[str] = []
    for check in target.numeric_targets:
        if benchmark_report is None:
            numeric_failures.append(f"{check.metric}: no benchmark report supplied")
            continue
        try:
            actual = _lookup_metric(benchmark_report, check.metric)
        except KeyError as exc:
            numeric_failures.append(str(exc))
            continue
        if not _compare(actual, check.comparator, check.value):
            numeric_failures.append(f"{check.metric}={actual} does not satisfy {check.comparator} {check.value}")
    acceptance_ok = acceptance_passed or not target.requires_acceptance_pass
    return CriterionResult(
        criterion=target.criterion,
        name=target.name,
        acceptance_passed=acceptance_passed,
        numeric_failures=tuple(numeric_failures),
        passed=acceptance_ok and not numeric_failures,
    )


def evaluate_scorecard(
    acceptance_results: Mapping[int, bool],
    targets: Sequence[CriterionTarget],
    *,
    benchmark_report: Mapping[str, Any] | None = None,
) -> ScorecardReport:
    """Pure evaluation: no pytest, no I/O. `acceptance_results` is
    criterion -> passed; `benchmark_report` is `benchmarks/routing/report.json`
    (or an injected stand-in for tests) used for criteria with
    `numeric_targets`."""
    rows = tuple(
        _evaluate_one(target, acceptance_results.get(target.criterion, False), benchmark_report) for target in targets
    )
    return ScorecardReport(criteria=rows, overall_pass=all(row.passed for row in rows))


def render_markdown(report: ScorecardReport) -> str:
    lines = [
        "# E12 pilot exit-criteria scorecard",
        "",
        f"Overall pilot verdict: **{'PASS' if report.overall_pass else 'FAIL'}**",
        "",
        "| criterion | name | acceptance | numeric failures | verdict |",
        "|---|---|---|---|---|",
    ]
    for row in report.criteria:
        failures = "; ".join(row.numeric_failures) if row.numeric_failures else "-"
        lines.append(
            f"| {row.criterion} | {row.name} | {'PASS' if row.acceptance_passed else 'FAIL'} | "
            f"{failures} | {'PASS' if row.passed else 'FAIL'} |"
        )
    return "\n".join(lines) + "\n"


def write_report(report: ScorecardReport, out_dir: Path | None = None) -> tuple[Path, Path]:
    """Write report.json + report.md into `out_dir`.

    Defaulting `out_dir` to `SCORECARD_DIR` (git-tracked) is for DELIBERATE
    regeneration via `main()` only — tests must always pass an explicit
    temporary `out_dir` (same discipline as `benchmarks/routing/harness.py`
    after its E04 review finding: a test must never dirty the working tree).
    """
    target_dir = out_dir or SCORECARD_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    json_path = target_dir / "report.json"
    md_path = target_dir / "report.md"
    json_path.write_text(json.dumps(report.as_dict(), indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path


def load_e04_benchmark_report(path: Path = E04_REPORT_PATH) -> dict[str, Any] | None:
    """`benchmarks/routing/report.json`, or None if it hasn't been generated
    yet (`python -m benchmarks.routing.harness`) — numeric_targets sourced
    from it then all fail closed via `_evaluate_one`'s "no benchmark report
    supplied" branch, never silently pass."""
    if not path.exists():
        return None
    return dict(json.loads(path.read_text(encoding="utf-8")))


class _OutcomeCollector:
    """Minimal pytest plugin recording each test's call-phase outcome,
    mirroring tests/unit/test_acceptance_scaffold_collection.py's collector."""

    def __init__(self) -> None:
        self.outcomes: dict[str, str] = {}

    def pytest_runtest_logreport(self, report: Any) -> None:
        if report.when == "call":
            self.outcomes[report.nodeid] = report.outcome


def execute_acceptance_corpus() -> dict[int, bool]:
    """Run every acceptance criterion EXCEPT criterion 16 (see module
    docstring for why) via an in-process pytest invocation, and return
    {criterion_number: passed}."""
    collector = _OutcomeCollector()
    pytest.main(
        [
            "-q",
            "--no-header",
            "-p",
            "no:cacheprovider",
            "-m",
            "acceptance",
            "--deselect",
            CRITERION_16_TEST_NODEID,
            str(ACCEPTANCE_DIR),
        ],
        plugins=[collector],
    )
    name_to_criterion = {name: criterion for criterion, name in CRITERION_TEST_NAMES.items()}
    results: dict[int, bool] = {}
    for nodeid, outcome in collector.outcomes.items():
        function_name = nodeid.split("::")[-1]
        criterion = name_to_criterion.get(function_name)
        if criterion is not None:
            results[criterion] = outcome == "passed"
    return results


def main() -> int:
    targets = load_targets(DEFAULT_TARGETS_PATH)
    acceptance_results = execute_acceptance_corpus()
    acceptance_results[CRITERION_16] = True  # this invocation's own successful completion IS criterion 16's proof
    benchmark_report = load_e04_benchmark_report()
    report = evaluate_scorecard(acceptance_results, targets, benchmark_report=benchmark_report)
    json_path, md_path = write_report(report)
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    print(f"pilot verdict: {'PASS' if report.overall_pass else 'FAIL'}")
    return 0 if report.overall_pass else 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
