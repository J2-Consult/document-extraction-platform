"""`GuardedProvider`: the only sanctioned wrapper around a raw `ModelProvider`.

Guards, in order, before any network attempt:
  1. circuit breaker — opens after N CONSECUTIVE failures, refuses while
     cooling down, half-opens after `cooldown_s` (one trial call: success
     closes, failure re-opens for a full cooldown). Time comes from the
     injected `Clock`, so tests drive it with a fake.
  2. per-tenant cost cap — spend at/over the cap refuses the call with an
     ITEMIZED `CostCapExceeded` (tenant, cap, totals, per-category), so the
     job that dies on cost dies loudly.
  3. rate limit — sliding-window client-side limit; refusals never count as
     provider failures.

The call itself is bounded by a REAL wall-clock timeout (a fake clock cannot
interrupt a hung socket), and the response is treated as UNTRUSTED DATA:
schema-validated into `ProviderResponse` (`extra="forbid"`), with the model's
version claim stamped under this wrapper's own component version.

Payload hygiene: the wrapped call receives page image + one region + the
opaque `job_ref` — the tenant id held here is used for accounting ONLY and
is never part of the provider payload. Nothing derived from document content
is logged; failures carry type names and counters, not text.

Provider credentials are the transport adapter's concern and come from the
environment there — never constructor arguments here, never logged.
"""

from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from enum import Enum

from pydantic import ValidationError

from domain.extraction import PageImage, Region
from ports.clock import Clock
from ports.cost import COST_CATEGORIES, CostCapExceeded, CostCategory, CostLedger
from ports.providers import (
    CircuitOpenError,
    InvalidProviderResponseError,
    ModelProvider,
    ProviderCallError,
    ProviderResponse,
    ProviderTimeoutError,
    RateLimitExceededError,
)

GUARDED_PROVIDER_COMPONENT_VERSION = "guarded-provider/1.0.0"


@dataclass(frozen=True)
class GuardedProviderConfig:
    cost_cap: float
    timeout_s: float = 30.0
    failure_threshold: int = 5
    cooldown_s: float = 30.0
    rate_limit_calls: int = 10
    rate_limit_window_s: float = 1.0
    cost_category: CostCategory = "regional_model"

    def __post_init__(self) -> None:
        if self.cost_cap <= 0 or self.timeout_s <= 0 or self.cooldown_s <= 0:
            raise ValueError("cost_cap, timeout_s, and cooldown_s must all be positive")
        if self.failure_threshold < 1 or self.rate_limit_calls < 1 or self.rate_limit_window_s <= 0:
            raise ValueError("failure_threshold, rate_limit_calls, and rate_limit_window_s must be positive")


class _CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class GuardedProvider:
    """`ValidatedModelProvider` built from a raw `ModelProvider` plus guards."""

    def __init__(
        self,
        inner: ModelProvider,
        *,
        tenant_id: str,
        clock: Clock,
        ledger: CostLedger,
        config: GuardedProviderConfig,
    ) -> None:
        if not tenant_id:
            raise ValueError("tenant_id must be non-empty")
        self._inner = inner
        self._tenant_id = tenant_id
        self._clock = clock
        self._ledger = ledger
        self._config = config
        self._state = _CircuitState.CLOSED
        self._consecutive_failures = 0
        self._opened_at = 0.0
        self._call_times: deque[float] = deque()

    @property
    def component_version(self) -> str:
        return GUARDED_PROVIDER_COMPONENT_VERSION

    def read_region(self, image: PageImage, region: Region, job_ref: str) -> ProviderResponse:
        self._check_circuit()
        self._check_cost_cap()
        self._check_rate_limit()
        raw = self._attempt_call(image, region, job_ref)
        response = self._validate(raw)
        self._ledger.record(self._tenant_id, self._config.cost_category, response.cost)
        self._record_success()
        return response.model_copy(
            update={"model_version": f"{GUARDED_PROVIDER_COMPONENT_VERSION}+{response.model_version}"}
        )

    # -- guards ------------------------------------------------------------

    def _check_circuit(self) -> None:
        if self._state is not _CircuitState.OPEN:
            return
        if self._clock.now() - self._opened_at < self._config.cooldown_s:
            raise CircuitOpenError(f"circuit open; retry after cooldown of {self._config.cooldown_s}s")
        self._state = _CircuitState.HALF_OPEN  # cooled down: allow ONE trial call

    def _check_cost_cap(self) -> None:
        spent_total = self._ledger.spent(self._tenant_id)
        if spent_total < self._config.cost_cap:
            return
        raise CostCapExceeded(
            tenant_id=self._tenant_id,
            cap=self._config.cost_cap,
            spent_total=spent_total,
            spent_by_category={
                category: spend
                for category in COST_CATEGORIES
                if (spend := self._ledger.spent_in_category(self._tenant_id, category)) > 0
            },
            attempted_category=self._config.cost_category,
        )

    def _check_rate_limit(self) -> None:
        now = self._clock.now()
        window_start = now - self._config.rate_limit_window_s
        while self._call_times and self._call_times[0] <= window_start:
            self._call_times.popleft()
        if len(self._call_times) >= self._config.rate_limit_calls:
            raise RateLimitExceededError(
                f"client-side rate limit: {self._config.rate_limit_calls} calls per "
                f"{self._config.rate_limit_window_s}s window"
            )
        self._call_times.append(now)

    # -- the call ----------------------------------------------------------

    def _attempt_call(self, image: PageImage, region: Region, job_ref: str) -> object:
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(self._inner.read_region, image, region, job_ref)
            try:
                return future.result(timeout=self._config.timeout_s)
            except FutureTimeoutError as exc:
                self._record_failure()
                raise ProviderTimeoutError(f"provider call exceeded {self._config.timeout_s}s budget") from exc
            except Exception as exc:  # noqa: BLE001 - any inner failure becomes a typed, counted error
                self._record_failure()
                raise ProviderCallError(f"provider call failed: {type(exc).__name__}") from exc
        finally:
            executor.shutdown(wait=False)

    def _validate(self, raw: object) -> ProviderResponse:
        try:
            return ProviderResponse.model_validate(raw)
        except ValidationError as exc:
            self._record_failure()
            raise InvalidProviderResponseError(
                f"provider response failed schema validation ({exc.error_count()} errors)"
            ) from exc

    # -- breaker bookkeeping -------------------------------------------------

    def _record_success(self) -> None:
        self._state = _CircuitState.CLOSED
        self._consecutive_failures = 0

    def _record_failure(self) -> None:
        if self._state is _CircuitState.HALF_OPEN:
            self._open_circuit()
            return
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._config.failure_threshold:
            self._open_circuit()

    def _open_circuit(self) -> None:
        self._state = _CircuitState.OPEN
        self._consecutive_failures = 0
        self._opened_at = self._clock.now()
