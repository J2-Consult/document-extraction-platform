"""JobQueue port + Job model (epic E03).

A `Job` is the processing unit created alongside a registered document
(`IngestionRepository.register_upload`) and later relayed from the outbox to
a `JobQueue` implementation for a worker to lease. The model carries exactly
what v0.2 SS10.1 requires: an idempotency key (so redelivery/replay never
double-processes), an attempt counter with a bounded max, a `deadline` (the
earliest time the job is eligible for the next lease — used for backoff
scheduling), a dead-letter terminal state, and an itemized `terminal_reason`.

Pure interface + data shape: no I/O here, no framework imports.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class JobStatus(StrEnum):
    QUEUED = "queued"
    LEASED = "leased"
    COMPLETED = "completed"
    DEAD_LETTER = "dead_letter"


class Job(BaseModel):
    """One unit of asynchronous work, keyed for exactly-once processing."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    job_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    payload: dict[str, object] = Field(default_factory=dict)
    status: JobStatus = JobStatus.QUEUED
    attempts: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=5, ge=1)
    deadline: float = Field(default=0.0, description="Epoch seconds; not eligible for lease before this.")
    terminal_reason: str | None = None


@runtime_checkable
class JobQueue(Protocol):
    def enqueue(
        self,
        *,
        tenant_id: str,
        kind: str,
        idempotency_key: str,
        payload: dict[str, object],
    ) -> Job:
        """Create (or, if `(tenant_id, idempotency_key)` already exists, return
        unchanged) the job. Idempotent by construction — replaying the same
        outbox row never creates a second job."""
        ...

    def lease(self, *, kind: str) -> Job | None:
        """Return the next due QUEUED job of `kind` (`deadline` already elapsed),
        transitioning it to LEASED. None if no job is due."""
        ...

    def complete(self, job_id: str) -> None:
        """Mark `job_id` COMPLETED. Idempotent: completing an already-completed
        (or unknown) job is a no-op — worker redelivery of a finished job must
        never raise or re-run side effects."""
        ...

    def fail(self, job_id: str, *, reason: str) -> Job:
        """Record a failed attempt. Reschedules with bounded backoff while
        attempts remain; on exhausting `max_attempts` transitions to
        DEAD_LETTER with `terminal_reason=reason` (itemized, never generic)."""
        ...

    def get(self, job_id: str) -> Job | None:
        """Look up a job by id, or None if it does not exist."""
        ...
