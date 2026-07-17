# E05 interface design (architect draft)

Authority: epic E05 + CLAUDE.md. Public shapes below are binding; flag deviations.

## Module layout

```
src/ports/extraction_passes.py  # one small Protocol per pass (interface segregation):
                                # NativeTextPass, PagePreprocessor, LayoutDetector,
                                # OcrPass, SpecializedDetector, RegionalVlmFallback
src/ports/providers.py          # ModelProvider protocol (regional calls only), ProviderResponse
src/ports/clock.py              # Clock protocol (now() -> float) — fake-able time
src/ports/cost.py               # CostLedger protocol: record(tenant_id, category, cost), spent(tenant_id)
src/adapters/passes/            # concrete passes (pdf_text via pypdf, stub detectors)
src/adapters/providers/         # provider wrappers: timeout, CircuitBreaker, RateLimit,
                                # per-tenant cost caps, component-version stamping
src/services/extraction/
  cascade.py                    # CascadeOrchestrator — passes by REGISTRATION, never edited
  confidence.py                 # ConfidenceGate: raw + calibrated per region
  assembler.py                  # TemplateAssembler -> draft TemplateBody (no business meaning)
  targeted.py                   # TargetedExtractor (fast path, label-anchor based)
```

## Key shapes

- Common value objects (frozen dataclasses or Pydantic, in src/domain): `PageImage`
  (bytes + coordinate_space id + dpi), `Region` (page, bbox, kind, score),
  `TextSpan` (text, bbox, page), `PassOutput` (regions/spans + provenance fragments +
  component_version). Every output fragment carries enough to build E06 provenance
  (method, component_version, bbox, coordinate_space).
- Pass protocols are SINGLE-method: e.g.
  `class NativeTextPass(Protocol): def extract_text(self, pdf_bytes: bytes) -> PassOutput`
  `class RegionalVlmFallback(Protocol): def read_region(self, image: PageImage, region: Region, job_ref: str) -> PassOutput`
  — VLM fallback accepts ONE region; there is deliberately no whole-page/whole-doc
  method on any protocol (structural enforcement of "VLM per region only").
- `CascadeOrchestrator(passes: CascadeRegistration, gate: ConfidenceGate, ledger: CostLedger, clock: Clock)` —
  deterministic passes run before probabilistic; adding a pass = new registration
  entry (kind → implementation), dispatch loop closed for modification.
- `ConfidenceGate.evaluate(region_scores) -> GateDecision` where GateDecision routes
  each region: `accept | vlm_fallback | review`; records `raw_score` AND
  `calibrated_confidence` per region.
- Provider wrapper (`src/adapters/providers/guarded.py` `GuardedProvider`): wraps any
  `ModelProvider` with timeout, circuit breaker (opens after N consecutive failures,
  half-open after cooldown — fake clock tested), rate limit, per-tenant cost cap
  (cap breach ⇒ raise `CostCapExceeded` → job fails ITEMIZED, never silent).
  Payloads: page images/regions + opaque `job_ref` ONLY — never tenant ids;
  responses schema-validated before use (untrusted data).
- Cost accounting: `CostLedger.record(tenant, category: Literal["regional_model","full_analysis","ocr"], cost)`
  — feeds criteria 1/3 reports.
- `TargetedExtractor.extract(pdf_bytes, template: TemplateBody) -> list[Observation]` —
  label-text-first anchor matching (tolerant to small shifts), value-region read,
  state assignment `present/empty/unreadable/not_found` per E01 legality; every
  observation carries provenance.

## Tests (per epic)

Spy/fake implementations for every port live in tests/unit/fakes/ (reusable by later
epics). Born-digital: OCR spy never invoked; scanned: preprocessor+OCR invoked, VLM
fake called only for the one low-confidence region; 5px-shifted re-render of invoice
0043 (generate via fixtures/pdfs/generate_pdfs.py functions with a y-offset param in
the TEST, not by editing fixtures) extracts all values via anchors; state
distinguishability (criterion 8); breaker + cost cap with fake clock.
