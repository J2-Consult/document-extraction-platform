"""CascadeOrchestrator: deterministic passes before probabilistic ones,
registration-based dispatch (open/closed), VLM strictly per region, cost
accounting per category, itemized halt on cost-cap breach.
"""

from __future__ import annotations

import pytest

from adapters.passes.layout import ScriptedLayoutDetector
from adapters.passes.native_text import PypdfNativeTextPass
from adapters.passes.ocr import ScriptedOcrPass
from adapters.passes.preprocessor import DeterministicPagePreprocessor
from adapters.passes.vlm_regional import ProviderBackedRegionalVlmFallback
from adapters.providers.cost_ledger import InMemoryCostLedger
from adapters.providers.guarded import GuardedProvider, GuardedProviderConfig
from domain.extraction import Region, TextSpan
from services.extraction.cascade import (
    CascadeCosts,
    CascadeOrchestrator,
    CascadeRegistration,
    ExtractionJobFailed,
)
from services.extraction.confidence import ConfidenceGate
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.passes import (
    NeverCalledVlmFallback,
    RecordingOcrPass,
    RecordingPreprocessor,
    RecordingSpecializedDetector,
    RecordingVlmFallback,
)
from tests.unit.fakes.pdfs import NV_20260042, render_invoice_pdf_bytes, render_textless_pdf_bytes
from tests.unit.fakes.providers import ScriptedModelProvider, provider_payload

_TENANT = "t-nordvik"
_JOB_REF = "job-cascade-01"
_COSTS = CascadeCosts(full_analysis=0.50, ocr_per_page=0.10)

_CONFIDENT_REGION = Region(page=1, bbox=[56.0, 700.0, 400.0, 720.0], coordinate_space="page-1", kind="text", score=0.95)
_LOW_CONFIDENCE_REGION = Region(
    page=1, bbox=[206.0, 636.0, 346.0, 648.0], coordinate_space="page-1", kind="text", score=0.55
)
_HOPELESS_REGION = Region(page=1, bbox=[56.0, 100.0, 400.0, 120.0], coordinate_space="page-1", kind="text", score=0.10)


def _gate() -> ConfidenceGate:
    return ConfidenceGate(accept_threshold=0.9, review_threshold=0.35)


def _ocr_span(text: str = "OCR LINE", confidence: float = 0.95) -> TextSpan:
    return TextSpan(
        text=text, page=1, bbox=[56.0, 700.0, 300.0, 720.0], coordinate_space="unstamped", confidence=confidence
    )


def _scanned_fixture(
    *,
    regions: tuple[Region, ...],
    vlm: RecordingVlmFallback | NeverCalledVlmFallback,
    ledger: InMemoryCostLedger,
    detectors: dict[str, RecordingSpecializedDetector] | None = None,
) -> CascadeOrchestrator:
    registration = CascadeRegistration(
        native_text=PypdfNativeTextPass(),
        preprocessor=RecordingPreprocessor(DeterministicPagePreprocessor(render_dpi=300.0)),
        layout=ScriptedLayoutDetector(regions_by_page={1: regions}),
        ocr=RecordingOcrPass(ScriptedOcrPass(spans_by_page={1: (_ocr_span(),)})),
        vlm_fallback=vlm,
        detectors=detectors or {},
    )
    return CascadeOrchestrator(registration, _gate(), ledger, FakeClock(), costs=_COSTS)


def _guarded_vlm(ledger: InMemoryCostLedger, *, cost_cap: float = 100.0) -> RecordingVlmFallback:
    provider = ScriptedModelProvider([provider_payload(text="Net 30 days", cost=0.02)])
    guarded = GuardedProvider(
        provider,
        tenant_id=_TENANT,
        clock=FakeClock(),
        ledger=ledger,
        config=GuardedProviderConfig(cost_cap=cost_cap),
    )
    return RecordingVlmFallback(ProviderBackedRegionalVlmFallback(guarded))


def test_born_digital_invoice_never_touches_preprocessor_ocr_or_vlm() -> None:
    preprocessor = RecordingPreprocessor(DeterministicPagePreprocessor(render_dpi=300.0))
    ocr = RecordingOcrPass(ScriptedOcrPass(spans_by_page={}))
    vlm = NeverCalledVlmFallback()
    ledger = InMemoryCostLedger()
    registration = CascadeRegistration(
        native_text=PypdfNativeTextPass(),
        preprocessor=preprocessor,
        layout=ScriptedLayoutDetector(regions_by_page={}),
        ocr=ocr,
        vlm_fallback=vlm,
    )
    orchestrator = CascadeOrchestrator(registration, _gate(), ledger, FakeClock(), costs=_COSTS)

    result = orchestrator.analyze(render_invoice_pdf_bytes(NV_20260042), tenant_id=_TENANT, job_ref=_JOB_REF)

    assert result.path == "born_digital"
    assert result.native.method == "pdf_text"
    assert len(result.native.spans) > 0
    assert ocr.call_count == 0, "OCR must NEVER be invoked on a born-digital document"
    assert preprocessor.call_count == 0
    assert vlm.call_count == 0
    assert all(outcome.assessment.route == "accept" for outcome in result.region_outcomes)
    assert ledger.spent_in_category(_TENANT, "full_analysis") == pytest.approx(_COSTS.full_analysis)
    assert ledger.spent_in_category(_TENANT, "ocr") == 0.0


