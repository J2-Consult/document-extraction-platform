# E06 — Provenance & coordinate spaces

**Objective:** make "provenance to pixels" mechanically true: coordinate spaces, affine transforms back to source, per-page geometry — and extend E01's validator so nothing without provenance survives.
**Depends on:** E01. **Owned paths:** `src/domain/provenance/`, extensions in `src/services/validation/`.
**Read first:** v0.2 §7 entirely; architecture doc principle 8.

## Scope
- Provenance model: source artifact (hash, page), working artifact (hash, coordinate_space id), bbox, method, component_version, `transform_to_source` (affine 6-tuple) or reference to a versioned transform artifact.
- Per-page geometry (width/height/unit/rotation per page — mixed page sizes are legal).
- Preprocessing records: render DPI, deskew angle, crop, rotation matrix, pipeline version.
- Transform utilities: bbox mapping working-space ⇄ source-space; composition; inverse.
- Validator extensions: provenance required on values, blank assertions, unmapped content, chunks, human corrections; coordinate-space id must resolve to a recorded space.

## Tests first (acceptance: criteria 9, 10)
- Property-based round-trip: random bboxes through deskew+scale transforms map back within tolerance (criterion 10).
- Fixture sweep: every value/unmapped note in fixtures carries valid provenance (criterion 9 baseline).
- A value missing provenance, or citing an unknown coordinate space, is rejected (extends criterion 11).
- Mixed-page-size document geometry validates; page index out of range rejected.

## Security
Hashes make the audit trail tamper-evident: verify source hash on read paths that surface provenance externally.

## Definition of done
Criteria 9–10 unskipped; transform utils 100% branch-covered (they are small and load-bearing).
