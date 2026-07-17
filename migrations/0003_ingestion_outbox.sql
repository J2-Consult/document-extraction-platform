-- E03 migration 0003 — transactional outbox for ingestion, plus the
-- idempotency guarantees `IngestionRepository.register_upload` relies on.
--
-- Design notes
-- ------------
-- * ingestion_outbox: written in the SAME transaction as the documents/jobs
--   rows it accompanies (`register_upload`), then drained by the outbox
--   relay (src/services/ingestion/outbox_relay.py) into the JobQueue. Tenant-
--   first key, FORCE RLS, least-privilege grants — same pattern as E02's
--   0002_rls_grants.sql.
-- * Idempotency: `document_id`/`job_id`/`outbox_id` are deterministic hashes
--   of (tenant_id, source_sha256, intent) computed by the caller
--   (services/ingestion/identity.py). `documents`' existing primary key
--   (tenant_id, document_id, version) and `jobs`' existing primary key
--   (tenant_id, job_id) already give `INSERT ... ON CONFLICT DO NOTHING` a
--   natural arbiter for those two tables — no new index needed, and this
--   migration does not alter either table. `ingestion_outbox` gets the same
--   treatment via its own primary key below.
-- * Idempotent: safe to re-run against a dirty database.

CREATE TABLE IF NOT EXISTS ingestion_outbox (
    tenant_id       text        NOT NULL,
    outbox_id       text        NOT NULL,
    document_id     text        NOT NULL,
    job_id          text        NOT NULL,
    job_kind        text        NOT NULL,
    idempotency_key text        NOT NULL,
    payload         jsonb       NOT NULL DEFAULT '{}'::jsonb,
    relayed         boolean     NOT NULL DEFAULT false,
    created_at      timestamptz NOT NULL DEFAULT now(),
    relayed_at      timestamptz,
    PRIMARY KEY (tenant_id, outbox_id)
);

CREATE INDEX IF NOT EXISTS ingestion_outbox_pending
    ON ingestion_outbox (tenant_id, created_at)
    WHERE NOT relayed;

ALTER TABLE ingestion_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingestion_outbox FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_ingestion_outbox_tenant ON ingestion_outbox;
CREATE POLICY p_ingestion_outbox_tenant ON ingestion_outbox
    FOR ALL TO api_service, worker
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

REVOKE ALL ON ingestion_outbox FROM api_service, worker;

-- api_service: writes the outbox row as part of registration (no delete —
-- append-only in spirit, relayed rows are updated in place via `relayed`).
GRANT SELECT, INSERT, UPDATE ON ingestion_outbox TO api_service;

-- worker: drains (reads) and marks rows relayed.
GRANT SELECT, INSERT, UPDATE ON ingestion_outbox TO worker;
