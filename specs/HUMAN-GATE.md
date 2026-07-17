# Human review gate — items requiring sign-off before production merge

Per MODELS.md §2/§3.4: E02 and E10, and any diff touching RLS, mask scoping, or
prompt assembly, require human approval regardless of model verdicts. All items
below carry two-model process coverage (generator + cross-model reviewer) and green
deterministic gates; what they lack is the mandated human eye.

## 1. E02 — tenant isolation (migrations/0001, 0002; src/adapters/postgres/session.py)
FORCE RLS on all five tables, per-role policies (synthesis can never see customer
masks/private templates even with tenant context set), least-privilege roles,
transactional tenant GUC. 36-test isolation suite runs green as real restricted
roles against live Postgres. Reviewer: Fable (approve). VERIFY YOURSELF:
`make test-isolation` and read migrations/0002_rls_grants.sql.

## 2. E03 — migration 0003 (ingestion_outbox RLS surface)
Additive table with FORCE RLS + tenant policy + revoke-then-grant. Reviewer: Opus
(approve; explicitly flagged the RLS surface for this gate).

## 3. E07 — migration 0004 (projection tables + security_invoker views)
RLS mirrored from E02; `document_values`/`resolved_active_masks` are
security_invoker so view ownership never bypasses RLS; resolution is
selection-not-merge. Reviewer: Opus (approve). A latent section-read defect found
in review was fixed and regression-tested (commits 20ab3cd/b47ad73).

## 4. E10 — context orchestrator (prompt-injection boundary)
Allow-list of exactly four read-only operations; tenant scope not model-suppliable;
token budget refuse-and-refine; delimited data blocks with marker-forgery
neutralization; injection regression suite (unit + live). Reviewer: Fable (approve).
VERIFY YOURSELF: read src/services/orchestrator/prompt.py + dispatcher.py and run
`pytest tests/unit/services/orchestrator/test_injection_regression.py -v`.

## Accepted process defects (recorded, not hidden)
- E04: unit tests landed in one commit AFTER implementation commits (TDD-history
  violation). Accepted rather than rewriting shared history; all gates green.
- E03: commits reconstructed at epic completion (disclosed in commit bodies);
  red state is structural and machine-verifiable.
- E07: its criteria-7/12 acceptance edits were swept into E05 commit 53dec99 by a
  concurrent-staging accident (content verified E07's, disclosed).

## Deviations from MODELS.md the human should ratify
- Cross-FAMILY review was impossible with an all-Claude team (user-specified);
  approximated as cross-MODEL review (Sonnet↔Opus↔Fable). §1's different-family
  rule is waived for this program run.
- The architecture doc and client draft v0.2 were absent; specs/SKELETON-CRITERIA.md
  and specs/FIXTURES-SPEC.md are reconstructions from the epics and must be
  reconciled against the originals when available. targets.json values are
  placeholders pending client agreement (marked TODO).
