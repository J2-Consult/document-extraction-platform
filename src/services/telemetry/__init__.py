"""Telemetry application services (epic E12): typed metric definitions, thin
per-flow recorder utilities, and the in-memory fake `MetricsSink` used across
this package's tests.

Recorders here NEVER edit another epic's service internals — each one
consumes that epic's existing result/domain objects (`RoutingDecision`,
`MappingResult`, `DraftMigration`, `HeldDocument`, `Job`, ...) and turns them
into `MetricsSink.counter`/`histogram` calls. See `services.telemetry.metrics`
for the emitted metric name constants and `services.telemetry.recorders` for
the `record_*` functions themselves.
"""

from __future__ import annotations
