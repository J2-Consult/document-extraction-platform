"""Retrieval port (epic E10): the ONLY operations the LLM-facing context
orchestrator may invoke. This module is the trust boundary's vocabulary.

ALLOW-LIST (complete and closed — this is the whole retrieval surface):

1. ``get_document_value(document_id, system_context, semantic_role)``
   -> ``RetrievedValue | None`` — one value addressed by semantic role,
   resolved through the ONE selected mask (selection, never merge).
2. ``get_document_section(document_id, section_path)``
   -> ``tuple[RetrievedSection, ...]`` — the value(s) of one
   section-addressed element only; never a whole document.
3. ``search_document_sections(filters, query, limit)``
   -> ``tuple[RetrievedSection, ...]`` — bounded substring search over
   section-addressed values; ``filters`` keys are allow-listed
   (``document_id`` only), ``limit`` is validated and capped.
4. ``get_provenance(document_id, element_id)``
   -> ``RetrievedProvenance | None`` — the provenance record of one
   already-identified element (the citation source).

Adding an operation = a NEW registration in
``services.orchestrator.dispatcher.build_registry`` plus review — never an
edit to the dispatcher (open/closed; the allow-list is data).

Security invariants (review-blocking):

- TENANT SCOPE IS NOT A PARAMETER. No operation accepts a tenant_id in any
  form; tenant context is bound to the underlying session by the composition
  root (``adapters.postgres.session.tenant_transaction``), outside model
  control. A tenant parameter supplied at dispatch is an unknown-parameter
  error.
- Read-only and parameterized: implementations go through
  ``adapters.postgres.queries`` (E07's typed read seam) only — no SQL
  surface, no model-generated SQL, no whole-document fetch.
- Result-limited: every operation returns a bounded number of rows.
- Every retrieved value carries provenance; retrieved text is DATA, never
  instructions (``services.orchestrator.prompt`` wraps it in delimited
  blocks before it goes anywhere near a model).

Pure interface: stdlib + dataclasses only; no I/O, no framework imports.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class RetrievedValue:
    """One semantically addressed document value, provenance included."""

    document_id: str
    element_id: str
    value: str | None
    state: str
    confidence_calibrated: float
    provenance: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class RetrievedSection:
    """One section-addressed value (element joined to its mask entry's section_path)."""

    document_id: str
    element_id: str
    section_path: str
    semantic_role: str
    system_context: str
    value: str | None
    state: str
    provenance: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class RetrievedProvenance:
    """The provenance record of one element — the citation an answer must carry."""

    document_id: str
    element_id: str
    provenance: Mapping[str, Any]


@runtime_checkable
class RetrievalOperations(Protocol):
    """Exactly four operations; see the module docstring for the allow-list
    and its security invariants (no tenant parameter, read-only, bounded)."""

    def get_document_value(self, document_id: str, system_context: str, semantic_role: str) -> RetrievedValue | None:
        """One value addressed by semantic role through the selected mask."""
        ...

    def get_document_section(self, document_id: str, section_path: str) -> tuple[RetrievedSection, ...]:
        """The value(s) of one section-addressed element only."""
        ...

    def search_document_sections(
        self, filters: Mapping[str, str], query: str, limit: int
    ) -> tuple[RetrievedSection, ...]:
        """Bounded substring search over section-addressed values."""
        ...

    def get_provenance(self, document_id: str, element_id: str) -> RetrievedProvenance | None:
        """The provenance record of one already-identified element."""
        ...
