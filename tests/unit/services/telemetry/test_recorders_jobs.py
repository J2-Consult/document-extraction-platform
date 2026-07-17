"""record_job_status + embedding-build recorders (epic E12): consume E03's
real `Job` (src/adapters/jobs/) — DLQ/backlog — and E11's `EmbeddingBuildService`
scheduling output (src/services/embedding/builds.py) — build backlog + switch
time."""

from __future__ import annotations

from adapters.jobs.in_memory import InMemoryJobQueue
from adapters.vectorindex.in_memory import HashEmbedder, InMemoryVectorIndex
from ports.jobs import JobStatus
from ports.vectorindex import EmbeddingSetKey
from services.embedding.builds import EmbeddingBuildService, RetentionPolicy
from services.telemetry.fake import InMemoryMetricsSink
from services.telemetry.metrics import EMBEDDING_BUILD_SCHEDULED_TOTAL, EMBEDDING_SWITCH_TIME_MS, JOBS_STATUS_TOTAL
from services.telemetry.recorders import (
    record_embedding_build_scheduled,
    record_embedding_build_switch,
    record_job_status,
)
from tests.unit.fakes.clock import FakeClock


def _build_service(clock: FakeClock) -> tuple[EmbeddingBuildService, InMemoryJobQueue]:
    jobs = InMemoryJobQueue(clock=clock)
    service = EmbeddingBuildService(
        index=InMemoryVectorIndex(),
        embedder=HashEmbedder(dimensions=4),
        jobs=jobs,
        clock=clock,
        retention=RetentionPolicy(keep_complete_sets=2),
        structural_window_tokens=8,
        structural_overlap_tokens=2,
    )
    return service, jobs


def test_embedding_build_scheduled_emits_backlog_and_generic_job_status_counters() -> None:
    clock = FakeClock()
    service, _jobs = _build_service(clock)
    key = EmbeddingSetKey(
        tenant_id="t-nordvik",
        document_id="doc-1",
        mask_id="mask_mbrvendor",
        mask_version=1,
        template_id="tmpl_mbr",
        template_version=1,
    )
    job = service.schedule_semantic_build(key)
    sink = InMemoryMetricsSink()

    record_embedding_build_scheduled(sink, job, doc_class="maintenance_report", component_version="e11-v1")

    scheduled = [c for c in sink.counters if c.name == EMBEDDING_BUILD_SCHEDULED_TOTAL]
    assert len(scheduled) == 1
    assert scheduled[0].dimensions["tenant"] == "t-nordvik"

    status = [c for c in sink.counters if c.name == JOBS_STATUS_TOTAL]
    assert len(status) == 1
    assert status[0].dimensions["status"] == JobStatus.QUEUED
    assert status[0].dimensions["kind"] == job.kind


def test_embedding_build_switch_emits_switch_time_histogram() -> None:
    sink = InMemoryMetricsSink()

    record_embedding_build_switch(
        sink, tenant_id="t-nordvik", doc_class="maintenance_report", component_version="e11-v1", switch_time_ms=42.0
    )

    switches = [h for h in sink.histograms if h.name == EMBEDDING_SWITCH_TIME_MS]
    assert len(switches) == 1
    assert switches[0].value == 42.0
    assert switches[0].dimensions["tenant"] == "t-nordvik"


def test_job_status_dead_letter_emits_terminal_status_dimension() -> None:
    clock = FakeClock()
    jobs = InMemoryJobQueue(clock=clock, max_attempts=1)
    job = jobs.enqueue(tenant_id="t-nordvik", kind="embedding_build", idempotency_key="k1", payload={})
    dead = jobs.fail(job.job_id, reason="adapter_timeout")
    assert dead.status == JobStatus.DEAD_LETTER  # sanity

    sink = InMemoryMetricsSink()
    record_job_status(sink, dead, doc_class="maintenance_report", component_version="e11-v1")

    status = [c for c in sink.counters if c.name == JOBS_STATUS_TOTAL]
    assert len(status) == 1
    assert status[0].dimensions["status"] == JobStatus.DEAD_LETTER
    assert status[0].dimensions["kind"] == "embedding_build"
