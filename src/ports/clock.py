"""Clock port: an injectable time source (epic E03, reused by E05).

Every scheduling decision that needs "now" (job backoff deadlines today,
extraction-cascade timeouts later) takes a `Clock` instead of calling
`time.time()` directly, so tests can advance time deterministically with a
fake instead of sleeping. Deliberately minimal — one method, one job.

Pure interface: no I/O here, no framework imports.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    def now(self) -> float:
        """Current time as epoch seconds. Used for scheduling/ordering only —
        never for display formatting, so sub-second precision and timezone
        are the implementation's concern, not the contract's."""
        ...
