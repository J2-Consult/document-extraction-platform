"""MetricsSink port (epic E12): counters and histograms with a bounded label set.

Telemetry is a leak channel (CLAUDE.md security section): every dimension
value emitted through this port MUST be an id, hash, state token, or number —
never document content or PII. This port is a pure sink interface and does
not itself enforce that; enforcement is a dedicated regression test
(`tests/unit/services/telemetry/test_no_pii_regression.py`) that scans every
dimension value emitted by every recorder in `services.telemetry.recorders`
against a forbidden-value list drawn from real fixture content.

Dimensions are a flat `Mapping[str, str]`. The epic's base dimension set is
`tenant`, `path`, `doc_class`, `component_version`; individual metrics add a
small number of metric-specific keys (e.g. `outcome`, `method`, `relation`)
documented next to their `record_*` helper in `services.telemetry.recorders`.
`path` follows the routing vocabulary (`fast_path` / `full_analysis`) where a
metric is routing-shaped; metrics with no natural "path" simply omit it.

Pure interface: no I/O here, no framework imports.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable


@runtime_checkable
class MetricsSink(Protocol):
    def counter(self, name: str, *, dimensions: Mapping[str, str], value: int = 1) -> None:
        """Increment the named counter by `value` (default 1), tagged with `dimensions`."""
        ...

    def histogram(self, name: str, value: float, *, dimensions: Mapping[str, str]) -> None:
        """Record one observation of `value` for the named histogram, tagged with `dimensions`."""
        ...
