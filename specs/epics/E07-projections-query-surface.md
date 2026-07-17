# E07 — Relational projections & the document_values query surface

**Objective:** idempotent projections of query-hot arrays (`extracted_values`, `mask_entries`) derived from immutable artifacts, and the `document_values` view (security_invoker) that everything downstream queries.
**Depends on:** E02, E03. **Owned paths:** `migrations/` (additive), `src/services/projection/`, `src/adapters/postgres/queries.py`.
**Read first:** architecture doc §5.5 (as amended: selection-not-merge, attribution); v0.2 §9.1–9.2.

## Scope
- Projection tables per v0.2 §9.1 with tenant-first keys; writer is idempotent and derived only from the immutable artifact bodies (re-runnable, order-independent).
- `resolved_active_masks` + `document_values` view with `security_invoker=true`; **resolution is selection, never merge** — the customer's materialized effective mask or the vendor baseline, one immutable mask.
- Expose entry attribution (`inherited_from`, `overridden`) so "toggle the baseline / show my changes" are WHERE clauses (ADR 20 — the future UI's contract).
- Typed read-side query module (parameterized, no string SQL) used by mapping, orchestrator, and embedding epics.

## Tests first (acceptance: criteria 12 + view behavior)
- Projection equals artifacts: for every fixture document, `document_values` rows == values decoded straight from the JSON artifacts (criterion 12), with no JSON-array Cartesian expansion (assert query plan touches projections).
- Idempotency: project twice → identical rows.
- With `app.tenant_id` set: customer effective mask resolves, full coverage, 3 rows `overridden=true`; baseline-toggle query returns exactly the customer-authored/overridden subset. Unset: vendor baseline. (Revised criterion 7.)
- RLS holds through the view for a restricted role (ties into E02 suite).

## Security
`security_invoker` so RLS is never bypassed by view ownership; the query module is the only sanctioned read path — direct table access from services fails review.

## Definition of done
Criteria 7 and 12 unskipped; EXPLAIN-based regression test pinned; projection writer covered for partial-failure re-runs.
