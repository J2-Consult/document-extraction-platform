"""Outbox relay (epic E03): drains committed outbox rows into the JobQueue,
replay-safely."""

from __future__ import annotations

from adapters.jobs.in_memory import InMemoryJobQueue
from services.ingestion.outbox_relay import OutboxRelay
from services.ingestion.service import IngestionService
from tests.unit.fakes.clock import FakeClock
from tests.unit.services.ingestion.fakes import InMemoryIngestionRepository, InMemoryObjectStore, SpyPdfSanitizer

PDF_BYTES = b"%PDF-1.7\n%...\n1 0 obj\n<< >>\nendobj\n%%EOF"
TENANT = "t-nordvik"


def test_relay_enqueues_pending_outbox_rows_and_marks_them_relayed() -> None:
    repo = InMemoryIngestionRepository()
    service = IngestionService(InMemoryObjectStore(), repo, SpyPdfSanitizer())
    service.ingest(tenant_id=TENANT, intent="extract", original_filename="invoice.pdf", data=PDF_BYTES)

    job_queue = InMemoryJobQueue(clock=FakeClock())
    relay = OutboxRelay(repo, job_queue)

    report = relay.relay_once(TENANT)

    assert len(report.relayed_outbox_ids) == 1
    assert job_queue.lease(kind="process_document") is not None
    assert repo.fetch_pending_outbox(TENANT) == ()  # marked relayed, not re-offered


def test_relaying_the_same_outbox_row_twice_does_not_duplicate_the_job() -> None:
    repo = InMemoryIngestionRepository()
    service = IngestionService(InMemoryObjectStore(), repo, SpyPdfSanitizer())
    service.ingest(tenant_id=TENANT, intent="extract", original_filename="invoice.pdf", data=PDF_BYTES)

    (entry,) = repo.fetch_pending_outbox(TENANT)
    job_queue = InMemoryJobQueue(clock=FakeClock())
    relay = OutboxRelay(repo, job_queue)

    relay.relay_once(TENANT)
    # Simulate the relay crashing after enqueue but before mark-relayed by
    # re-delivering the same row's payload directly: JobQueue.enqueue is
    # idempotent on (tenant_id, idempotency_key), so a repeat never creates a
    # second job.
    job_queue.enqueue(tenant_id=entry.tenant_id, kind=entry.job_kind, idempotency_key=entry.idempotency_key, payload={})

    leased_first = job_queue.lease(kind="process_document")
    assert leased_first is not None
    assert job_queue.lease(kind="process_document") is None  # still just the one job
