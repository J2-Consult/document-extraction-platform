# E05 — Multipass extraction cascade & targeted extractor

**Objective:** the analysis engine (slow path) and the anchor-based targeted extractor (fast path), built as swappable passes behind ports — deterministic before probabilistic, VLM per region only.
**Depends on:** E04, E06. **Owned paths:** `src/services/extraction/`, `src/adapters/passes/`, `src/adapters/providers/`.
**Read first:** architecture doc §4.3 (multipass), design rules; v0.2 §4.4 note, §6.1–6.2.

## Scope
- Ports, one per pass (interface segregation): `NativeTextPass`, `PagePreprocessor`, `LayoutDetector`, `OcrPass`, `SpecializedDetector` (table/kv/mark/signature), `RegionalVlmFallback`. A `CascadeOrchestrator` composes them; adding a pass is registration, not modification (open/closed).
- Provider abstraction wrapping external models: timeouts, circuit breaker, rate limits, **per-tenant cost caps**, component-version stamping into provenance.
- Confidence gate: region-level scores; below-threshold regions → VLM fallback or review. Raw score + calibrated routing confidence both recorded (v0.2 §6.2).
- Template assembler: draft template versions, **no business meaning**, fingerprint via E04's serializer.
- Targeted extractor (fast path): label-text-first anchor matching, value-region read, value-state assignment (`present/empty/unreadable/not_found`).

## Tests first (acceptance: criteria 1-part, 8; legacy anchor-robustness)
- Born-digital invoice: every value `provenance.method='pdf_text'`; OCR pass never invoked (spy).
- Scanned path invokes preprocessor + OCR; VLM fake called only for the one low-confidence region, never whole pages.
- 5px-shifted re-render of invoice 0043 extracts all values via label anchors.
- Confidently blank optional field → `state='empty'`, distinguishable from `unreadable` and `not_found` (criterion 8), each state carrying provenance.
- Circuit breaker opens after N provider failures (fake clock); per-tenant cost cap halts calls with itemized job failure.
- Cost accounting separates regional model use from full analysis (feeds criterion 1/3 reports).

## Security
Provider keys from env; provider payloads contain page images/regions only — never tenant identifiers beyond an opaque job ref; responses treated as untrusted data (schema-validated).

## Definition of done
Criterion 8 unskipped; cascade fully driveable with in-memory fakes; provider adapters share one contract-test suite.
