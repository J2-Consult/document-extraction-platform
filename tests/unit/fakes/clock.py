"""FakeClock: a deterministic, manually-advanced `Clock` test double.

Shared by the JobQueue backoff tests and the ingestion-service tests — a pure
test double, never shipped.
"""

from __future__ import annotations


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def now(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds
