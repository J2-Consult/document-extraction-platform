"""In-memory `JobQueue` adapter (epic E03).

Single-process reference implementation of the `JobQueue` port: the outbox
relay's default target in dev, and what the E03 test suite exercises for
idempotent enqueue, redelivery-is-a-no-op, bounded backoff, and DLQ behavior.
Not a distributed queue — a real deployment sits a durable backend (SQS,
Postgres-backed queue, ...) behind the same port; that adapter is future work
(disclosed in the E03 report, not part of this epic's scope).
"""

from __future__ import annotations

from uuid import uuid4

from ports.clock import Clock
from ports.jobs import Job, JobQueue, JobStatus  # noqa: F401 - JobQueue imported for the Protocol contract

DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_BASE_DELAY_SECONDS = 1.0
DEFAULT_BACKOFF_FACTOR = 2.0
DEFAULT_MAX_DELAY_SECONDS = 60.0


def bounded_backoff_seconds(
    attempt: int,
    *,
    base: float = DEFAULT_BASE_DELAY_SECONDS,
    factor: float = DEFAULT_BACKOFF_FACTOR,
    max_delay: float = DEFAULT_MAX_DELAY_SECONDS,
) -> float:
    """Exponential backoff (`base * factor**(attempt-1)`), capped at `max_delay`."""
    return min(base * (factor ** max(attempt - 1, 0)), max_delay)


class InMemoryJobQueue:
    """`JobQueue` backed by a plain dict; one process, no persistence."""

    def __init__(
        self,
        clock: Clock,
        *,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        base_delay_seconds: float = DEFAULT_BASE_DELAY_SECONDS,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
        max_delay_seconds: float = DEFAULT_MAX_DELAY_SECONDS,
    ) -> None:
        self._clock = clock
        self._max_attempts = max_attempts
        self._base_delay = base_delay_seconds
        self._factor = backoff_factor
        self._max_delay = max_delay_seconds
        self._jobs: dict[str, Job] = {}
        self._by_idempotency: dict[tuple[str, str], str] = {}

    def enqueue(self, *, tenant_id: str, kind: str, idempotency_key: str, payload: dict[str, object]) -> Job:
        existing_id = self._by_idempotency.get((tenant_id, idempotency_key))
        if existing_id is not None:
            return self._jobs[existing_id]
        job = Job(
            job_id=f"job_{uuid4().hex}",
            tenant_id=tenant_id,
            kind=kind,
            idempotency_key=idempotency_key,
            payload=dict(payload),
            status=JobStatus.QUEUED,
            attempts=0,
            max_attempts=self._max_attempts,
            deadline=self._clock.now(),
            terminal_reason=None,
        )
        self._jobs[job.job_id] = job
        self._by_idempotency[(tenant_id, idempotency_key)] = job.job_id
        return job

    def lease(self, *, kind: str) -> Job | None:
        now = self._clock.now()
        for job in self._jobs.values():
            if job.kind == kind and job.status == JobStatus.QUEUED and job.deadline <= now:
                leased = job.model_copy(update={"status": JobStatus.LEASED})
                self._jobs[job.job_id] = leased
                return leased
        return None

    def complete(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if job is None or job.status == JobStatus.COMPLETED:
            return
        self._jobs[job_id] = job.model_copy(update={"status": JobStatus.COMPLETED})

    def fail(self, job_id: str, *, reason: str) -> Job:
        job = self._jobs[job_id]
        attempts = job.attempts + 1
        if attempts >= job.max_attempts:
            updated = job.model_copy(
                update={"status": JobStatus.DEAD_LETTER, "attempts": attempts, "terminal_reason": reason}
            )
        else:
            delay = bounded_backoff_seconds(
                attempts, base=self._base_delay, factor=self._factor, max_delay=self._max_delay
            )
            updated = job.model_copy(
                update={
                    "status": JobStatus.QUEUED,
                    "attempts": attempts,
                    "deadline": self._clock.now() + delay,
                    "terminal_reason": None,
                }
            )
        self._jobs[job_id] = updated
        return updated

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)
