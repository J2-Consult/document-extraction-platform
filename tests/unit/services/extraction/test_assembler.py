"""TemplateAssembler: draft TemplateBody from a cascade result — anchored
value regions from label/value span pairs, fingerprint via E04's fpv module,
working-space spans mapped back to source space, NO business meaning.
"""

from __future__ import annotations

import pytest

from adapters.fingerprint import fpv
from adapters.fingerprint.born_digital import BornDigitalFingerprintExtractor
from adapters.passes.layout import ScriptedLayoutDetector
from adapters.passes.native_text import PypdfNativeTextPass
from adapters.passes.ocr import OCR_STUB_COMPONENT_VERSION, ScriptedOcrPass
from adapters.passes.preprocessor import DeterministicPagePreprocessor
from adapters.providers.cost_ledger import InMemoryCostLedger
from domain.artifacts.canonical import JsonCanonicalSerializer
from domain.artifacts.template import TemplateBody
from domain.extraction import PageDims, PassOutput, TextSpan
from services.extraction.assembler import TemplateAssembler
from services.extraction.cascade import CascadeCosts, CascadeOrchestrator, CascadeRegistration
from services.extraction.confidence import ConfidenceGate
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.passes import NeverCalledVlmFallback, RecordingOcrPass, RecordingPreprocessor
from tests.unit.fakes.pdfs import NV_20260042, render_invoice_pdf_bytes


def _born_digital_result(pdf_bytes: bytes) -> object:
    registration = CascadeRegistration(
        native_text=PypdfNativeTextPass(),
        preprocessor=RecordingPreprocessor(DeterministicPagePreprocessor(render_dpi=300.0)),
        layout=ScriptedLayoutDetector(regions_by_page={}),
        ocr=RecordingOcrPass(ScriptedOcrPass(spans_by_page={})),
        vlm_fallback=NeverCalledVlmFallback(),
    )
    orchestrator = CascadeOrchestrator(
        registration,
        ConfidenceGate(accept_threshold=0.9, review_threshold=0.35),
        InMemoryCostLedger(),
        FakeClock(),
        costs=CascadeCosts(full_analysis=0.5, ocr_per_page=0.1),
    )
    return orchestrator.analyze(pdf_bytes, tenant_id="t-nordvik", job_ref="job-asm-01")


def _assembler() -> TemplateAssembler:
    return TemplateAssembler(serializer=JsonCanonicalSerializer())


def test_draft_template_from_born_digital_invoice_is_valid_and_anchored() -> None:
    pdf_bytes = render_invoice_pdf_bytes(NV_20260042)
    result = _born_digital_result(pdf_bytes)

    draft = _assembler().assemble(result, template_id="tmpl_draft", version=1, doc_class="invoice")  # type: ignore[arg-type]

    assert isinstance(draft, TemplateBody)
    assert draft.template_id == "tmpl_draft"
    assert draft.version == 1
    assert draft.doc_class == "invoice"
    assert draft.page_count == 1
    assert (draft.pages[0].width, draft.pages[0].height) == (595.0, 842.0)

    anchored = {element.anchor.label_text: element for element in draft.elements if element.anchor is not None}
    assert "Invoice number:" in anchored
    element = anchored["Invoice number:"]
    assert element.kind == "value_region"
    assert element.page == 1
    assert element.bbox[0] == pytest.approx(206.0), "value bbox must start at the value span, not the label"
    assert element.anchor is not None
    assert element.anchor.label_bbox[0] == pytest.approx(56.0)

    element_ids = [element.element_id for element in draft.elements]
    assert len(element_ids) == len(set(element_ids)), "element ids must be unique"


def test_draft_fingerprint_reproduces_the_from_pdf_fpv1_key() -> None:
    pdf_bytes = render_invoice_pdf_bytes(NV_20260042)
    result = _born_digital_result(pdf_bytes)

    draft = _assembler().assemble(result, template_id="tmpl_draft", version=1, doc_class="invoice")  # type: ignore[arg-type]

    features = BornDigitalFingerprintExtractor().extract(pdf_bytes)
    expected = fpv.fingerprint_key(features, JsonCanonicalSerializer())
    assert draft.fingerprint == expected
    assert draft.fingerprint.startswith("fpv1:sha256:")


def test_working_space_ocr_spans_are_mapped_back_to_source_space() -> None:
    scale = 300.0 / 72.0
    working_label = TextSpan(
        text="Invoice number:",
        page=1,
        bbox=[56.0 * scale, 780.0 * scale, 131.0 * scale, 792.0 * scale],
        coordinate_space="page-1@300dpi",
        confidence=0.9,
    )
    working_value = TextSpan(
        text="2026-0042",
        page=1,
        bbox=[206.0 * scale, 780.0 * scale, 251.0 * scale, 792.0 * scale],
        coordinate_space="page-1@300dpi",
        confidence=0.9,
    )
    inverse_scale = 72.0 / 300.0
    ocr_output = PassOutput(
        method="ocr",
        component_version=OCR_STUB_COMPONENT_VERSION,
        transform_to_source=[inverse_scale, 0.0, 0.0, inverse_scale, 0.0, 0.0],
        spans=(working_label, working_value),
    )

    draft = _assembler().assemble_from_outputs(
        outputs=(ocr_output,),
        pages=(PageDims(page=1, width=595.0, height=842.0),),
        template_id="tmpl_draft_scan",
        version=1,
        doc_class="invoice",
    )

    anchored = [element for element in draft.elements if element.anchor is not None]
    assert len(anchored) == 1
    assert anchored[0].anchor is not None
    assert anchored[0].anchor.label_bbox[0] == pytest.approx(56.0)
    assert anchored[0].bbox[0] == pytest.approx(206.0)
    assert anchored[0].bbox[1] == pytest.approx(780.0)
