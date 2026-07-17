-- E07 migration 0004 — relational projections and the document_values query surface.
--
-- Design notes
-- ------------
-- * Projections, not sources of truth. extracted_values and mask_entries are
--   derived ONLY from the immutable artifact bodies by the projection writer
--   (src/services/projection/); they carry no state of their own and may be
--   deleted and re-derived at any time. Unlike the versioned artifact tables
--   they are therefore NOT append-only: the writer converges by
--   delete-and-reinsert of a whole (tenant, document/mask, version) scope
--   inside one transaction.
-- * Tenant-first keys, FORCE RLS, and least-privilege grants follow E02's
--   0002_rls_grants.sql exactly. mask_entries mirrors decoder_masks (vendor
--   rows have tenant_id NULL, readable by every tenant role, written only by
--   the admin path); extracted_values mirrors documents (strict single-tenant).
-- * Resolution is SELECTION, never merge (ADR: selection-not-merge). The
--   resolved_active_masks view picks exactly ONE mask per
--   (template_id, template_version, system_context): the invoking tenant's
--   active customer-scope materialized effective mask when one exists,
--   OTHERWISE the vendor baseline — and exposes that single mask's entries
--   with attribution (origin, inherited_from, overridden) so "toggle the
--   baseline / show my changes" are WHERE clauses, not merge logic.
-- * Both views set security_invoker = true: the invoking role's RLS applies,
--   never the view owner's — a superuser-owned view must not lend its RLS
--   bypass to anyone.
-- * Idempotent: safe to re-run against a dirty database.

CREATE TABLE IF NOT EXISTS extracted_values (
    tenant_id             text    NOT NULL,
    document_id           text    NOT NULL,
    content_id            text    NOT NULL,
    content_version       integer NOT NULL,
    element_id            text    NOT NULL,
    value                 text,
    state                 text    NOT NULL,
    confidence_raw        double precision NOT NULL,
    confidence_calibrated double precision NOT NULL,
    provenance            jsonb   NOT NULL,   -- no value or blank assertion without provenance
    PRIMARY KEY (tenant_id, document_id, content_id, content_version, element_id),
    CONSTRAINT extracted_values_version_positive CHECK (content_version >= 1),
    CONSTRAINT extracted_values_state_valid
        CHECK (state IN ('present', 'empty', 'not_applicable', 'unreadable', 'not_found')),
    -- E01 state/value legality, restated relationally: present <=> value non-null.
    CONSTRAINT extracted_values_state_value_legal CHECK ((state = 'present') = (value IS NOT NULL)),
    CONSTRAINT extracted_values_confidence_range
        CHECK (confidence_raw BETWEEN 0 AND 1 AND confidence_calibrated BETWEEN 0 AND 1)
);

CREATE TABLE IF NOT EXISTS mask_entries (
    tenant_id              text,               -- NULL <=> scope = 'vendor' (as decoder_masks)
    mask_id                text    NOT NULL,
    mask_version           integer NOT NULL,
    scope                  text    NOT NULL,
    template_id            text    NOT NULL,
    template_version       integer NOT NULL,
    system_context         text    NOT NULL,
    element_id             text    NOT NULL,
    semantic_role          text    NOT NULL,
    target_schema          text    NOT NULL,   -- wire key "schema" in the artifact body
    target_field           text    NOT NULL,
    target_datatype        text    NOT NULL,
    enum_map               jsonb,
    section_path           text,
    origin                 text    NOT NULL,
    inherited_from_mask_id text,
    inherited_from_version integer,
    overridden             boolean NOT NULL,
    validated_by           text,
    CONSTRAINT mask_entries_version_positive CHECK (mask_version >= 1),
    CONSTRAINT mask_entries_scope_valid CHECK (scope IN ('vendor', 'customer')),
    CONSTRAINT mask_entries_scope_tenant CHECK ((scope = 'vendor') = (tenant_id IS NULL)),
    CONSTRAINT mask_entries_origin_valid CHECK (origin IN ('vendor', 'customer')),
    -- E01 attribution invariants, restated relationally.
    CONSTRAINT mask_entries_overridden_has_inheritance
        CHECK (NOT overridden OR inherited_from_mask_id IS NOT NULL),
    CONSTRAINT mask_entries_inheritance_pair
        CHECK ((inherited_from_mask_id IS NULL) = (inherited_from_version IS NULL))
);

-- Tenant-first composite identity (NULLS NOT DISTINCT: vendor rows collide
-- instead of silently duplicating — same pattern as decoder_masks).
CREATE UNIQUE INDEX IF NOT EXISTS mask_entries_identity_key
    ON mask_entries (tenant_id, mask_id, mask_version, element_id) NULLS NOT DISTINCT;

-- Resolution path: find a mask's entries by the template/context it decodes.
CREATE INDEX IF NOT EXISTS mask_entries_by_template_context
    ON mask_entries (template_id, template_version, system_context);

