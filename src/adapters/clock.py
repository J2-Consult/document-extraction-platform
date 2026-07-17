"""SystemClock: the real `Clock` adapter (epic E03).

Deliberately tiny — a single wrapper around `time.time()` — so production
wiring has something to inject wherever a `Clock` is required, mirroring the
fake clock tests use to advance time deterministically. Not listed among the
epic's explicit adapter paths but a direct, minimal counterpart to
`ports/clock.py`; disclosed in the E03 report.
"""

from __future__ import annotations

import time


class SystemClock:
    def now(self) -> float:
        return time.time()
