"""benchmarks.scorecard.runner (epic E12): targets loading + scorecard
evaluation + report rendering, tested against `tmp_path` only — the
checked-in benchmarks/scorecard/report.{json,md} snapshot is regenerated
exclusively by a deliberate `python -m benchmarks.scorecard.runner` run
(same discipline as benchmarks/routing/harness.py after its E04 review
finding), never by a test."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.scorecard.runner import (
    DEFAULT_TARGETS_PATH,
    NumericTarget,
    evaluate_scorecard,
    load_targets,
    render_markdown,
    write_report,
)

ALL_PASS_ACCEPTANCE = dict.fromkeys(range(1, 17), True)

_E04_REPORT_ALL_TARGETS_MET = {
    "candidate_hit_rate": 0.9,
    "false_accept_rate": 0.0,
    "false_reject_rate": 0.0,
    "latency_ms": {"p50": 2.0, "p95": 3.0},
    "net_cost": {"savings_fraction": 0.2},
}


def test_load_targets_returns_exactly_one_entry_per_skeleton_criterion() -> None:
    targets = load_targets(DEFAULT_TARGETS_PATH)

    assert len(targets) == 16
    assert [target.criterion for target in targets] == list(range(1, 17))
    for target in targets:
        assert target.name
        assert target.todo  # every entry carries an explicit TODO marker (epic DoD)


def test_load_targets_rejects_a_file_missing_a_criterion(tmp_path: Path) -> None:
    incomplete = tmp_path / "targets.json"
    incomplete.write_text(
        json.dumps(
            {
                "version": 1,
                "criteria": [
                    {"criterion": 1, "name": "x", "requires_acceptance_pass": True, "todo": "t"},
                ],
            }
        )
    )

    with pytest.raises(ValueError, match="16"):
        load_targets(incomplete)


def test_evaluate_scorecard_passes_when_acceptance_and_numeric_targets_are_all_met() -> None:
    targets = load_targets(DEFAULT_TARGETS_PATH)

    report = evaluate_scorecard(ALL_PASS_ACCEPTANCE, targets, benchmark_report=_E04_REPORT_ALL_TARGETS_MET)

    assert report.overall_pass is True
    assert len(report.criteria) == 16
    assert all(row.passed for row in report.criteria)


def test_evaluate_scorecard_fails_overall_when_one_acceptance_criterion_fails() -> None:
    targets = load_targets(DEFAULT_TARGETS_PATH)
    acceptance_results = dict(ALL_PASS_ACCEPTANCE)
    acceptance_results[9] = False

    report = evaluate_scorecard(acceptance_results, targets, benchmark_report=_E04_REPORT_ALL_TARGETS_MET)

    assert report.overall_pass is False
    failing = next(row for row in report.criteria if row.criterion == 9)
    assert failing.passed is False
    other = next(row for row in report.criteria if row.criterion == 1)
    assert other.passed is True


def test_tightening_one_numeric_target_flips_the_overall_pilot_verdict_to_fail() -> None:
    """Criterion 16's own required proof: tightening ANY one target flips the verdict."""
    targets = list(load_targets(DEFAULT_TARGETS_PATH))
    baseline = evaluate_scorecard(ALL_PASS_ACCEPTANCE, targets, benchmark_report=_E04_REPORT_ALL_TARGETS_MET)
    assert baseline.overall_pass is True

    criterion_3 = next(target for target in targets if target.criterion == 3)
    tightened_numeric_targets = tuple(
        NumericTarget(metric="candidate_hit_rate", comparator="gte", value=2.0, source="e04_benchmark_report")
        if numeric_target.metric == "candidate_hit_rate"
        else numeric_target
        for numeric_target in criterion_3.numeric_targets
    )
    tightened_criterion_3 = criterion_3.model_copy(update={"numeric_targets": tightened_numeric_targets})
    tightened_targets = [tightened_criterion_3 if t.criterion == 3 else t for t in targets]

    tightened_report = evaluate_scorecard(
        ALL_PASS_ACCEPTANCE, tightened_targets, benchmark_report=_E04_REPORT_ALL_TARGETS_MET
    )

    assert tightened_report.overall_pass is False
    flipped = next(row for row in tightened_report.criteria if row.criterion == 3)
    assert flipped.passed is False


def test_write_report_writes_json_and_markdown_with_all_16_rows_to_out_dir(tmp_path: Path) -> None:
    targets = load_targets(DEFAULT_TARGETS_PATH)
    report = evaluate_scorecard(ALL_PASS_ACCEPTANCE, targets, benchmark_report=_E04_REPORT_ALL_TARGETS_MET)

    json_path, md_path = write_report(report, out_dir=tmp_path)

    assert json_path.parent == tmp_path
    assert md_path.parent == tmp_path
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert len(data["criteria"]) == 16
    assert data["overall_pass"] is True
    markdown = md_path.read_text(encoding="utf-8")
    assert "16" in markdown
    assert "PASS" in markdown


def test_render_markdown_contains_a_row_per_criterion() -> None:
    targets = load_targets(DEFAULT_TARGETS_PATH)
    report = evaluate_scorecard(ALL_PASS_ACCEPTANCE, targets, benchmark_report=_E04_REPORT_ALL_TARGETS_MET)

    markdown = render_markdown(report)

    for criterion in range(1, 17):
        assert f"| {criterion} |" in markdown