ALTER TABLE extracted_values ENABLE ROW LEVEL SECURITY;
ALTER TABLE extracted_values FORCE  ROW LEVEL SECURITY;
ALTER TABLE mask_entries     ENABLE ROW LEVEL SECURITY;
ALTER TABLE mask_entries     FORCE  ROW LEVEL SECURITY;

-- extracted_values: strict single-tenant, both ways (like documents in 0002).
DROP POLICY IF EXISTS p_extracted_values_tenant ON extracted_values;
CREATE POLICY p_extracted_values_tenant ON extracted_values
    FOR ALL TO api_service, worker, orchestrator_readonly
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

-- mask_entries: vendor rows (tenant_id NULL) readable by all tenant roles; a
-- tenant reads its own rows and writes/deletes ONLY its own (vendor projection
-- rows are written by the admin path, exactly like vendor decoder_masks rows).
DROP POLICY IF EXISTS p_mask_entries_read_tenant ON mask_entries;
CREATE POLICY p_mask_entries_read_tenant ON mask_entries
    FOR SELECT TO api_service, worker, orchestrator_readonly
    USING (tenant_id IS NULL OR tenant_id = current_setting('app.tenant_id', true));

DROP POLICY IF EXISTS p_mask_entries_write_tenant ON mask_entries;
CREATE POLICY p_mask_entries_write_tenant ON mask_entries
    FOR INSERT TO api_service, worker
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

DROP POLICY IF EXISTS p_mask_entries_delete_tenant ON mask_entries;
CREATE POLICY p_mask_entries_delete_tenant ON mask_entries
    FOR DELETE TO api_service, worker
    USING (tenant_id = current_setting('app.tenant_id', true));

-- ---------------------------------------------------------------------------
-- Views. security_invoker = true on BOTH: RLS is evaluated as the invoking
-- role, so the (superuser-owned) views can never widen anyone's visibility.
-- ---------------------------------------------------------------------------

-- Selection, never merge: rank the visible active masks for each
-- (template_id, template_version, system_context) — the invoking tenant's
-- customer mask outranks the vendor baseline — and expose ONLY the top-ranked
-- mask's entries. The explicit tenant predicate keeps selection semantics
-- correct even for roles that bypass RLS (admin paths).
CREATE OR REPLACE VIEW resolved_active_masks WITH (security_invoker = true) AS
WITH visible AS (
    SELECT m.tenant_id, m.mask_id, m.version, m.scope,
           m.template_id, m.template_version, m.system_context
    FROM decoder_masks m
    WHERE m.active
      AND (m.tenant_id IS NULL OR m.tenant_id = current_setting('app.tenant_id', true))
),
selected AS (
    SELECT v.*,
           row_number() OVER (
               PARTITION BY v.template_id, v.template_version, v.system_context
               ORDER BY (v.scope = 'customer') DESC
           ) AS pick
    FROM visible v
)
SELECT s.tenant_id,
       s.mask_id,
       s.version AS mask_version,
       s.scope,
       s.template_id,
       s.template_version,
       s.system_context,
       e.element_id,
       e.semantic_role,
       e.target_schema,
       e.target_field,
       e.target_datatype,
       e.enum_map,
       e.section_path,
       e.origin,
       e.inherited_from_mask_id,
       e.inherited_from_version,
       e.overridden,
       e.validated_by
FROM selected s
JOIN mask_entries e
  ON e.tenant_id IS NOT DISTINCT FROM s.tenant_id
 AND e.mask_id = s.mask_id
 AND e.mask_version = s.version
WHERE s.pick = 1;

-- The query surface everything downstream reads: one row per extracted value
-- of the document's current content version, straight from the projections —
-- never from jsonb arrays.
CREATE OR REPLACE VIEW document_values WITH (security_invoker = true) AS
SELECT d.tenant_id,
       d.document_id,
       d.template_id,
       d.template_version,
       ev.content_id,
       ev.content_version,
       ev.element_id,
       ev.value,
       ev.state,
       ev.confidence_raw,
       ev.confidence_calibrated,
       ev.provenance
FROM documents d
JOIN extracted_values ev
  ON ev.tenant_id = d.tenant_id
 AND ev.document_id = d.document_id
 AND ev.content_id = d.content_id
 AND ev.content_version = d.content_version;

-- ---------------------------------------------------------------------------
-- Grants (least privilege; revoke-then-grant so re-runs converge).
-- api_service/worker write projections (delete-and-reinsert needs DELETE —
-- projections are derived, not versioned artifacts, so this does not weaken
-- the append-only rule). orchestrator_readonly reads only. synthesis gets
-- nothing here: projections are per-tenant derived data, not shared knowledge.
-- ---------------------------------------------------------------------------
REVOKE ALL ON extracted_values, mask_entries, resolved_active_masks, document_values
    FROM api_service, worker, orchestrator_readonly, synthesis;

GRANT SELECT, INSERT, DELETE ON extracted_values, mask_entries TO api_service, worker;
GRANT SELECT ON extracted_values, mask_entries TO orchestrator_readonly;
GRANT SELECT ON resolved_active_masks, document_values TO api_service, worker, orchestrator_readonly;
