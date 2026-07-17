"""Per-tenant rate limiting (epic E03 security requirement)."""

from __future__ import annotations

from api.rate_limit import FixedWindowRateLimiter
from tests.unit.fakes.clock import FakeClock


def test_allows_up_to_max_requests_within_the_window() -> None:
    clock = FakeClock()
    limiter = FixedWindowRateLimiter(clock, max_requests=3, window_seconds=60)

    assert limiter.allow("t-1") is True
    assert limiter.allow("t-1") is True
    assert limiter.allow("t-1") is True
    assert limiter.allow("t-1") is False


def test_tenants_are_isolated() -> None:
    clock = FakeClock()
    limiter = FixedWindowRateLimiter(clock, max_requests=1, window_seconds=60)

    assert limiter.allow("t-1") is True
    assert limiter.allow("t-1") is False
    assert limiter.allow("t-2") is True  # a different tenant's limit is untouched


def test_a_new_window_resets_the_count() -> None:
    clock = FakeClock()
    limiter = FixedWindowRateLimiter(clock, max_requests=1, window_seconds=60)

    assert limiter.allow("t-1") is True
    assert limiter.allow("t-1") is False
    clock.advance(61)
    assert limiter.allow("t-1") is True
