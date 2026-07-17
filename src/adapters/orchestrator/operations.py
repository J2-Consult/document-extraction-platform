"""`PostgresRetrievalOperations`: the retrieval port over E07's query seam.

Implements `ports.retrieval.RetrievalOperations` via
`adapters.postgres.queries` ONLY — the sanctioned typed read-side module.
No SQL lives here; every statement is parameterized inside the seam.

Tenant scope: this adapter takes an already-scoped connection. The
composition root binds `app.tenant_id` transaction-locally via
`adapters.postgres.session.tenant_transaction` BEFORE constructing the
pipeline; RLS on the `security_invoker` views does the enforcement. No
method accepts tenant identity — the port forbids it.

`get_provenance` derives from `DocumentValueRow.provenance` (every projected
value already carries its provenance), so no extra read path is introduced.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import psycopg

import adapters.postgres.queries as queries
from ports.retrieval import RetrievedProvenance, RetrievedSection, RetrievedValue


def _to_value(row: queries.DocumentValueRow) -> RetrievedValue:
    return RetrievedValue(
        document_id=row.document_id,
        element_id=row.element_id,
        value=row.value,
        state=row.state,
        confidence_calibrated=row.confidence_calibrated,
        provenance=row.provenance,
    )


def _to_section(row: queries.DocumentSectionRow) -> RetrievedSection:
    return RetrievedSection(
        document_id=row.document_id,
        element_id=row.element_id,
        section_path=row.section_path,
        semantic_role=row.semantic_role,
        system_context=row.system_context,
        value=row.value,
        state=row.state,
        provenance=row.provenance,
    )


class PostgresRetrievalOperations:
    """The four allow-listed operations, executed on the caller's scoped connection."""

    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self._conn = conn

    def get_document_value(self, document_id: str, system_context: str, semantic_role: str) -> RetrievedValue | None:
        row = queries.get_document_value(self._conn, document_id, system_context, semantic_role)
        return None if row is None else _to_value(row)

    def get_document_section(self, document_id: str, section_path: str) -> tuple[RetrievedSection, ...]:
        rows = queries.get_document_section(self._conn, document_id, section_path)
        return tuple(_to_section(row) for row in rows)

    def search_document_sections(
        self, filters: Mapping[str, str], query: str, limit: int
    ) -> tuple[RetrievedSection, ...]:
        rows = queries.search_document_sections(
            self._conn, query=query, limit=limit, document_id=filters.get("document_id")
        )
        return tuple(_to_section(row) for row in rows)

    def get_provenance(self, document_id: str, element_id: str) -> RetrievedProvenance | None:
        for row in queries.get_document_values(self._conn, document_id):
            if row.element_id == element_id:
                return RetrievedProvenance(document_id=document_id, element_id=element_id, provenance=row.provenance)
        return None
