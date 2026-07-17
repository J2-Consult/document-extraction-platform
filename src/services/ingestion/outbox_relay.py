"""Outbox relay (epic E03): drain committed outbox rows into the JobQueue.

Transactional-outbox pattern: `IngestionService`/`IngestionRepository` never
call the `JobQueue` inside the DB transaction (the queue is a separate
system, so it cannot participate in the Postgres transaction's atomicity).
Instead the transaction writes an outbox row, and this relay — running
separately, any number of times — reads committed outbox rows and enqueues
them. Safe to run concurrently or re-run after a crash: `JobQueue.enqueue` is
itself idempotent on `(tenant_id, idempotency_key)`, so relaying the same row
twice (e.g. the relay dies after enqueueing but before marking the row
relayed) never creates a duplicate job.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ports.ingestion_repo import IngestionRepository
from ports.jobs import JobQueue

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RelayReport:
    tenant_id: str
    relayed_outbox_ids: tuple[str, ...]


class OutboxRelay:
    def __init__(self, repository: IngestionRepository, job_queue: JobQueue) -> None:
        self._repository = repository
        self._job_queue = job_queue

    def relay_once(self, tenant_id: str, *, limit: int = 100) -> RelayReport:
        pending = self._repository.fetch_pending_outbox(tenant_id, limit=limit)
        relayed_ids: list[str] = []
        for entry in pending:
            self._job_queue.enqueue(
                tenant_id=entry.tenant_id,
                kind=entry.job_kind,
                idempotency_key=entry.idempotency_key,
                payload=entry.payload,
            )
            self._repository.mark_outbox_relayed(entry.tenant_id, entry.outbox_id)
            relayed_ids.append(entry.outbox_id)
            logger.info("outbox row relayed", extra={"tenant_id": tenant_id, "outbox_id": entry.outbox_id})
        return RelayReport(tenant_id=tenant_id, relayed_outbox_ids=tuple(relayed_ids))
