-- E02 migration 0002 — row-level security policies and least-privilege grants.
--
-- Roles (api_service, worker, orchestrator_readonly, synthesis) are created by the
-- migration runner (src/adapters/postgres/migrator.py) BEFORE this file is applied,
-- because their passwords come from the environment.
--
-- ENABLE + FORCE RLS on every tenant-owned table. FORCE makes the policies bind even
-- for the table owner; superusers (migration/seed paths only) still bypass RLS, which
-- is how vendor/shared rows get written. All policies key on
-- current_setting('app.tenant_id', true) — NULL when unset, so "no context" sees no
-- tenant rows. Policies are scoped per role so the synthesis role's narrow view cannot
-- be widened by simply setting app.tenant_id.

ALTER TABLE templates      ENABLE ROW LEVEL SECURITY;
ALTER TABLE templates      FORCE  ROW LEVEL SECURITY;
ALTER TABLE decoder_masks  ENABLE ROW LEVEL SECURITY;
ALTER TABLE decoder_masks  FORCE  ROW LEVEL SECURITY;
ALTER TABLE documents      ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents      FORCE  ROW LEVEL SECURITY;
ALTER TABLE jobs           ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs           FORCE  ROW LEVEL SECURITY;
ALTER TABLE review_items   ENABLE ROW LEVEL SECURITY;
ALTER TABLE review_items   FORCE  ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- templates: vendor rows (tenant_id NULL) readable by all tenant roles; a tenant
-- reads its own private rows and inserts ONLY its own (vendor rows => admin path).
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS p_templates_read_tenant ON templates;
CREATE POLICY p_templates_read_tenant ON templates
    FOR SELECT TO api_service, worker, orchestrator_readonly
    USING (tenant_id IS NULL OR tenant_id = current_setting('app.tenant_id', true));

DROP POLICY IF EXISTS p_templates_write_tenant ON templates;
CREATE POLICY p_templates_write_tenant ON templates
    FOR INSERT TO api_service, worker
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

-- synthesis: shared vendor templates ONLY, regardless of app.tenant_id.
DROP POLICY IF EXISTS p_templates_read_synthesis ON templates;
CREATE POLICY p_templates_read_synthesis ON templates
    FOR SELECT TO synthesis
    USING (tenant_id IS NULL);

-- ---------------------------------------------------------------------------
-- decoder_masks: same shape; synthesis is restricted to vendor-scope masks.
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS p_masks_read_tenant ON decoder_masks;
CREATE POLICY p_masks_read_tenant ON decoder_masks
    FOR SELECT TO api_service, worker, orchestrator_readonly
    USING (tenant_id IS NULL OR tenant_id = current_setting('app.tenant_id', true));

DROP POLICY IF EXISTS p_masks_write_tenant ON decoder_masks;
CREATE POLICY p_masks_write_tenant ON decoder_masks
    FOR INSERT TO api_service, worker
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

-- synthesis: vendor-scope masks ONLY; never a customer-scope mask.
DROP POLICY IF EXISTS p_masks_read_synthesis ON decoder_masks;
CREATE POLICY p_masks_read_synthesis ON decoder_masks
    FOR SELECT TO synthesis
    USING (scope = 'vendor');

-- ---------------------------------------------------------------------------
-- documents / jobs / review_items: strict single-tenant. Every row action is
-- gated on the tenant context both ways (USING for read/update/delete visibility,
-- WITH CHECK so a tenant cannot INSERT/UPDATE a row into another tenant).
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS p_documents_tenant ON documents;
CREATE POLICY p_documents_tenant ON documents
    FOR ALL TO api_service, worker, orchestrator_readonly
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

DROP POLICY IF EXISTS p_jobs_tenant ON jobs;
CREATE POLICY p_jobs_tenant ON jobs
    FOR ALL TO api_service, worker, orchestrator_readonly
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

DROP POLICY IF EXISTS p_review_items_tenant ON review_items;
CREATE POLICY p_review_items_tenant ON review_items
    FOR ALL TO api_service, worker, orchestrator_readonly
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

-- ---------------------------------------------------------------------------
-- Grants (least privilege). Revoke-then-grant so re-runs converge to this exact set.
-- Note: RLS is the isolation control; grants are defence in depth. Withholding
-- UPDATE/DELETE on the versioned artifact tables reinforces append-only.
-- ---------------------------------------------------------------------------
REVOKE ALL ON templates, decoder_masks, documents, jobs, review_items
    FROM api_service, worker, orchestrator_readonly, synthesis;

-- api_service: append-only insert on artifacts; full DML on operational tables.
GRANT SELECT, INSERT                 ON templates, decoder_masks       TO api_service;
GRANT SELECT, INSERT, UPDATE, DELETE ON documents, jobs, review_items  TO api_service;

-- worker: reads artifacts, appends artifacts, advances operational rows (no delete).
GRANT SELECT, INSERT         ON templates, decoder_masks       TO worker;
GRANT SELECT, INSERT, UPDATE ON documents, jobs, review_items  TO worker;

-- orchestrator_readonly: SELECT only, everywhere.
GRANT SELECT ON templates, decoder_masks, documents, jobs, review_items TO orchestrator_readonly;

-- synthesis: SELECT only, and ONLY on the shared-knowledge tables. No grant on
-- documents/jobs/review_items at all; RLS further narrows it to vendor rows.
GRANT SELECT ON templates, decoder_masks TO synthesis;
