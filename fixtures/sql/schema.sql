-- Minimal fixture-load schema for the E00 walking-skeleton harness.
-- This is NOT the real system schema (that belongs to E02's migrations); it
-- exists only so `load_fixtures.py` has somewhere to put the fixture bundle
-- for acceptance tests to read back from.

CREATE TABLE IF NOT EXISTS fixture_templates (
    artifact_id text NOT NULL,
    version integer NOT NULL,
    tenant_id text NULL,
    body jsonb NOT NULL,
    PRIMARY KEY (artifact_id, version)
);

CREATE TABLE IF NOT EXISTS fixture_decoder_masks (
    artifact_id text NOT NULL,
    version integer NOT NULL,
    tenant_id text NULL,
    body jsonb NOT NULL,
    PRIMARY KEY (artifact_id, version)
);

CREATE TABLE IF NOT EXISTS fixture_documents (
    artifact_id text NOT NULL,
    version integer NOT NULL,
    tenant_id text NULL,
    body jsonb NOT NULL,
    PRIMARY KEY (artifact_id, version)
);
