"""Extraction-pass ports (epic E05): one small Protocol per pass.

Interface segregation applied literally — six single-method protocols, no
god-interface. "VLM per region only" is enforced STRUCTURALLY:
`RegionalVlmFallback.read_region` accepts exactly one `Region`, and no
protocol in this module has a whole-page or whole-document model method.
The only methods that accept raw `pdf_bytes` are the deterministic
native-text pass and the per-page preprocessor (which must read the source
to render one page) — never a probabilistic pass.

Adding a new pass kind = a new Protocol here + a new registration entry in
`services.extraction.cascade.CascadeRegistration`, never an edit to an
existing protocol (open/closed).

Pure interfaces: no I/O here, no framework imports beyond the domain
vocabulary the passes exchange.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from domain.extraction import PageImage, PassOutput, Region


@runtime_checkable
class NativeTextPass(Protocol):
    """Deterministic native (born-digital) text extraction — never OCR,
    never a model call."""

    def extract_text(self, pdf_bytes: bytes) -> PassOutput: ...


@runtime_checkable
class PagePreprocessor(Protocol):
    """Renders ONE page of the source PDF into a working raster, recording
    the transform back to source space on the returned `PageImage`."""

    def preprocess(self, pdf_bytes: bytes, page: int) -> PageImage: ...


@runtime_checkable
class LayoutDetector(Protocol):
    """Detects candidate regions on one preprocessed page image."""

    def detect_regions(self, image: PageImage) -> PassOutput: ...


@runtime_checkable
class OcrPass(Protocol):
    """Recognizes text spans on one preprocessed page image."""

    def recognize_text(self, image: PageImage) -> PassOutput: ...


@runtime_checkable
class SpecializedDetector(Protocol):
    """Refines ONE detected region of a specific kind (table/kv/mark/
    signature/checkbox). Region-scoped by construction."""

    def detect(self, image: PageImage, region: Region) -> PassOutput: ...


@runtime_checkable
class RegionalVlmFallback(Protocol):
    """Reads ONE low-confidence region with a vision-language model. There is
    deliberately no whole-page/whole-document method: a caller CANNOT ask a
    VLM for more than one region at a time through this port."""

    def read_region(self, image: PageImage, region: Region, job_ref: str) -> PassOutput: ...
