"""TemplateAssembler (epic E05): a draft `TemplateBody` from cascade output.

Structure only, NO business meaning: label/value span pairs become anchored
`value_region` elements (what a mask later gives meaning to is not recorded
here). Spans from working-space passes (OCR at render DPI) are mapped back to
source space through each output's `transform_to_source` before any pairing
or fingerprinting, so the draft's geometry is always source-space points.

The fingerprint is computed by E04's registered fpv algorithm from the SAME
span geometry the elements were built from; because the native-text pass uses
fpv1's nominal line metrics, a draft assembled from a born-digital document
reproduces the from-PDF fingerprint key exactly.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from adapters.fingerprint import fpv
from domain.artifacts.template import Anchor, PageGeometry, TemplateBody, TemplateElement
from domain.extraction import PageDims, PassOutput, TextSpan
from domain.provenance.transform import AffineTransform
from ports.canonical import CanonicalSerializer
from services.extraction.cascade import CascadeResult

_LABEL_SUFFIX = ":"


class TemplateAssembler:
    def __init__(self, *, serializer: CanonicalSerializer) -> None:
        self._serializer = serializer

    def assemble(self, result: CascadeResult, *, template_id: str, version: int, doc_class: str) -> TemplateBody:
        outputs = (result.native, *result.ocr_outputs, *result.vlm_outputs)
        return self.assemble_from_outputs(
            outputs=outputs,
            pages=result.native.pages,
            template_id=template_id,
            version=version,
            doc_class=doc_class,
        )

    def assemble_from_outputs(
        self,
        *,
        outputs: Sequence[PassOutput],
        pages: Sequence[PageDims],
        template_id: str,
        version: int,
        doc_class: str,
    ) -> TemplateBody:
        if not pages:
            raise ValueError("at least one source page is required to assemble a template")
        spans = _source_space_spans(outputs)
        elements = _anchored_elements(spans)
        if not elements:
            raise ValueError("no anchored label/value pairs found — nothing to assemble a draft template from")
        return TemplateBody(
            template_id=template_id,
            version=version,
            doc_class=doc_class,
            fingerprint=self._fingerprint(pages, spans),
            page_count=len(pages),
            pages=[_page_geometry(page) for page in pages],
            elements=elements,
        )

    def _fingerprint(self, pages: Sequence[PageDims], spans: Sequence[TextSpan]) -> str:
        algorithm = fpv.get_algorithm(fpv.current_version())
        page_bboxes: list[fpv.PageBBoxes] = [
            (
                page.width,
                page.height,
                [(span.bbox[0], span.bbox[1], span.bbox[2], span.bbox[3]) for span in spans if span.page == page.page],
            )
            for page in pages
        ]
        features = algorithm.features_from_bboxes(len(pages), page_bboxes)
        return fpv.fingerprint_key(features, self._serializer)


def _source_space_spans(outputs: Sequence[PassOutput]) -> list[TextSpan]:
    """Every span from every output, mapped into source space."""
    spans: list[TextSpan] = []
    for output in outputs:
        transform = AffineTransform.from_sequence(output.transform_to_source)
        spans.extend(
            span.model_copy(
                update={"bbox": list(transform.apply_to_bbox(span.bbox)), "coordinate_space": f"page-{span.page}"}
            )
            for span in output.spans
        )
    return spans


def _anchored_elements(spans: Sequence[TextSpan]) -> list[TemplateElement]:
    """One `value_region` element per label/value span pair, top to bottom."""
    labels = [span for span in spans if span.text.endswith(_LABEL_SUFFIX)]
    elements: list[TemplateElement] = []
    used_ids: set[str] = set()
    for label in sorted(labels, key=lambda span: (span.page, -span.bbox[1], span.bbox[0])):
        value = _value_span_for(label, spans)
        if value is None:
            continue
        elements.append(_element(label, value, _unique_id(_slug(label.text), used_ids)))
    return elements


def _element(label: TextSpan, value: TextSpan, element_id: str) -> TemplateElement:
    return TemplateElement(
        element_id=element_id,
        kind="value_region",
        page=label.page,
        bbox=list(value.bbox),
        anchor=Anchor(label_text=label.text, label_bbox=list(label.bbox)),
    )


def _value_span_for(label: TextSpan, spans: Sequence[TextSpan]) -> TextSpan | None:
    """The nearest span to the right of the label on the same visual row."""
    candidates = [
        span
        for span in spans
        if span is not label and span.page == label.page and _same_row(label, span) and span.bbox[0] >= label.bbox[2]
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda span: span.bbox[0])


def _same_row(a: TextSpan, b: TextSpan) -> bool:
    return a.bbox[1] < b.bbox[3] and b.bbox[1] < a.bbox[3]


def _page_geometry(page: PageDims) -> PageGeometry:
    return PageGeometry(page=page.page, width=page.width, height=page.height, unit="pt", rotation=0)


def _slug(label_text: str) -> str:
    words = re.sub(r"[^a-z0-9]+", "_", label_text.lower().rstrip(_LABEL_SUFFIX)).strip("_")
    return f"el_{words}"


def _unique_id(base: str, used_ids: set[str]) -> str:
    element_id = base
    suffix = 2
    while element_id in used_ids:
        element_id = f"{base}_{suffix}"
        suffix += 1
    used_ids.add(element_id)
    return element_id
