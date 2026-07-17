"""RateLimiter port + a minimal fixed-window adapter (epic E03).

Injected into the ingest route so `/ingest` can be rate-limited per tenant
(CLAUDE.md security: "Rate-limit the ingest endpoint per tenant"). A narrow,
route-specific port — like `PdfSanitizer`, nothing else in the platform
depends on it (yet), so it lives beside the route rather than in `src/ports/`.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ports.clock import Clock


@runtime_checkable
class RateLimiter(Protocol):
    def allow(self, tenant_id: str) -> bool:
        """True iff `tenant_id` may make another call right now."""
        ...


class FixedWindowRateLimiter:
    """Simple per-tenant fixed-window counter. Single-process only — a real
    deployment needs a shared backend (Redis, ...); that adapter is future
    work, out of this epic's scope."""

    def __init__(self, clock: Clock, *, max_requests: int, window_seconds: float) -> None:
        self._clock = clock
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._window_start: dict[str, float] = {}
        self._window_count: dict[str, int] = {}

    def allow(self, tenant_id: str) -> bool:
        now = self._clock.now()
        window_start = self._window_start.get(tenant_id)
        if window_start is None or now - window_start >= self._window_seconds:
            self._window_start[tenant_id] = now
            self._window_count[tenant_id] = 1
            return True
        if self._window_count[tenant_id] >= self._max_requests:
            return False
        self._window_count[tenant_id] += 1
        return True


class AllowAllRateLimiter:
    """No-op limiter for tests/dev wiring that don't care about limits."""

    def allow(self, tenant_id: str) -> bool:
        return True
