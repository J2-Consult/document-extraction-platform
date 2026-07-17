"""THE typed read-side query module for the E07 query surface.

This is the only sanctioned read path over the projections and their views —
mapping (E09), the context orchestrator (E10), and the embedding pipeline
(E11) call these functions; direct table access from services fails review.
The function set is designed around E10's four allow-listed retrieval
operations (`get_document_value`, `get_document_section`,
`search_document_sections`, `get_provenance` — provenance rides on every
`DocumentValueRow`).

Security model: every statement is parameterized (no string-built SQL, no
identifiers from inputs) and runs on the CALLER's connection — tenant scope
comes from ``app.tenant_id`` set via `adapters.postgres.session`, enforced by
RLS through the ``security_invoker`` views, never from a function argument a
model could supply. Resolution is selection, never merge: the
``resolved_active_masks`` view exposes exactly one mask's entries per
(template, system_context).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psycopg

# Exported so the EXPLAIN-based regression test pins the exact production read
# path (plan must touch projection tables, never expand jsonb arrays).
SELECT_DOCUMENT_VALUES_SQL = """
SELECT tenant_id, document_id, template_id, template_version,
       content_id, content_version, element_id, value, state,
       confidence_raw, confidence_calibrated, provenance
FROM document_values
WHERE document_id = %(document_id)s
ORDER BY element_id
"""

_SELECT_DOCUMENT_VALUE_BY_ROLE = """
SELECT dv.tenant_id, dv.document_id, dv.template_id, dv.template_version,
       dv.content_id, dv.content_version, dv.element_id, dv.value, dv.state,
       dv.confidence_raw, dv.confidence_calibrated, dv.provenance
FROM document_values dv
JOIN resolved_active_masks ram
  ON ram.template_id = dv.template_id
 AND ram.template_version = dv.template_version
 AND ram.element_id = dv.element_id
WHERE dv.document_id = %(document_id)s
  AND ram.system_context = %(system_context)s
  AND ram.semantic_role = %(semantic_role)s
ORDER BY dv.element_id
LIMIT 1
"""

_MASK_ENTRY_COLUMNS = """
       tenant_id, mask_id, mask_version, scope, template_id, template_version,
       system_context, element_id, semantic_role, target_schema, target_field,
       target_datatype, enum_map, section_path, origin, inherited_from_mask_id,
       inherited_from_version, overridden, validated_by
"""

_SELECT_MASK_ENTRIES = f"""
SELECT {_MASK_ENTRY_COLUMNS}
FROM mask_entries
WHERE mask_id = %(mask_id)s AND mask_version = %(mask_version)s
ORDER BY element_id
"""

_SELECT_MASK_ENTRIES_BY_OVERRIDDEN = f"""
SELECT {_MASK_ENTRY_COLUMNS}
FROM mask_entries
WHERE mask_id = %(mask_id)s AND mask_version = %(mask_version)s
  AND overridden = %(overridden)s
ORDER BY element_id
"""

_SELECT_RESOLVED_MASK = f"""
SELECT {_MASK_ENTRY_COLUMNS}
FROM resolved_active_masks
WHERE template_id = %(template_id)s
  AND template_version = %(template_version)s
  AND system_context = %(system_context)s
ORDER BY element_id
"""

# ADR 20: "toggle the baseline / show my changes" is a WHERE clause over the
# selected mask's attribution — never a runtime merge of mask arrays.
_SELECT_BASELINE_TOGGLE = f"""
SELECT {_MASK_ENTRY_COLUMNS}
FROM resolved_active_masks
WHERE template_id = %(template_id)s
  AND template_version = %(template_version)s
  AND system_context = %(system_context)s
  AND overridden
ORDER BY element_id
"""

# Section reads resolve through `resolved_active_masks` — ONE selected mask's
# entries per (template, system_context), never a merge over mask_entries — so
# a customer effective mask existing alongside the vendor baseline yields one
# row per section, with semantic_role/system_context from the selected mask
# only. Template matching: a templated document joins its own template's
# selected mask; an untemplated document (documents.template_id IS NULL, e.g.
# fingerprint-unrouted uploads such as doc_mbr001) matches by element identity
# alone — element ids exist only in the template that defined them, and
# resolution has already collapsed each (template, context) to a single mask.
_SECTION_COLUMNS = """
SELECT dv.tenant_id, dv.document_id, dv.element_id, ram.section_path,
       ram.semantic_role, ram.system_context, dv.value, dv.state, dv.provenance
FROM document_values dv
JOIN resolved_active_masks ram
  ON ram.element_id = dv.element_id
 AND ram.section_path IS NOT NULL
 AND (dv.template_id IS NULL
      OR (ram.template_id = dv.template_id AND ram.template_version = dv.template_version))
"""

_SELECT_DOCUMENT_SECTION = (
    _SECTION_COLUMNS
    + """
WHERE dv.document_id = %(document_id)s
  AND ram.section_path = %(section_path)s
ORDER BY dv.element_id
"""
)

# ILIKE wildcards are anchored around the bound parameter; '%%' is the escaped
# literal '%' in a psycopg query string. A '%' inside the user's query text is
# a wildcard within the search — a search-semantics choice, not SQL injection.
_SEARCH_SECTIONS = (
    _SECTION_COLUMNS
    + """
