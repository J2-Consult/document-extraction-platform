"""`OcrPass` adapter: deterministic OCR stand-in.

STUBBED: no real character recognition — the transcription is supplied at
construction, keyed by page (real OCR engines are provider-side).

REAL and load-bearing: the interface, the restamping of every span into the
working image's coordinate space and page, and the provenance stamping
(method='ocr', component version, the image's transform_to_source) — exactly
what a real OCR adapter must do with engine output.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from domain.extraction import PageImage, PassOutput, TextSpan

OCR_STUB_COMPONENT_VERSION = "ocr-stub/1.0.0"


class ScriptedOcrPass:
    def __init__(self, *, spans_by_page: Mapping[int, Sequence[TextSpan]]) -> None:
        self._spans_by_page = {page: tuple(spans) for page, spans in spans_by_page.items()}

    def recognize_text(self, image: PageImage) -> PassOutput:
        spans = tuple(
            span.model_copy(update={"coordinate_space": image.coordinate_space, "page": image.page})
            for span in self._spans_by_page.get(image.page, ())
        )
        return PassOutput(
            method="ocr",
            component_version=OCR_STUB_COMPONENT_VERSION,
            transform_to_source=list(image.transform_to_source),
            spans=spans,
        )
