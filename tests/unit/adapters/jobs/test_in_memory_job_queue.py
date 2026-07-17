"""InMemoryJobQueue behavior (epic E03 "Tests first"):

- worker redelivery of a completed job is a no-op
- failed jobs land in DLQ with an itemized reason
- retries use bounded backoff, proven with a fake clock
"""

from __future__ import annotations

from adapters.jobs.in_memory import InMemoryJobQueue, bounded_backoff_seconds
from ports.jobs import JobStatus
from tests.unit.fakes.clock import FakeClock


def _queue(**kwargs: object) -> InMemoryJobQueue:
    return InMemoryJobQueue(clock=FakeClock(), **kwargs)  # type: ignore[arg-type]


def test_enqueue_same_idempotency_key_returns_the_same_job() -> None:
    queue = _queue()
    first = queue.enqueue(tenant_id="t-1", kind="process_document", idempotency_key="hash:extract", payload={})
    second = queue.enqueue(tenant_id="t-1", kind="process_document", idempotency_key="hash:extract", payload={})
    assert first.job_id == second.job_id


def test_lease_returns_a_queued_due_job_and_marks_it_leased() -> None:
    queue = _queue()
    created = queue.enqueue(tenant_id="t-1", kind="process_document", idempotency_key="k1", payload={})
    leased = queue.lease(kind="process_document")
    assert leased is not None
    assert leased.job_id == created.job_id
    assert leased.status == JobStatus.LEASED


def test_lease_does_not_return_the_same_job_twice() -> None:
    queue = _queue()
    queue.enqueue(tenant_id="t-1", kind="process_document", idempotency_key="k1", payload={})
    queue.lease(kind="process_document")
    assert queue.lease(kind="process_document") is None


def test_redelivery_of_a_completed_job_is_a_no_op() -> None:
    queue = _queue()
    job = queue.enqueue(tenant_id="t-1", kind="process_document", idempotency_key="k1", payload={})
    queue.lease(kind="process_document")
    queue.complete(job.job_id)
    queue.complete(job.job_id)  # redelivery: must not raise or change state
    assert queue.get(job.job_id).status == JobStatus.COMPLETED  # type: ignore[union-attr]


def test_complete_on_unknown_job_id_is_a_no_op() -> None:
    queue = _queue()
    queue.complete("job_does_not_exist")  # must not raise


def test_fail_reschedules_with_bounded_backoff_using_the_fake_clock() -> None:
    clock = FakeClock(start=100.0)
    queue = InMemoryJobQueue(clock=clock, max_attempts=5, base_delay_seconds=1.0, backoff_factor=2.0)
    job = queue.enqueue(tenant_id="t-1", kind="process_document", idempotency_key="k1", payload={})
    queue.lease(kind="process_document")

    failed = queue.fail(job.job_id, reason="extractor timeout")

    assert failed.status == JobStatus.QUEUED
    assert failed.attempts == 1
    assert failed.deadline == clock.now() + bounded_backoff_seconds(1, base=1.0, factor=2.0)
    # not due yet: leasing again before the clock advances past the deadline finds nothing
    assert queue.lease(kind="process_document") is None
    clock.advance(failed.deadline - clock.now())
    relea = queue.lease(kind="process_document")
    assert relea is not None
    assert relea.job_id == job.job_id


def test_fail_caps_backoff_delay_at_max_delay() -> None:
    delay = bounded_backoff_seconds(10, base=1.0, factor=2.0, max_delay=30.0)
    assert delay == 30.0


def test_fail_exhausting_max_attempts_lands_in_dlq_with_itemized_reason() -> None:
    clock = FakeClock()
    queue = InMemoryJobQueue(clock=clock, max_attempts=2, base_delay_seconds=0.1)
    job = queue.enqueue(tenant_id="t-1", kind="process_document", idempotency_key="k1", payload={})

    queue.lease(kind="process_document")
    first_failure = queue.fail(job.job_id, reason="transient error")
    assert first_failure.status == JobStatus.QUEUED

    clock.advance(first_failure.deadline - clock.now())
    queue.lease(kind="process_document")
    second_failure = queue.fail(job.job_id, reason="extractor crashed: OOM")

    assert second_failure.status == JobStatus.DEAD_LETTER
    assert second_failure.terminal_reason == "extractor crashed: OOM"
    assert queue.lease(kind="process_document") is None