def test_scanned_path_runs_preprocessor_and_ocr_per_page() -> None:
    ledger = InMemoryCostLedger()
    vlm = NeverCalledVlmFallback()
    orchestrator = _scanned_fixture(regions=(_CONFIDENT_REGION,), vlm=vlm, ledger=ledger)

    result = orchestrator.analyze(render_textless_pdf_bytes(), tenant_id=_TENANT, job_ref=_JOB_REF)

    assert result.path == "scanned"
    registration_preprocessor = orchestrator.passes.preprocessor
    assert isinstance(registration_preprocessor, RecordingPreprocessor)
    assert registration_preprocessor.pages_preprocessed == [1]
    registration_ocr = orchestrator.passes.ocr
    assert isinstance(registration_ocr, RecordingOcrPass)
    assert registration_ocr.pages_recognized == [1]
    assert len(result.ocr_outputs) == 1
    assert result.ocr_outputs[0].method == "ocr"
    assert vlm.call_count == 0, "all regions confident: no fallback"


def test_vlm_fake_is_called_only_for_the_one_low_confidence_region_never_whole_pages() -> None:
    ledger = InMemoryCostLedger()
    vlm = _guarded_vlm(ledger)
    regions = (_CONFIDENT_REGION, _LOW_CONFIDENCE_REGION, _HOPELESS_REGION)
    orchestrator = _scanned_fixture(regions=regions, vlm=vlm, ledger=ledger)

    result = orchestrator.analyze(render_textless_pdf_bytes(), tenant_id=_TENANT, job_ref=_JOB_REF)

    assert vlm.call_count == 1, "exactly ONE region falls between review and accept thresholds"
    read_region = vlm.regions_read[0]
    assert read_region.bbox == _LOW_CONFIDENCE_REGION.bbox
    image, _, job_ref = vlm.calls[0]
    page_bbox = [0.0, 0.0, image.width, image.height]
    assert read_region.bbox != page_bbox, "the VLM must never be handed a whole page as a region"
    assert job_ref == _JOB_REF
    assert [region.bbox for region in result.review_regions] == [_HOPELESS_REGION.bbox]


def test_cost_accounting_separates_regional_model_from_full_analysis_and_ocr() -> None:
    ledger = InMemoryCostLedger()
    vlm = _guarded_vlm(ledger)
    orchestrator = _scanned_fixture(regions=(_LOW_CONFIDENCE_REGION,), vlm=vlm, ledger=ledger)

    orchestrator.analyze(render_textless_pdf_bytes(), tenant_id=_TENANT, job_ref=_JOB_REF)

    assert ledger.spent_in_category(_TENANT, "full_analysis") == pytest.approx(0.50)
    assert ledger.spent_in_category(_TENANT, "ocr") == pytest.approx(0.10)
    assert ledger.spent_in_category(_TENANT, "regional_model") == pytest.approx(0.02)
    assert ledger.spent(_TENANT) == pytest.approx(0.62)


def test_cost_cap_breach_halts_the_job_with_an_itemized_failure_never_silently() -> None:
    ledger = InMemoryCostLedger()
    # full_analysis (0.50) + ocr (0.10) exceed this cap before the VLM call.
    vlm = _guarded_vlm(ledger, cost_cap=0.25)
    orchestrator = _scanned_fixture(regions=(_LOW_CONFIDENCE_REGION,), vlm=vlm, ledger=ledger)

    with pytest.raises(ExtractionJobFailed) as excinfo:
        orchestrator.analyze(render_textless_pdf_bytes(), tenant_id=_TENANT, job_ref=_JOB_REF)

    failure = excinfo.value
    assert failure.job_ref == _JOB_REF
    assert "cost cap" in failure.reason
    assert failure.items["tenant_id"] == _TENANT
    assert failure.items["cap"] == 0.25
    assert failure.items["attempted_category"] == "regional_model"
    by_category = failure.items["spent_by_category"]
    assert isinstance(by_category, dict)
    assert by_category["full_analysis"] == pytest.approx(0.50)


def test_registered_specialized_detector_is_dispatched_by_region_kind_without_editing_the_orchestrator() -> None:
    from adapters.passes.detectors import EchoSpecializedDetector

    ledger = InMemoryCostLedger()
    kv_region = Region(page=1, bbox=[56.0, 500.0, 400.0, 520.0], coordinate_space="page-1", kind="kv", score=0.95)
    kv_detector = RecordingSpecializedDetector(EchoSpecializedDetector(kind="kv"))
    orchestrator = _scanned_fixture(
        regions=(kv_region, _CONFIDENT_REGION),
        vlm=NeverCalledVlmFallback(),
        ledger=ledger,
        detectors={"kv": kv_detector},
    )

    result = orchestrator.analyze(render_textless_pdf_bytes(), tenant_id=_TENANT, job_ref=_JOB_REF)

    assert kv_detector.call_count == 1, "detector must be dispatched for its registered kind only"
    assert kv_detector.regions_detected[0].kind == "kv"
    assert len(result.detector_outputs) == 1
    assert result.detector_outputs[0].method == "detector"
