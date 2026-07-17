"""Hard wall-clock timeout helper for feature extraction over hostile files.

The wrapped call runs inside a single-use worker thread; if it does not
finish within `timeout_s`, `run_bounded` raises `BoundedTimeoutError`
immediately without blocking the caller further.

CPython cannot forcibly kill another thread mid-computation, so a
pathological input can leave the worker thread running in the background
after the timeout fires — `run_bounded` does not wait for it
(`shutdown(wait=False)`). This is a documented limitation, not a full
sandbox: the actual hostile-file boundary is the sandboxed worker process
CLAUDE.md's security section describes; this helper assumes it is already
running inside that boundary and exists to bound one extraction call's
*wall-clock* contribution to that worker, not to contain arbitrary CPU/memory
abuse on its own.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import TypeVar

T = TypeVar("T")


class BoundedTimeoutError(TimeoutError):
    """Raised by `run_bounded` when the wrapped call exceeds its time budget."""


def run_bounded(fn: Callable[..., T], *args: object, timeout_s: float, **kwargs: object) -> T:
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(fn, *args, **kwargs)
        try:
            return future.result(timeout=timeout_s)
        except FutureTimeoutError as exc:
            raise BoundedTimeoutError(f"exceeded {timeout_s}s budget") from exc
    finally:
        executor.shutdown(wait=False)
