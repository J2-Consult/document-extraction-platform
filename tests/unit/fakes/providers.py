"""Provider fakes/spies for E05 tests (reusable by later epics).

`ScriptedModelProvider` plays a queue of raw payloads or exceptions and
records every call — the spy proving what a provider was (and was not) sent.
`SlowModelProvider` answers after a real-time delay, for timeout tests.

Pure test doubles, never shipped.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence

from domain.extraction import PageImage, Region


def provider_payload(
    *,
    text: str | None = "extracted text",
    raw_confidence: float = 0.9,
    cost: float = 0.01,
    model_version: str = "fake-vlm/1",
) -> dict[str, object]:
    """A well-formed raw provider payload (`ProviderResponse`-shaped)."""
    return {"text": text, "raw_confidence": raw_confidence, "cost": cost, "model_version": model_version}


class ScriptedModelProvider:
    """`ModelProvider` spy: pops one scripted step per call. A step is either
    a raw payload mapping (returned) or an exception instance (raised)."""

    def __init__(self, script: Sequence[Mapping[str, object] | Exception]) -> None:
        self._script: list[Mapping[str, object] | Exception] = list(script)
        self.calls: list[tuple[PageImage, Region, str]] = []

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def read_region(self, image: PageImage, region: Region, job_ref: str) -> Mapping[str, object]:
        self.calls.append((image, region, job_ref))
        if not self._script:
            raise AssertionError("ScriptedModelProvider script exhausted — test scripted too few steps")
        step = self._script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


class SlowModelProvider:
    """`ModelProvider` that answers after a REAL wall-clock delay."""

    def __init__(self, *, delay_s: float, payload: Mapping[str, object] | None = None) -> None:
        self._delay_s = delay_s
        self._payload = dict(payload) if payload is not None else provider_payload()
        self.call_count = 0

    def read_region(self, image: PageImage, region: Region, job_ref: str) -> Mapping[str, object]:
        self.call_count += 1
        time.sleep(self._delay_s)
        return self._payload
