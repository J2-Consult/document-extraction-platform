"""Fakes and spies for the E10 retrieval port.

`FakeRetrievalOperations` serves canned rows and records every call (unit
tests, injection regression suite). `RecordingRetrievalOperations` wraps a
real implementation and records operation names only (the criterion-13 spy
proving the answer came via `get_document_value` alone).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ports.retrieval import RetrievalOperations, RetrievedProvenance, RetrievedSection, RetrievedValue


class FakeRetrievalOperations:
    """In-memory `RetrievalOperations`: canned rows in, call log out."""

    def __init__(
        self,
        *,
        values: Mapping[tuple[str, str, str], RetrievedValue] | None = None,
        sections: Mapping[tuple[str, str], tuple[RetrievedSection, ...]] | None = None,
    ) -> None:
        self._values = dict(values or {})
        self._sections = dict(sections or {})
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get_document_value(self, document_id: str, system_context: str, semantic_role: str) -> RetrievedValue | None:
        self.calls.append(
            (
                "get_document_value",
                {"document_id": document_id, "system_context": system_context, "semantic_role": semantic_role},
            )
        )
        return self._values.get((document_id, system_context, semantic_role))

    def get_document_section(self, document_id: str, section_path: str) -> tuple[RetrievedSection, ...]:
        self.calls.append(("get_document_section", {"document_id": document_id, "section_path": section_path}))
        return self._sections.get((document_id, section_path), ())

    def search_document_sections(
        self, filters: Mapping[str, str], query: str, limit: int
    ) -> tuple[RetrievedSection, ...]:
        self.calls.append(("search_document_sections", {"filters": dict(filters), "query": query, "limit": limit}))
        wanted_document = filters.get("document_id")
        hits = [
            section
            for rows in self._sections.values()
            for section in rows
            if section.value is not None
            and query.lower() in section.value.lower()
            and (wanted_document is None or section.document_id == wanted_document)
        ]
        return tuple(hits[:limit])

    def get_provenance(self, document_id: str, element_id: str) -> RetrievedProvenance | None:
        self.calls.append(("get_provenance", {"document_id": document_id, "element_id": element_id}))
        for value in self._values.values():
            if value.document_id == document_id and value.element_id == element_id:
                return RetrievedProvenance(document_id, element_id, value.provenance)
        for rows in self._sections.values():
            for section in rows:
                if section.document_id == document_id and section.element_id == element_id:
                    return RetrievedProvenance(document_id, element_id, section.provenance)
        return None


class RecordingRetrievalOperations:
    """Spy wrapper over a real implementation: records operation names only."""

    def __init__(self, inner: RetrievalOperations) -> None:
        self._inner = inner
        self.operations_called: list[str] = []

    def get_document_value(self, document_id: str, system_context: str, semantic_role: str) -> RetrievedValue | None:
        self.operations_called.append("get_document_value")
        return self._inner.get_document_value(document_id, system_context, semantic_role)

    def get_document_section(self, document_id: str, section_path: str) -> tuple[RetrievedSection, ...]:
        self.operations_called.append("get_document_section")
        return self._inner.get_document_section(document_id, section_path)

    def search_document_sections(
        self, filters: Mapping[str, str], query: str, limit: int
    ) -> tuple[RetrievedSection, ...]:
        self.operations_called.append("search_document_sections")
        return self._inner.search_document_sections(filters, query, limit)

    def get_provenance(self, document_id: str, element_id: str) -> RetrievedProvenance | None:
        self.operations_called.append("get_provenance")
        return self._inner.get_provenance(document_id, element_id)
