# E09 — Mapping outcomes, review workflow, Validation Service integration

**Objective:** the stateless mapping service with the strict outcome state machine — no partial records, ever — plus the human-review loop and the preparator hand-off to the external Validation Service.
**Depends on:** E05, E07, E08. **Owned paths:** `src/services/mapping/`, `src/services/review/`, `src/adapters/validation_service/`, `src/api/routes/mappings.py`.
**Read first:** architecture doc §6 (esp. 6.4); v0.2 §6.3; the Validation Service design doc (preparator pattern, `_bboxes`).

## Scope
- Mapping pipeline (each step one component): resolve refs → apply mask (semantic roles, `enum_map`, table column mapping) → coerce/normalize per `target_datatype` → bind versioned target schema → outcome.
- Outcomes: `completed | pending_review | pending_template_review | rejected | failed` — a required low-confidence value ⇒ `pending_review`, `record: null`, itemized `review_items`, `contract_validation: not_evaluated` (v0.2 §6.3). Optional low-confidence exclusion only when the target schema permits absence, with the review item still reported.
- Review workflow: correction re-enters with `provenance.method='human'` + corrector identity; re-map to `completed`.
- Validation Service adapter (preparator): flatten the decoded record, attach `_bboxes` from provenance, invoke ruleset; business-rule violations remain a distinct category from contract errors, extraction uncertainty, and technical failure.
- **Forbidden here above all:** any business rule in this codebase.

## Tests first (acceptance: criteria 7-part, 11-part; skeleton 6/7 legacy)
- Vendor mask + `invoice_record_v1`: clean invoice → `completed`, record validates; ticked "Yes" → `true` via enum_map.
- Smudged total (0.61 < threshold, required) → `pending_review`, `record: null`, itemized entry (criterion 7); after human correction → `completed`, correction carries provenance.
- Optional low-confidence value excluded only when schema permits; review item still present.
- Four error categories asserted distinct on four crafted inputs.
- Preparator contract test: recorded request matches the Validation Service payload schema (service faked; contract pinned).
- Statelessness: same inputs twice ⇒ byte-identical outputs.

## Security
Endpoint authorization per target schema (not every caller may bind every schema); responses never echo raw document content beyond the mapped record; review corrections are authenticated and audited.

## Definition of done
Criterion 7 unskipped end-to-end (extract → pending → correct → completed); mapping service importable with zero adapter imports (statelessness proven by architecture test).
