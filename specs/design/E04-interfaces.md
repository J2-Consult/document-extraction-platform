# E04 interface design (architect draft)

Authority: epic E04 + CLAUDE.md + fixtures/fpv1.py. Implementer may adjust internals;
public shapes below require a flagged deviation.

## Module layout

```
src/ports/fingerprint.py     # FingerprintFeatureExtractor, FingerprintFeatures
src/ports/verification.py    # TemplateVerifier, VerificationResult, VerificationCheck
src/ports/routing_store.py   # TemplateCandidateIndex, RoutingDecisionStore
src/adapters/fingerprint/
  born_digital.py            # native text-block/drawing geometry, line projections
  scanned.py                 # post-deskew geometry, low-res visual features
  fpv.py                     # fpv registry: version -> (extractor config, quantization);
                             # bump machinery + re-key-from-stored-bodies helper
src/services/routing/
  router.py                  # CandidateRouter: extract -> key -> candidates -> verify -> decision
  decisions.py               # RoutingDecision dataclass/model
benchmarks/routing/
  decoys.py                  # decoy generator (same geometry, moved labels)
  harness.py                 # corpus runner -> report artifact (JSON + md table)
```

## Key shapes

- `FingerprintFeatures`: frozen model `{fpv: int, page_count: int, pages: [...]}` —
  the born-digital feature shape MUST reproduce fixtures/fpv1.py exactly (same
  quantization grid, same canonical serialization via E01's `CanonicalSerializer`,
  same `fpv1:sha256:<hex>` key). A test pins byte-equality of keys against fpv1.py
  for both fixture invoices.
- `class FingerprintFeatureExtractor(Protocol):
     def extract(self, pdf_bytes: bytes) -> FingerprintFeatures` — OCR, region
  classification, and VLM are excluded BY CONSTRUCTION: adapters in
  `src/adapters/fingerprint/` may import pypdf/geometry helpers only; an
  architecture test asserts the package imports no provider/OCR modules.
- `VerificationResult`: `status: Literal["accepted","rejected","inconclusive"]`,
  `checks: tuple[VerificationCheck, ...]` where VerificationCheck =
  `{check_id, passed: bool | None, detail}` (None = not evaluable → contributes to
  inconclusive). `inconclusive` is NEVER force-matched — router routes it to the
  slow path; make this a type-level impossibility where practical (router's fast
  path accepts only `status == "accepted"`).
- `class TemplateVerifier(Protocol):
     def verify(self, features: FingerprintFeatures, pdf_bytes: bytes,
                candidate: TemplateBody) -> VerificationResult` — bounded
  discriminating checks: page count/geometry, stable label anchors, major regions,
  table boundaries, optional negative anchors. Hard time budget per check.
- `class TemplateCandidateIndex(Protocol):
     def find_by_key(self, fingerprint_key: str) -> Sequence[TemplateRef]` — in-memory
  fake for tests; Postgres adapter lands with E07's query surface, not here.
- `RoutingDecision`: fpv version, fingerprint key, candidate ref | None,
  verification result, latency_ms, component_versions, routed_to:
  `Literal["fast_path","full_analysis"]`. Persisted via
  `RoutingDecisionStore.append(decision)` (append-only port; in-memory fake now).
- `CandidateRouter.route(pdf_bytes) -> RoutingDecision` — pure orchestration over the
  ports; constructor injection; no I/O beyond the ports.

## Benchmark harness

Runs fixtures + generated decoys through the router with spy providers; emits
`benchmarks/routing/report.json` (+ human-readable table): candidate-hit rate,
false-accept and false-reject SEPARATELY, p50/p95 latency, net cost vs full
analysis. Criterion 3's acceptance test asserts the artifact exists and has the
required fields; criterion-2's decoy path and criterion-1's zero-full-analysis
spy assertions live in tests/acceptance.

## Test placement

tests/unit/services/routing/, tests/unit/adapters/fingerprint/,
benchmarks assertions in tests/unit/benchmarks_routing/ (fast, no network);
acceptance criteria 1–3 unskipped in tests/acceptance/test_skeleton_criteria.py.