WHERE dv.value ILIKE '%%' || %(query)s || '%%'
"""
)

_SEARCH_SECTIONS_TAIL = """
ORDER BY dv.document_id, ram.section_path
LIMIT %(limit)s
"""

_SEARCH_DOCUMENT_FILTER = "  AND dv.document_id = %(document_id)s\n"

MAX_SEARCH_LIMIT = 100


@dataclass(frozen=True, slots=True)
class DocumentValueRow:
    """One extracted value of a document, provenance included (E10's citation source)."""

    tenant_id: str
    document_id: str
    template_id: str | None
    template_version: int | None
    content_id: str
    content_version: int
    element_id: str
    value: str | None
    state: str
    confidence_raw: float
    confidence_calibrated: float
    provenance: dict[str, Any]


@dataclass(frozen=True, slots=True)
class MaskEntryRecord:
    """One mask entry as read back from `mask_entries` or `resolved_active_masks`."""

    tenant_id: str | None
    mask_id: str
    mask_version: int
    scope: str
    template_id: str
    template_version: int
    system_context: str
    element_id: str
    semantic_role: str
    target_schema: str
    target_field: str
    target_datatype: str
    enum_map: dict[str, Any] | None
    section_path: str | None
    origin: str
    inherited_from_mask_id: str | None
    inherited_from_version: int | None
    overridden: bool
    validated_by: str | None


@dataclass(frozen=True, slots=True)
class DocumentSectionRow:
    """One section-addressed value (element joined to its mask entry's section_path)."""

    tenant_id: str
    document_id: str
    element_id: str
    section_path: str
    semantic_role: str
    system_context: str
    value: str | None
    state: str
    provenance: dict[str, Any]


def get_document_values(conn: psycopg.Connection[Any], document_id: str) -> tuple[DocumentValueRow, ...]:
    """All extracted values of a document through `document_values` (RLS applies)."""
    cursor = conn.execute(SELECT_DOCUMENT_VALUES_SQL, {"document_id": document_id})
    return tuple(DocumentValueRow(*row) for row in cursor.fetchall())


def get_document_value(
    conn: psycopg.Connection[Any],
    document_id: str,
    system_context: str,
    semantic_role: str,
) -> DocumentValueRow | None:
    """E10 retrieval op: one value addressed by semantic role.

    The role is resolved through the ONE selected mask (`resolved_active_masks`):
    with tenant context set that is the customer's materialized effective mask,
    otherwise the vendor baseline — a role that only exists in the non-selected
    mask does not resolve (selection, never merge).
    """
    cursor = conn.execute(
        _SELECT_DOCUMENT_VALUE_BY_ROLE,
        {"document_id": document_id, "system_context": system_context, "semantic_role": semantic_role},
    )
    row = cursor.fetchone()
    return DocumentValueRow(*row) if row is not None else None


def get_mask_entries(
    conn: psycopg.Connection[Any],
    mask_id: str,
    mask_version: int,
    *,
    overridden: bool | None = None,
) -> tuple[MaskEntryRecord, ...]:
    """Entries of one specific mask version, optionally filtered by attribution."""
    if overridden is None:
        cursor = conn.execute(_SELECT_MASK_ENTRIES, {"mask_id": mask_id, "mask_version": mask_version})
    else:
        cursor = conn.execute(
            _SELECT_MASK_ENTRIES_BY_OVERRIDDEN,
            {"mask_id": mask_id, "mask_version": mask_version, "overridden": overridden},
        )
    return tuple(MaskEntryRecord(*row) for row in cursor.fetchall())


def resolve_active_mask(
    conn: psycopg.Connection[Any],
    template_id: str,
    template_version: int,
    system_context: str,
) -> tuple[MaskEntryRecord, ...]:
    """The selected mask's entries for a template/context (exactly one mask's).

    Selection order comes from `resolved_active_masks`: the invoking tenant's
    active customer-scope mask when one exists, else the vendor baseline.
    """
    cursor = conn.execute(
        _SELECT_RESOLVED_MASK,
        {"template_id": template_id, "template_version": template_version, "system_context": system_context},
    )
    return tuple(MaskEntryRecord(*row) for row in cursor.fetchall())


def baseline_toggle(
    conn: psycopg.Connection[Any],
    template_id: str,
    template_version: int,
    system_context: str,
) -> tuple[MaskEntryRecord, ...]:
    """The customer-authored/overridden subset of the selected mask (ADR 20)."""
    cursor = conn.execute(
        _SELECT_BASELINE_TOGGLE,
        {"template_id": template_id, "template_version": template_version, "system_context": system_context},
    )
    return tuple(MaskEntryRecord(*row) for row in cursor.fetchall())


def get_document_section(
    conn: psycopg.Connection[Any],
    document_id: str,
    section_path: str,
) -> tuple[DocumentSectionRow, ...]:
    """E10 retrieval op: the value(s) of one section-addressed element only."""
    cursor = conn.execute(
        _SELECT_DOCUMENT_SECTION,
        {"document_id": document_id, "section_path": section_path},
    )
    return tuple(DocumentSectionRow(*row) for row in cursor.fetchall())


def search_document_sections(
    conn: psycopg.Connection[Any],
    *,
    query: str,
    limit: int,
    document_id: str | None = None,
) -> tuple[DocumentSectionRow, ...]:
    """E10 retrieval op: bounded substring search over section-addressed values."""
    if not 1 <= limit <= MAX_SEARCH_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_SEARCH_LIMIT}, got {limit}")
    params: dict[str, Any] = {"query": query, "limit": limit}
    sql = _SEARCH_SECTIONS
    if document_id is not None:
        sql += _SEARCH_DOCUMENT_FILTER
        params["document_id"] = document_id
    cursor = conn.execute(sql + _SEARCH_SECTIONS_TAIL, params)
    return tuple(DocumentSectionRow(*row) for row in cursor.fetchall())
