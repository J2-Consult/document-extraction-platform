"""Benchmark harness: runs fixtures + generated decoys through
`CandidateRouter` and emits `benchmarks/routing/report.json` (+
`report.md`) with candidate-hit rate, false-accept/false-reject rates
(reported SEPARATELY), p50/p95 latency, and net cost vs full analysis.

Corpus ground truth:
  - `nv_invoice_20260042`/`nv_invoice_20260043`: real Nordvik invoices —
    SHOULD fast-path (`expect_fast_path=True`).
  - `decoy_*`: same page geometry, rotated labels (`decoys.py`) — get a
    candidate hit but MUST be rejected (`expect_fast_path=False`).
  - `mbr_report_001`: a different document class entirely — no candidate hit
    expected at all (`expect_fast_path=False`).

False-accept = a `expect_fast_path=False` item that routed to `fast_path`.
False-reject = a `expect_fast_path=True` item that did NOT route to
`fast_path`. The epic's definition of done requires false-accept = 0 on this
corpus.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from adapters.clock import SystemClock
from benchmarks.routing.cost_model import CostModel, cost_for_decision
from benchmarks.routing.decoys import generate_decoy_corpus
from domain.artifacts.template import TemplateArtifact
from ports.clock import Clock
from ports.routing_store import RoutingDecision, TemplateCandidate
from services.routing.factory import DEFAULT_COMPONENT_VERSIONS, build_default_router
from services.routing.memory import InMemoryRoutingDecisionStore, candidate_from_template_body

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_PDFS_DIR = REPO_ROOT / "fixtures" / "pdfs"
FIXTURES_ARTIFACTS_DIR = REPO_ROOT / "fixtures" / "artifacts"
REPORT_DIR = Path(__file__).resolve().parent

# Pinned `generated_at` for the checked-in snapshot (report.json/report.md).
# `main()` stamps deliberate regenerations with this constant so re-running
# the harness with unchanged inputs doesn't churn the timestamp; bump it when
# deliberately refreshing the snapshot after a real behavior change. Latency
# fields still vary run-to-run — accepted for explicit runs.
_SNAPSHOT_GENERATED_AT_EPOCH = 1784142688.0  # 2026-07-15T19:11:28+00:00 (first checked-in snapshot)


class _FixedClock:
    """`Clock` pinned to one instant (see `_SNAPSHOT_GENERATED_AT_EPOCH`)."""

    def __init__(self, epoch_seconds: float) -> None:
        self._epoch_seconds = epoch_seconds

    def now(self) -> float:
        return self._epoch_seconds


@dataclass(frozen=True)
class CorpusItem:
    name: str
    pdf_bytes: bytes
    expect_fast_path: bool


def _load_template_candidate() -> TemplateCandidate:
    data = json.loads((FIXTURES_ARTIFACTS_DIR / "tmpl_nvinv.v1.json").read_text(encoding="utf-8"))
    artifact = TemplateArtifact.model_validate(data)
    return candidate_from_template_body(artifact.body)


def build_corpus() -> list[CorpusItem]:
    items = [
        CorpusItem("nv_invoice_20260042", (FIXTURES_PDFS_DIR / "nv_invoice_20260042.pdf").read_bytes(), True),
        CorpusItem("nv_invoice_20260043", (FIXTURES_PDFS_DIR / "nv_invoice_20260043.pdf").read_bytes(), True),
        CorpusItem("mbr_report_001", (FIXTURES_PDFS_DIR / "mbr_report_001.pdf").read_bytes(), False),
    ]
    for name, pdf_bytes in generate_decoy_corpus().items():
        items.append(CorpusItem(name, pdf_bytes, False))
    return items


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = (len(ordered) - 1) * pct
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)


@dataclass(frozen=True)
class BenchmarkReport:
    generated_at: str
    corpus_size: int
    candidate_hit_rate: float
    false_accept_rate: float
    false_accept_count: int
    false_reject_rate: float
    false_reject_count: int
    latency_ms_p50: float
    latency_ms_p95: float
    net_cost: dict[str, float]
    items: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "corpus_size": self.corpus_size,
            "candidate_hit_rate": self.candidate_hit_rate,
            "false_accept_rate": self.false_accept_rate,
            "false_accept_count": self.false_accept_count,
            "false_reject_rate": self.false_reject_rate,
            "false_reject_count": self.false_reject_count,
            "latency_ms": {"p50": self.latency_ms_p50, "p95": self.latency_ms_p95},
            "net_cost": self.net_cost,
            "items": self.items,
        }


def _item_row(item: CorpusItem, decision: RoutingDecision) -> dict[str, Any]:
    return {
        "name": item.name,
        "expect_fast_path": item.expect_fast_path,
        "candidate_hit": decision.candidate is not None,
        "routed_to": decision.routed_to,
        "verification_status": decision.verification.status if decision.verification else None,
        "latency_ms": decision.latency_ms,
    }


def run_benchmark(cost_model: CostModel | None = None, *, clock: Clock | None = None) -> BenchmarkReport:
    """Run the corpus through the router and build the report.

    `clock` stamps `generated_at` only (per-item latency is measured by the
    router's own injected clock, independent of this one). Injectable so a
    deliberate snapshot regeneration with unchanged inputs doesn't churn the
    timestamp — `main()` pins it to `_SNAPSHOT_GENERATED_AT_EPOCH`; callers
    wanting a real wall-clock stamp pass `SystemClock()`.
    """
    generated_at_clock = clock if clock is not None else SystemClock()
    corpus = build_corpus()
    store = InMemoryRoutingDecisionStore()
    router = build_default_router(
        [_load_template_candidate()], store=store, component_versions=DEFAULT_COMPONENT_VERSIONS
    )
    cost_model = cost_model or CostModel()

    items: list[dict[str, Any]] = []
    candidate_hits = 0
    false_accepts = 0
    false_rejects = 0
    latencies: list[float] = []
    fast_path_cost = 0.0
    full_analysis_baseline_cost = 0.0

    for item in corpus:
        decision = router.route(item.pdf_bytes)
        latencies.append(decision.latency_ms)
        candidate_hits += int(decision.candidate is not None)
        accepted = decision.routed_to == "fast_path"
        if accepted and not item.expect_fast_path:
            false_accepts += 1
        if (not accepted) and item.expect_fast_path:
            false_rejects += 1
        fast_path_cost += cost_for_decision(decision, cost_model)
        full_analysis_baseline_cost += cost_model.full_analysis_cost
        items.append(_item_row(item, decision))

    corpus_size = len(corpus)
    negatives = sum(1 for item in corpus if not item.expect_fast_path)
    positives = corpus_size - negatives
    savings_fraction = (
        (full_analysis_baseline_cost - fast_path_cost) / full_analysis_baseline_cost
        if full_analysis_baseline_cost
        else 0.0
    )

    return BenchmarkReport(
        generated_at=datetime.fromtimestamp(generated_at_clock.now(), tz=UTC).isoformat(),
        corpus_size=corpus_size,
        candidate_hit_rate=candidate_hits / corpus_size,
        false_accept_rate=(false_accepts / negatives) if negatives else 0.0,
        false_accept_count=false_accepts,
        false_reject_rate=(false_rejects / positives) if positives else 0.0,
        false_reject_count=false_rejects,
        latency_ms_p50=_percentile(latencies, 0.50),
        latency_ms_p95=_percentile(latencies, 0.95),
        net_cost={
            "fast_path_total_cost_units": fast_path_cost,
            "full_analysis_baseline_cost_units": full_analysis_baseline_cost,
            "savings_fraction": savings_fraction,
        },
        items=items,
    )


def render_markdown(report: BenchmarkReport) -> str:
    lines = [
        "# E04 candidate-routing benchmark report",
        "",
        f"Generated: {report.generated_at}",
        "",
        "| metric | value |",
        "|---|---|",
        f"| corpus size | {report.corpus_size} |",
        f"| candidate-hit rate | {report.candidate_hit_rate:.2%} |",
        f"| false-accept rate | {report.false_accept_rate:.2%} ({report.false_accept_count}) |",
        f"| false-reject rate | {report.false_reject_rate:.2%} ({report.false_reject_count}) |",
        f"| latency p50 (ms) | {report.latency_ms_p50:.3f} |",
        f"| latency p95 (ms) | {report.latency_ms_p95:.3f} |",
        f"| net cost savings vs full analysis | {report.net_cost['savings_fraction']:.2%} |",
        "",
        "| item | expect fast_path | candidate hit | routed_to | verification | latency (ms) |",
        "|---|---|---|---|---|---|",
    ]
    for entry in report.items:
        lines.append(
            f"| {entry['name']} | {entry['expect_fast_path']} | {entry['candidate_hit']} | "
            f"{entry['routed_to']} | {entry['verification_status']} | {entry['latency_ms']:.3f} |"
        )
    return "\n".join(lines) + "\n"


def write_report(report: BenchmarkReport, out_dir: Path | None = None) -> tuple[Path, Path]:
    """Write report.json + report.md into `out_dir`.

    Defaulting `out_dir` to `REPORT_DIR` (this package, where the snapshot
    artifacts are git-tracked) is for DELIBERATE regeneration via `main()`
    only. Tests must always pass an explicit temporary `out_dir` — writing
    into the tracked directory from a test run dirties the working tree.
    """
    target_dir = out_dir or REPORT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    json_path = target_dir / "report.json"
    md_path = target_dir / "report.md"
    json_path.write_text(json.dumps(report.as_dict(), indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path


def main() -> int:
    report = run_benchmark(clock=_FixedClock(_SNAPSHOT_GENERATED_AT_EPOCH))
    json_path, md_path = write_report(report)
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    if report.false_accept_count != 0:
        print(f"FAIL: false_accept_count={report.false_accept_count} (must be 0)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
