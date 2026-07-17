# E02 — Tenant-aware schema, RLS, roles, isolation suite

**Objective:** the database as the isolation boundary — schema migrations, FORCE RLS, least-privilege roles, and the CI isolation suite that every future PR must keep green.
**Depends on:** E00. **Owned paths:** `migrations/`, `src/adapters/postgres/session.py`, `tests/isolation/`.
**Read first:** architecture doc §5.5.1, §7.4 invariant, §10; v0.2 §8 entirely.

## Scope
- Migrations for `templates`, `documents`, `decoder_masks`, jobs, review_items — tenant-first composite keys per v0.2 §8.1; the unique active-mask-per-context index; the constraint trigger: mask on a customer-private template ⇒ customer scope, same tenant.
- `ENABLE + FORCE ROW LEVEL SECURITY` with `current_setting('app.tenant_id')` policies on every tenant-owned table.
- Roles: `api_service`, `worker`, `orchestrator_readonly`, and **`synthesis`** — synthesis can read templates only where `tenant_id IS NULL` and masks only where `scope='vendor'` (the architecture's absolute isolation invariant, §7.4).
- Transactional tenant-context manager; pool reuse clears/overwrites context (test it).

## Tests first (acceptance: criterion 4 + v0.2 §8.4)
Connect as real restricted roles (never superuser) and prove Tenant A cannot: select B's documents/derived values; resolve B's masks; read B's private templates; see/update B's jobs and review items; infer B's rows via views or error text. Plus:
- `test_synthesis_role_cannot_select_customer_masks_or_private_templates` — this is the invariant the client review omitted; it lives here permanently.
- `test_pool_reuse_does_not_leak_tenant_context`.
- `test_mask_on_private_template_with_wrong_scope_is_rejected_by_trigger`.

## Security
This epic IS the security control. Application filtering is defense-in-depth only; a test that passes because app code filtered is a failing test — assert at the SQL layer.

## Definition of done
`make test-isolation` green with restricted roles; suite wired into CI as a required check for all PRs; criterion 4 unskipped.
