-- E02 migration 0001 — tenant-isolated schema.
--
-- Design notes
-- ------------
-- * Tenant-first keys. Every operational table (documents, jobs, review_items)
--   carries a NOT NULL tenant_id as the first PK column. The versioned artifact
--   tables (templates, decoder_masks) allow tenant_id NULL for vendor/shared rows;
--   SQL forbids NULL in PRIMARY KEY columns, so their tenant-first composite key is
--   enforced as a UNIQUE index with NULLS NOT DISTINCT (so two vendor rows sharing
--   an id/version collide as intended).
-- * Append-only. Versioned artifact BODIES are immutable — enforced by a trigger
--   (reject_body_mutation) AND by withholding UPDATE/DELETE grants from the service
--   roles (see 0002). New versions are appended as new rows.
-- * Vendor rows. templates/decoder_masks with tenant_id NULL are the shared vendor
--   baseline; RLS (0002) makes them readable by all tenants, writable only by admin.
-- * Idempotent: safe to re-run against a dirty database.

CREATE TABLE IF NOT EXISTS templates (
    tenant_id     text,                                   -- NULL => vendor/shared
    template_id   text        NOT NULL,
    version       integer     NOT NULL,
    doc_class     text        NOT NULL,
    fingerprint   text,
    body          jsonb       NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT templates_version_positive CHECK (version >= 1)
);

-- Tenant-first composite identity (NULLS NOT DISTINCT: vendor rows with the same
-- template_id/version collide instead of silently duplicating).
CREATE UNIQUE INDEX IF NOT EXISTS templates_identity_key
    ON templates (tenant_id, template_id, version) NULLS NOT DISTINCT;

CREATE TABLE IF NOT EXISTS decoder_masks (
    tenant_id        text,                                -- NULL <=> scope = 'vendor'
    mask_id          text        NOT NULL,
    version          integer     NOT NULL,
    scope            text        NOT NULL,
    template_id      text        NOT NULL,
    template_version integer     NOT NULL,
    system_context   text        NOT NULL,
    active           boolean     NOT NULL DEFAULT true,
    body             jsonb       NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT decoder_masks_version_positive CHECK (version >= 1),
    CONSTRAINT decoder_masks_scope_valid CHECK (scope IN ('vendor', 'customer')),
    -- Vendor scope iff no tenant; customer scope iff a tenant owns it.
    CONSTRAINT decoder_masks_scope_tenant CHECK ((scope = 'vendor') = (tenant_id IS NULL))
);

CREATE UNIQUE INDEX IF NOT EXISTS decoder_masks_identity_key
    ON decoder_masks (tenant_id, mask_id, version) NULLS NOT DISTINCT;

-- At most one ACTIVE mask per (tenant, template, system_context). NULLS NOT DISTINCT
-- so the vendor baseline (tenant_id NULL) is also single-active per context.
CREATE UNIQUE INDEX IF NOT EXISTS decoder_masks_one_active_per_context
    ON decoder_masks (tenant_id, template_id, system_context) NULLS NOT DISTINCT
    WHERE active;

CREATE TABLE IF NOT EXISTS documents (
    tenant_id        text        NOT NULL,
    document_id      text        NOT NULL,
    version          integer     NOT NULL DEFAULT 1,
    template_id      text,
    template_version integer,
    content_id       text,
    content_version  integer,
    source_sha256    text,
    state            text        NOT NULL DEFAULT 'registered',
    body             jsonb       NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, document_id, version)
);

CREATE TABLE IF NOT EXISTS jobs (
    tenant_id   text        NOT NULL,
    job_id      text        NOT NULL,
    document_id text,
    kind        text,
    state       text        NOT NULL DEFAULT 'queued',
    body        jsonb       NOT NULL DEFAULT '{}'::jsonb,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, job_id)
);

CREATE TABLE IF NOT EXISTS review_items (
    tenant_id      text        NOT NULL,
    review_item_id text        NOT NULL,
    document_id    text,
    element_id     text,
    state          text        NOT NULL DEFAULT 'pending',
    body           jsonb       NOT NULL DEFAULT '{}'::jsonb,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, review_item_id)
);

-- Append-only enforcement for versioned artifact bodies. Blocks DELETE outright and
-- any UPDATE that would mutate the body or the version identity. Toggling operational
-- columns (e.g. decoder_masks.active) stays allowed for future activation flows.
CREATE OR REPLACE FUNCTION reject_body_mutation() RETURNS trigger
    LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'append-only: DELETE of versioned artifact % is forbidden', TG_TABLE_NAME
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF NEW.body IS DISTINCT FROM OLD.body
       OR NEW.version IS DISTINCT FROM OLD.version THEN
        RAISE EXCEPTION 'append-only: body/version of versioned artifact % is immutable', TG_TABLE_NAME
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_templates_append_only ON templates;
CREATE TRIGGER trg_templates_append_only
    BEFORE UPDATE OR DELETE ON templates
    FOR EACH ROW EXECUTE FUNCTION reject_body_mutation();

DROP TRIGGER IF EXISTS trg_decoder_masks_append_only ON decoder_masks;
CREATE TRIGGER trg_decoder_masks_append_only
    BEFORE UPDATE OR DELETE ON decoder_masks
    FOR EACH ROW EXECUTE FUNCTION reject_body_mutation();

-- Constraint trigger: a mask referencing a customer-private template MUST be
-- scope='customer' owned by that same tenant. SECURITY DEFINER so the check is
-- authoritative across the RLS boundary (the invoking role may not itself be able
-- to see another tenant's private template). search_path pinned to defeat
-- search-path hijacking of a definer-rights function.
CREATE OR REPLACE FUNCTION enforce_mask_template_scope() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.templates t
        WHERE t.template_id = NEW.template_id
          AND t.version = NEW.template_version
          AND t.tenant_id IS NOT NULL
    ) THEN
        IF NEW.scope <> 'customer'
           OR NOT EXISTS (
                SELECT 1 FROM public.templates t
                WHERE t.template_id = NEW.template_id
                  AND t.version = NEW.template_version
                  AND t.tenant_id = NEW.tenant_id
           ) THEN
            RAISE EXCEPTION
                'mask on a customer-private template must be scope=customer with the owning tenant (E02 invariant)'
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_mask_template_scope ON decoder_masks;
CREATE CONSTRAINT TRIGGER trg_mask_template_scope
    AFTER INSERT OR UPDATE ON decoder_masks
    DEFERRABLE INITIALLY IMMEDIATE
    FOR EACH ROW EXECUTE FUNCTION enforce_mask_template_scope();
