"""CascadeOrchestrator (epic E05): the analysis engine (slow path).

Deterministic passes run before probabilistic ones: native text first (a
born-digital document never touches the preprocessor, OCR, or any model),
then per-page preprocess + OCR + layout, then registered specialized
detectors, and only then the confidence gate routes individual regions to the
regional VLM fallback or to review. The VLM is handed ONE region at a time —
the port has no whole-page method, and this orchestrator never synthesizes a
page-sized region.

Open/closed: passes arrive via `CascadeRegistration`; adding a specialized
detector is a new `detectors` entry keyed by region kind, never an edit to
the dispatch loop.

Cost accounting: full analysis, per-page OCR, and regional model use are
recorded in separate ledger categories (criteria 1/3 reports). A per-tenant
cost-cap breach surfaces as `ExtractionJobFailed` carrying the full
itemization — never a silent halt.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from domain.extraction import PageImage, PassOutput, Region, TextSpan
from ports.clock import Clock
from ports.cost import CostCapExceeded, CostLedger
from ports.extraction_passes import (
    LayoutDetector,
    NativeTextPass,
    OcrPass,
    PagePreprocessor,
    RegionalVlmFallback,
    SpecializedDetector,
)
from services.extraction.confidence import ConfidenceGate, RegionAssessment, RegionScore

CascadePath = Literal["born_digital", "scanned"]


class ExtractionJobFailed(RuntimeError):  # noqa: N818 — name is BINDING (committed E05 test contract)
    """An extraction job halted. Always itemized: `items` carries the
    machine-readable failure detail (for a cost-cap breach: tenant, cap,
    totals, per-category spend, refused category)."""

    def __init__(self, *, job_ref: str, reason: str, items: Mapping[str, object]) -> None:
        self.job_ref = job_ref
        self.reason = reason
        self.items = dict(items)
        super().__init__(f"extraction job {job_ref} failed: {reason}")


@dataclass(frozen=True)
class CascadeCosts:
    """Deterministic cost model for the cascade's own (non-provider) work.
    Provider calls are costed by the provider response via `GuardedProvider`."""

    full_analysis: float
    ocr_per_page: float

    def __post_init__(self) -> None:
        if self.full_analysis < 0 or self.ocr_per_page < 0:
            raise ValueError("costs must not be negative")


@dataclass(frozen=True)
class CascadeRegistration:
    """The cascade's passes, by registration. `detectors` maps a region kind
    to the specialized detector for that kind — adding a kind is a new entry
    here, never an orchestrator edit."""

    native_text: NativeTextPass
    preprocessor: PagePreprocessor
    layout: LayoutDetector
    ocr: OcrPass
    vlm_fallback: RegionalVlmFallback
    detectors: Mapping[str, SpecializedDetector] = field(default_factory=dict)


@dataclass(frozen=True)
class RegionOutcome:
    """One region's gate assessment plus, when routed to fallback, the VLM's
    stamped output for exactly that region."""

    assessment: RegionAssessment
    vlm_output: PassOutput | None = None


@dataclass(frozen=True)
class CascadeResult:
    path: CascadePath
    native: PassOutput
    region_outcomes: tuple[RegionOutcome, ...]
    ocr_outputs: tuple[PassOutput, ...] = ()
    detector_outputs: tuple[PassOutput, ...] = ()

    @property
    def review_regions(self) -> tuple[Region, ...]:
        return tuple(
            outcome.assessment.region for outcome in self.region_outcomes if outcome.assessment.route == "review"
        )

    @property
    def vlm_outputs(self) -> tuple[PassOutput, ...]:
        return tuple(outcome.vlm_output for outcome in self.region_outcomes if outcome.vlm_output is not None)


class CascadeOrchestrator:
    def __init__(
        self,
        passes: CascadeRegistration,
        gate: ConfidenceGate,
        ledger: CostLedger,
        clock: Clock,
        *,
        costs: CascadeCosts,
    ) -> None:
        self._passes = passes
        self._gate = gate
        self._ledger = ledger
        self._clock = clock
        self._costs = costs

    @property
    def passes(self) -> CascadeRegistration:
        return self._passes

    def analyze(self, pdf_bytes: bytes, *, tenant_id: str, job_ref: str) -> CascadeResult:
        self._ledger.record(tenant_id, "full_analysis", self._costs.full_analysis)
        native = self._passes.native_text.extract_text(pdf_bytes)
        if native.spans:
            return self._born_digital(native)
        return self._scanned(pdf_bytes, native, tenant_id=tenant_id, job_ref=job_ref)

    # -- born-digital: deterministic text only, no raster, no models --------

    def _born_digital(self, native: PassOutput) -> CascadeResult:
        scores = [RegionScore(region=_span_region(span), raw_score=span.confidence) for span in native.spans]
        decision = self._gate.evaluate(scores)
        outcomes = tuple(RegionOutcome(assessment=assessment) for assessment in decision.assessments)
        return CascadeResult(path="born_digital", native=native, region_outcomes=outcomes)

    # -- scanned: per-page raster passes, then gated regional fallback ------

    def _scanned(self, pdf_bytes: bytes, native: PassOutput, *, tenant_id: str, job_ref: str) -> CascadeResult:
        if not native.pages:
            raise ValueError("source PDF yielded no pages")
        ocr_outputs: list[PassOutput] = []
        detector_outputs: list[PassOutput] = []
        images: dict[int, PageImage] = {}
        scores: list[RegionScore] = []
        for page in native.pages:
            image = self._passes.preprocessor.preprocess(pdf_bytes, page.page)
            images[page.page] = image
            ocr_outputs.append(self._recognize(image, tenant_id))
            scores.extend(self._detect_regions(image, detector_outputs))
        decision = self._gate.evaluate(scores)
        outcomes = tuple(self._resolve(assessment, images, job_ref) for assessment in decision.assessments)
        return CascadeResult(
            path="scanned",
            native=native,
            region_outcomes=outcomes,
            ocr_outputs=tuple(ocr_outputs),
            detector_outputs=tuple(detector_outputs),
        )

    def _recognize(self, image: PageImage, tenant_id: str) -> PassOutput:
        output = self._passes.ocr.recognize_text(image)
        self._ledger.record(tenant_id, "ocr", self._costs.ocr_per_page)
        return output

    def _detect_regions(self, image: PageImage, detector_outputs: list[PassOutput]) -> list[RegionScore]:
        layout = self._passes.layout.detect_regions(image)
        for region in layout.regions:
            detector = self._passes.detectors.get(region.kind)
            if detector is not None:
                detector_outputs.append(detector.detect(image, region))
        return [RegionScore(region=region, raw_score=region.score) for region in layout.regions]

    def _resolve(self, assessment: RegionAssessment, images: Mapping[int, PageImage], job_ref: str) -> RegionOutcome:
        if assessment.route != "vlm_fallback":
            return RegionOutcome(assessment=assessment)
        image = images[assessment.region.page]
        try:
            vlm_output = self._passes.vlm_fallback.read_region(image, assessment.region, job_ref)
        except CostCapExceeded as exc:
            raise ExtractionJobFailed(job_ref=job_ref, reason=str(exc), items=exc.itemized()) from exc
        return RegionOutcome(assessment=assessment, vlm_output=vlm_output)


def _span_region(span: TextSpan) -> Region:
    """A deterministic text span, viewed as a region for gating purposes."""
    return Region(
        page=span.page,
        bbox=list(span.bbox),
        coordinate_space=span.coordinate_space,
        kind="text",
        score=span.confidence,
    )
