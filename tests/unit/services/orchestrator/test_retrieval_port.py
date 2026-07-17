"""E10 port shape: EXACTLY four allow-listed retrieval operations, tenant-free
signatures, and the allow-list documented in the port docstring (epic DoD).

The port is the LLM trust boundary's vocabulary: if this test needs editing,
the allow-list changed and the change needs security review.
"""

from __future__ import annotations

import inspect

from ports import retrieval
from ports.retrieval import RetrievalOperations

EXPECTED_OPERATIONS: dict[str, tuple[str, ...]] = {
    "get_document_value": ("document_id", "system_context", "semantic_role"),
    "get_document_section": ("document_id", "section_path"),
    "search_document_sections": ("filters", "query", "limit"),
    "get_provenance": ("document_id", "element_id"),
}


def _public_operations() -> dict[str, inspect.Signature]:
    members = {
        name: member
        for name, member in vars(RetrievalOperations).items()
        if not name.startswith("_") and callable(member)
    }
    return {name: inspect.signature(member) for name, member in members.items()}


def test_port_exposes_exactly_the_four_allow_listed_operations() -> None:
    assert set(_public_operations()) == set(EXPECTED_OPERATIONS)


def test_every_operation_signature_matches_the_allow_list_exactly() -> None:
    for name, signature in _public_operations().items():
        parameters = tuple(parameter for parameter in signature.parameters if parameter != "self")
        assert parameters == EXPECTED_OPERATIONS[name], name


def test_no_operation_accepts_tenant_scope_in_any_parameter() -> None:
    """Tenant context is injected from the session OUTSIDE model control — the
    port signatures must not even be able to carry it."""
    for name, signature in _public_operations().items():
        assert not any("tenant" in parameter.lower() for parameter in signature.parameters), name


def test_allow_list_and_tenant_invariant_are_documented_in_the_port_docstring() -> None:
    documentation = (retrieval.__doc__ or "") + (RetrievalOperations.__doc__ or "")
    for operation in EXPECTED_OPERATIONS:
        assert operation in documentation, f"allow-list entry {operation!r} missing from the port docstring"
    assert "tenant" in documentation.lower()
