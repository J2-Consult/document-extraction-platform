"""InMemoryMetricsSink (epic E12): the fake `MetricsSink` used by every
recorder test in this package — records exactly what was emitted (name,
dimensions, value) so tests can assert metric name + dimensions from
real fixture-shaped inputs, per the epic's per-flow testing requirement."""

from __future__ import annotations

from ports.telemetry import MetricsSink
from services.telemetry.fake import InMemoryMetricsSink


def test_counter_call_is_recorded_with_name_dimensions_and_value() -> None:
    sink = InMemoryMetricsSink()

    sink.counter("routing.decisions_total", dimensions={"tenant": "t-1", "path": "fast_path"})
    sink.counter("routing.decisions_total", dimensions={"tenant": "t-1", "path": "full_analysis"}, value=3)

    assert len(sink.counters) == 2
    first, second = sink.counters
    assert first.name == "routing.decisions_total"
    assert first.dimensions == {"tenant": "t-1", "path": "fast_path"}
    assert first.value == 1
    assert second.value == 3


def test_histogram_call_is_recorded_with_name_dimensions_and_value() -> None:
    sink = InMemoryMetricsSink()

    sink.histogram("routing.latency_ms", 12.5, dimensions={"tenant": "t-1", "component_version": "fpv-1"})

    assert len(sink.histograms) == 1
    observation = sink.histograms[0]
    assert observation.name == "routing.latency_ms"
    assert observation.value == 12.5
    assert observation.dimensions == {"tenant": "t-1", "component_version": "fpv-1"}


def test_fake_sink_satisfies_the_metrics_sink_protocol() -> None:
    sink: MetricsSink = InMemoryMetricsSink()
    sink.counter("x", dimensions={})
    sink.histogram("y", 1.0, dimensions={})
    assert isinstance(sink, MetricsSink)


def test_all_dimension_values_helper_flattens_every_recorded_call_for_the_pii_regression_test() -> None:
    sink = InMemoryMetricsSink()
    sink.counter("a", dimensions={"tenant": "t-1", "state": "completed"})
    sink.histogram("b", 3.0, dimensions={"doc_class": "invoice"})

    assert set(sink.all_dimension_values()) == {"t-1", "completed", "invoice"}
