"""Unit tests for the routing benchmark harness. Fast, no network, no real
Postgres — the harness's ports are all in-memory/local pypdf-based, so this
runs the whole corpus (fixtures + generated decoys) inline.
"""

from __future__ import annotations

import json
from pathlib import Path

from benchmarks.routing.harness import build_corpus, run_benchmark, write_report


class _FixedClock:
    def __init__(self, epoch_seconds: float) -> None:
        self._epoch_seconds = epoch_seconds

    def now(self) -> float:
        return self._epoch_seconds


def test_build_corpus_includes_both_invoices_the_mbr_report_and_decoys() -> None:
    corpus = build_corpus()
    names = {item.name for item in corpus}
    assert "nv_invoice_20260042" in names
    assert "nv_invoice_20260043" in names
    assert "mbr_report_001" in names
    assert any(name.startswith("decoy_") for name in names)


def test_run_benchmark_has_zero_false_accepts_on_the_corpus() -> None:
    report = run_benchmark()

    assert report.false_accept_count == 0
    assert report.false_accept_rate == 0.0
    assert report.corpus_size == len(build_corpus())


def test_run_benchmark_has_zero_false_rejects_on_the_real_invoices() -> None:
    report = run_benchmark()

    assert report.false_reject_count == 0
    assert report.false_reject_rate == 0.0


def test_run_benchmark_candidate_hit_rate_and_latencies_are_well_formed() -> None:
    report = run_benchmark()

    assert 0.0 <= report.candidate_hit_rate <= 1.0
    assert report.latency_ms_p50 >= 0.0
    assert report.latency_ms_p95 >= report.latency_ms_p50
    for entry in report.items:
        assert entry["routed_to"] in {"fast_path", "full_analysis"}


def test_write_report_emits_json_and_markdown_with_required_fields(tmp_path: Path) -> None:
    report = run_benchmark()

    json_path, md_path = write_report(report, out_dir=tmp_path)

    assert json_path.exists()
    assert md_path.exists()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    for field in (
        "candidate_hit_rate",
        "false_accept_rate",
        "false_accept_count",
        "false_reject_rate",
        "false_reject_count",
        "latency_ms",
        "net_cost",
        "items",
    ):
        assert field in data
    assert set(data["latency_ms"]) == {"p50", "p95"}
    assert data["false_accept_count"] == 0
    md_text = md_path.read_text(encoding="utf-8").lower()
    assert "p50" in md_text or "latency" in md_text


def test_generated_at_is_stamped_from_the_injected_clock() -> None:
    """`generated_at` must come from the injected clock so a deliberate
    snapshot regeneration with unchanged inputs doesn't churn the timestamp
    (reviewer finding: tracked report artifacts must not vary per test run)."""
    report_a = run_benchmark(clock=_FixedClock(1784142688.0))
    report_b = run_benchmark(clock=_FixedClock(1784142688.0))

    assert report_a.generated_at == "2026-07-15T19:11:28+00:00"
    assert report_a.generated_at == report_b.generated_at
