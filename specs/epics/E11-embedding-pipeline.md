# E11 — Two-tier, version-paired embedding pipeline

**Objective:** semantic chunks for masked documents, structural token-overlap chunks for unmasked ones; embedding sets paired to mask/template versions, built async, coexisting, switched only when complete.
**Depends on:** E07, E08, E03 (jobs). **Owned paths:** `src/services/embedding/`, `src/adapters/vectorindex/`.
**Read first:** architecture doc §6.3, §7.5, ADR 16; v0.2 §10 note on activation.

## Scope
- Chunkers (one class each): semantic (from the decoded view: text + semantic_role + section_path + system_context + provenance) and structural (token window + overlap, section_path from heading hierarchy, page, bbox). Chunk emission for masked docs consumes E09's mapping output; structural tier reads the document store directly.
- `VectorIndex` port: entries keyed `(tenant, document_id, mask_id, mask_version)` — structural tier keyed by template version with null mask; tenant partition mandatory in the port signature (impossible to omit).
- Version pairing: activation schedules an async build **alongside** the current set; retrieval default switches only when the new set completes; older sets remain explicitly queryable; GC honors retention policy and tenant-deletion cascade covers **all** versions.

## Tests first (acceptance: criteria 15 + structural addressing)
- MBR (no mask) → structural set immediately; `section_path`-filtered query returns only 13.4/16.3 chunks, each citing page+bbox.
- Activate `mask_mbrvendor` v1 → new semantic set builds while structural keeps serving; afterwards both coexist keyed by version; default retrieval = active mask version (criterion 15).
- Interrupted build resumes idempotently (job replay, pairs with criterion 14).
- Cross-tenant retrieval impossible at the port level (type/test).
- Tenant deletion removes every embedding version (extends E02 cascade tests).
- Chunker unit tests: overlap boundaries, heading-path assignment, provenance on every chunk (criterion 9 extension).

## Security
Embedding payloads carry chunk text + metadata only; index adapter authenticates per service; deletion is verified (read-after-delete test), because forgotten embeddings are the classic retention leak.

## Definition of done
Criterion 15 unskipped; both chunkers behind one `Chunker` protocol; index adapter contract-tested against the in-memory fake and the real backend.
