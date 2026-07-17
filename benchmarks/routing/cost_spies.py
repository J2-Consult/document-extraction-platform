"""Tiny local provider Protocols + spies for proving the fast path avoids
expensive whole-document model calls (skeleton criterion 1).

E05 owns the REAL provider stack and extraction cascade. These are minimal,
private stand-ins scoped to `routing`/`benchmarks` so E05's real
implementations never collide with this epic's paths — they model just
enough of the cost/provider surface (full-layout call, whole-document VLM
call, regional call) to prove E04's routing contract: `fast_path` calls only
the regional provider (once per templated region); `full_analysis` calls the
full-layout and whole-document VLM providers.
"""

from __future__ import annotations

from typing import Protocol

BBox = tuple[float, float, float, float]


class FullLayoutProvider(Protocol):
    def analyze_layout(self, pdf_bytes: bytes) -> None: ...


class WholeDocumentVlmProvider(Protocol):
    def analyze_document(self, pdf_bytes: bytes) -> None: ...


class RegionalModelProvider(Protocol):
    def analyze_region(self, pdf_bytes: bytes, bbox: BBox) -> None: ...


class _CallSpy:
    def __init__(self) -> None:
        self.call_count = 0

    def _record(self) -> None:
        self.call_count += 1


class FullLayoutProviderSpy(_CallSpy):
    def analyze_layout(self, pdf_bytes: bytes) -> None:
        self._record()


class WholeDocumentVlmProviderSpy(_CallSpy):
    def analyze_document(self, pdf_bytes: bytes) -> None:
        self._record()


class RegionalModelProviderSpy(_CallSpy):
    def analyze_region(self, pdf_bytes: bytes, bbox: BBox) -> None:
        self._record()


def simulate_extraction_cascade(
    *,
    routed_to: str,
    pdf_bytes: bytes,
    regions: tuple[BBox, ...],
    full_layout: FullLayoutProviderSpy,
    whole_document_vlm: WholeDocumentVlmProviderSpy,
    regional: RegionalModelProviderSpy,
) -> None:
    """Stand-in for E05's extraction cascade, scoped to proving E04's routing
    contract holds: `fast_path` calls ONLY the regional provider (once per
    templated region, accounted separately from full-document calls);
    `full_analysis` calls full-layout + whole-document VLM. Not a real
    cost/cascade model — E05 replaces this wholesale.
    """
    if routed_to == "fast_path":
        for bbox in regions:
            regional.analyze_region(pdf_bytes, bbox)
        return
    full_layout.analyze_layout(pdf_bytes)
    whole_document_vlm.analyze_document(pdf_bytes)
