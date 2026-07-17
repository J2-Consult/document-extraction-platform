"""Pass spies for E05 cascade tests (reusable by later epics).

Each spy wraps a real port implementation and records what it was asked —
the proof mechanism for "OCR never invoked on born-digital" and "VLM called
only for the one low-confidence region, never whole pages".

Pure test doubles, never shipped.
"""

from __future__ import annotations

from domain.extraction import PageImage, PassOutput, Region
from ports.extraction_passes import (
    NativeTextPass,
    OcrPass,
    PagePreprocessor,
    RegionalVlmFallback,
    SpecializedDetector,
)


class ScriptedNativeTextPass:
    """`NativeTextPass` returning a canned output — for scripting degraded or
    empty text layers without crafting PDFs."""

    def __init__(self, output: PassOutput) -> None:
        self._output = output
        self.call_count = 0

    def extract_text(self, pdf_bytes: bytes) -> PassOutput:
        self.call_count += 1
        return self._output


class RecordingPreprocessor:
    def __init__(self, inner: PagePreprocessor) -> None:
        self._inner = inner
        self.pages_preprocessed: list[int] = []

    @property
    def call_count(self) -> int:
        return len(self.pages_preprocessed)

    def preprocess(self, pdf_bytes: bytes, page: int) -> PageImage:
        self.pages_preprocessed.append(page)
        return self._inner.preprocess(pdf_bytes, page)


class RecordingOcrPass:
    def __init__(self, inner: OcrPass) -> None:
        self._inner = inner
        self.pages_recognized: list[int] = []

    @property
    def call_count(self) -> int:
        return len(self.pages_recognized)

    def recognize_text(self, image: PageImage) -> PassOutput:
        self.pages_recognized.append(image.page)
        return self._inner.recognize_text(image)


class RecordingSpecializedDetector:
    def __init__(self, inner: SpecializedDetector) -> None:
        self._inner = inner
        self.regions_detected: list[Region] = []

    @property
    def call_count(self) -> int:
        return len(self.regions_detected)

    def detect(self, image: PageImage, region: Region) -> PassOutput:
        self.regions_detected.append(region)
        return self._inner.detect(image, region)


class RecordingVlmFallback:
    def __init__(self, inner: RegionalVlmFallback) -> None:
        self._inner = inner
        self.calls: list[tuple[PageImage, Region, str]] = []

    @property
    def call_count(self) -> int:
        return len(self.calls)

    @property
    def regions_read(self) -> list[Region]:
        return [region for _, region, _ in self.calls]

    def read_region(self, image: PageImage, region: Region, job_ref: str) -> PassOutput:
        self.calls.append((image, region, job_ref))
        return self._inner.read_region(image, region, job_ref)


class NeverCalledVlmFallback:
    """`RegionalVlmFallback` that fails the test if it is ever reached."""

    def __init__(self) -> None:
        self.call_count = 0

    def read_region(self, image: PageImage, region: Region, job_ref: str) -> PassOutput:
        self.call_count += 1
        raise AssertionError("VLM fallback must not be invoked in this scenario")


# Protocol conformance guards: a drifted fake fails HERE, not deep in a test.
def _static_protocol_checks(
    native: NativeTextPass,
    preprocessor: PagePreprocessor,
    ocr: OcrPass,
    detector: SpecializedDetector,
    vlm: RegionalVlmFallback,
) -> None:  # pragma: no cover - typing-time only
    del native, preprocessor, ocr, detector, vlm
