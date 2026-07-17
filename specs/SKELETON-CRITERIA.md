# Walking-skeleton acceptance criteria (1–16)

Reconstruction note: the client draft v0.2 §12.1 and `document-extraction-architecture.md`
are not present in this repository. This file reconstructs the 16 skeleton criteria from
the epic files' explicit acceptance mappings (each epic names the criteria it unskips).
Authority order: if the original v0.2 document is added later and disagrees, v0.2 wins
and this file must be corrected. Each criterion below is the contract for one skipped
acceptance-test scaffold created in E00 (`@pytest.mark.epic("EXX")`).

| # | Criterion (behavior, testable) | Epic |
|---|---|---|
| 1 | Fast path on a fingerprint-routed known invoice (doc_nv20260043) completes with **zero full-layout and zero whole-document VLM calls** (spy providers prove it); regional model calls are accounted separately in the cost record. | E04 (+E05) |
| 2 | A generated decoy with identical page geometry but moved labels gets a **candidate hit** from the cheap extractor but is **rejected by the verification gate** and routed to full analysis; the routing decision record captures fpv version, candidate, checks, result, latency, component versions. | E04 |
| 3 | The benchmark harness runs the corpus (fixtures + decoys) and emits a report artifact with candidate-hit rate, verification false-accept and false-reject rates **reported separately**, p50/p95 latency, and net cost vs full analysis. False-accept on the corpus = 0. | E04 |
| 4 | Connected as real restricted DB roles (never superuser), Tenant A cannot select, resolve, infer, or update any of Tenant B's documents, derived values, masks, private templates, jobs, or review items — enforced by RLS at the SQL layer, and the `synthesis` role cannot read customer-scope masks or customer-private templates. | E02 |
| 5 | Registering template v2 (field moved = compatible, one field split, one added) yields exact per-element lineage; compatible mask entries auto-migrate into a draft mask; split/added elements land in the review worklist. | E08 |
| 6 | A release unit (template + required compatible masks) activates atomically; documents processed under v1 remain reproducible against their pinned template/mask versions. | E08 |
| 7 | End-to-end mask-and-map: with tenant context set, resolution **selects** the customer's materialized effective mask (full coverage, exactly 3 entries `overridden=true`, baseline-toggle query returns the customer-authored subset); a required value below confidence threshold yields `pending_review` with `record: null` and an itemized review item; after human correction (provenance `method='human'`) re-mapping yields `completed`. | E07 + E09 |
| 8 | A confidently blank optional field is recorded `state='empty'`, mechanically distinguishable from `unreadable` and `not_found`, and every state assertion carries provenance. | E05 |
| 9 | Every extracted value and unmapped-content note in the fixture corpus carries valid provenance (source hash, page, bbox, method, component_version, coordinate space). | E06 |
| 10 | Property-based round-trip: random bboxes mapped through preprocessing transforms (deskew + scale + crop) and back to source space land within tolerance. | E06 |
| 11 | Every fixture artifact validates against the typed contracts; each listed invariant mutation (unknown element_id, missing provenance, envelope/body contradiction, illegal state/value combo, vendor mask with tenant_id, overridden without inherited_from, bad fingerprint) is rejected with an itemized machine-readable error (path + code + message). | E01 (+E06) |
| 12 | For every fixture document, `document_values` rows equal the values decoded straight from the immutable JSON artifacts; the query plan touches projection tables (no JSON-array Cartesian expansion); projecting twice is idempotent. | E07 |
| 13 | A payment-terms question about doc_nv20260042 is answered by the orchestrator via `get_document_value` only: assembled context stays under the token budget, the answer cites provenance, and a prompt-injection payload embedded in document text flows through retrieval as inert data. | E10 |
| 14 | Replaying the same upload N times produces exactly one stored object, one document row, one job; worker redelivery of a completed job is a no-op; a masquerading file (exe named .pdf) is rejected by magic bytes. | E03 |
| 15 | An unmasked document gets a structural embedding set immediately; activating a mask builds the semantic set async **alongside** the serving set; both coexist keyed by version and default retrieval switches only when the new set is complete. | E11 |
| 16 | The scorecard runner executes the acceptance corpus against `targets.yaml` and renders a pass/fail table for all pilot exit criteria; tightening any one target flips the pilot verdict to fail. | E12 |
