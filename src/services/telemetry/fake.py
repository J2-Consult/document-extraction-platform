"""`InMemoryMetricsSink`: a pure test double for `ports.telemetry.MetricsSink`.

Never shipped — used by every recorder test in this package (fake-sink
assertions per flow) and by the no-PII regression test, which scans
`all_dimension_values()` across every recorder invocation in the suite.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class RecordedCounter:
    name: str
    dimensions: Mapping[str, str]
    value: int


@dataclass(frozen=True, slots=True)
class RecordedHistogram:
    name: str
    value: float
    dimensions: Mapping[str, str]


@dataclass(slots=True)
class InMemoryMetricsSink:
    """Records every `counter`/`histogram` call verbatim, in call order."""

    counters: list[RecordedCounter] = field(default_factory=list)
    histograms: list[RecordedHistogram] = field(default_factory=list)

    def counter(self, name: str, *, dimensions: Mapping[str, str], value: int = 1) -> None:
        self.counters.append(RecordedCounter(name=name, dimensions=dict(dimensions), value=value))

    def histogram(self, name: str, value: float, *, dimensions: Mapping[str, str]) -> None:
        self.histograms.append(RecordedHistogram(name=name, value=value, dimensions=dict(dimensions)))

    def all_dimension_values(self) -> list[str]:
        """Every dimension VALUE emitted so far, across counters and histograms —
        the exact surface the no-PII regression test scans."""
        values: list[str] = []
        for counter in self.counters:
            values.extend(counter.dimensions.values())
        for histogram in self.histograms:
            values.extend(histogram.dimensions.values())
        return values
