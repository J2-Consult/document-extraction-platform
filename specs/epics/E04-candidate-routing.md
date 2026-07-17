# E04 — Cheap candidate extractor, verification gate, benchmark harness

**Objective:** the two-stage router: cheap fingerprint retrieval of candidate templates, then a verification gate that must accept before the fast path — with the benchmark harness that proves the net saving.
**Depends on:** E01 (canonical serializer), E03 (jobs). **Owned paths:** `src/services/routing/`, `src/adapters/fingerprint/`, `benchmarks/routing/`.
**Read first:** architecture doc §3.3 (as corrected: candidate + verification); v0.2 §4 entirely; fixtures/fpv1.py.

## Scope
- `FingerprintFeatureExtractor` port with two strategies: born-digital (native text-block/drawing geometry, line projections) and scanned (post-deskew geometry, low-res visual features). **Excluded by construction:** OCR, region classification, VLM.
- Canonical representation → `fpvN:sha256:` key; algorithm version bump machinery (changing features/quantization ⇒ new fpvN + re-key templates from stored bodies).
- `TemplateVerifier` port: bounded discriminating checks (page count/geometry, stable label anchors, major regions, table boundaries, optional negative anchors) → `accepted | rejected | inconclusive`. **Inconclusive is never force-matched** (principle 5).
- Routing decision record persisted: fpv version, candidate, checks, result, latency, component versions.
- Benchmark harness: runs the corpus (fixtures + generated decoys), reports candidate-hit rate, verification false-accept/false-reject **separately**, p50/p95 latency, and net cost vs full analysis.

## Tests first (acceptance: criteria 1, 2, 3)
- Both Nordvik invoices produce the same key from the *cheap extractor on raw PDFs* (not from templates).
- A generated decoy — same page geometry, moved labels — gets a candidate hit but is **rejected by verification** and routed to full analysis (criterion 2).
- Inconclusive → slow path; decision record written with all fields.
- Fast path on invoice #2 makes zero full-layout and zero whole-document VLM calls (spy providers); regional model calls accounted separately (criterion 1).
- Benchmark harness emits the criterion-3 report artifact.

## Security
Feature extraction runs on hostile files inside the sandboxed worker; hard timeouts; no shelling out with file-derived strings.

## Definition of done
Criteria 1–3 unskipped; decoy generator checked in; false-accept on the benchmark corpus = 0.
