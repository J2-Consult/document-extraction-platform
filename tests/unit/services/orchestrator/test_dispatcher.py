"""E10 dispatcher: the allow-list is DATA (registry of name -> handler +
parameter schema); the dispatcher validates and dispatches, and NEVER changes
to add an operation (open/closed). Tenant scope is not a suppliable parameter.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from ports.retrieval import RetrievedSection, RetrievedValue
from services.orchestrator.dispatcher import (
    MAX_SEARCH_LIMIT,
    SEARCH_FILTER_KEYS,
    OperationDispatcher,
    OperationSpec,
    ParameterSpec,
    build_registry,
)
from services.orchestrator.errors import (
    GENERIC_CLIENT_MESSAGE,
    InvalidParameterError,
    MissingParameterError,
    UnknownOperationError,
    UnknownParameterError,
)
from tests.unit.fakes.retrieval import FakeRetrievalOperations

PROVENANCE: dict[str, Any] = {
    "source": {"artifact_sha256": "0" * 64, "page": 1},
    "working": {"artifact_sha256": "1" * 64, "coordinate_space": "page-1"},
    "bbox": [206.0, 636.0, 346.0, 648.0],
    "method": "pdf_text",
    "component_version": "fixture-1.0.0",
    "transform_to_source": [1, 0, 0, 1, 0, 0],
}

PAYMENT_TERMS = RetrievedValue(
    document_id="doc_nv20260042",
    element_id="el_payment_terms",
    value="Net 30 days",
    state="present",
    confidence_calibrated=0.98,
    provenance=PROVENANCE,
)

BEARING_SECTION = RetrievedSection(
    document_id="doc_mbr001",
    element_id="el_sec_13_4",
    section_path="13.4",
    semantic_role="bearing_inspection_notes",
    system_context="cmms",
    value="Main rotor bearing inspected; wear within tolerance.",
    state="present",
    provenance=PROVENANCE,
)


def _fake() -> FakeRetrievalOperations:
    return FakeRetrievalOperations(
        values={("doc_nv20260042", "erp_invoice", "payment_terms_code"): PAYMENT_TERMS},
        sections={("doc_mbr001", "13.4"): (BEARING_SECTION,)},
    )


def _dispatch(fake: FakeRetrievalOperations, operation: str, parameters: Mapping[str, object]) -> object:
    return OperationDispatcher(build_registry(fake)).dispatch(operation, parameters)


def test_registry_is_exactly_the_four_operation_allow_list_as_data() -> None:
    registry = build_registry(_fake())

    assert set(registry) == {
        "get_document_value",
        "get_document_section",
        "search_document_sections",
        "get_provenance",
    }
    parameter_names = {name: tuple(parameter.name for parameter in spec.parameters) for name, spec in registry.items()}
    assert parameter_names == {
        "get_document_value": ("document_id", "system_context", "semantic_role"),
        "get_document_section": ("document_id", "section_path"),
        "search_document_sections": ("filters", "query", "limit"),
        "get_provenance": ("document_id", "element_id"),
    }


def test_dispatch_valid_operation_calls_handler_once_with_validated_parameters() -> None:
    fake = _fake()
    parameters = {
        "document_id": "doc_nv20260042",
        "system_context": "erp_invoice",
        "semantic_role": "payment_terms_code",
    }

    result = _dispatch(fake, "get_document_value", parameters)

    assert result == PAYMENT_TERMS
    assert fake.calls == [("get_document_value", parameters)]


def test_unknown_operation_is_rejected_before_any_handler_runs() -> None:
    fake = _fake()

    with pytest.raises(UnknownOperationError) as excinfo:
        _dispatch(fake, "delete_all_documents", {})

    assert fake.calls == [], "no handler may run for an operation outside the allow-list"
    assert excinfo.value.client_message == GENERIC_CLIENT_MESSAGE
    assert "delete_all_documents" not in excinfo.value.client_message
    assert "delete_all_documents" in excinfo.value.server_detail  # itemized server-side


def test_tenant_id_smuggled_as_top_level_parameter_is_rejected_as_unknown_parameter() -> None:
    fake = _fake()
    parameters = {
        "document_id": "doc_nv20260042",
        "system_context": "erp_invoice",
        "semantic_role": "payment_terms_code",
        "tenant_id": "t-victim",
    }

    with pytest.raises(UnknownParameterError) as excinfo:
        _dispatch(fake, "get_document_value", parameters)

    assert fake.calls == []
    assert "tenant_id" in excinfo.value.server_detail
    assert excinfo.value.client_message == GENERIC_CLIENT_MESSAGE


def test_tenant_id_smuggled_inside_search_filters_is_rejected() -> None:
    fake = _fake()
    parameters = {"filters": {"tenant_id": "t-victim"}, "query": "bearing", "limit": 5}

    with pytest.raises(InvalidParameterError) as excinfo:
        _dispatch(fake, "search_document_sections", parameters)

    assert fake.calls == []
    assert "tenant_id" in excinfo.value.server_detail


def test_missing_required_parameter_is_rejected() -> None:
    fake = _fake()

    with pytest.raises(MissingParameterError) as excinfo:
        _dispatch(fake, "get_document_section", {"document_id": "doc_mbr001"})

    assert fake.calls == []
    assert "section_path" in excinfo.value.server_detail


def test_parameter_of_the_wrong_type_is_rejected() -> None:
    fake = _fake()
    parameters = {"filters": {}, "query": "bearing", "limit": "5"}

    with pytest.raises(InvalidParameterError):
        _dispatch(fake, "search_document_sections", parameters)
    assert fake.calls == []


@pytest.mark.parametrize("limit", [0, -1, MAX_SEARCH_LIMIT + 1])
def test_search_limit_outside_bounds_is_rejected(limit: int) -> None:
    fake = _fake()

    with pytest.raises(InvalidParameterError):
        _dispatch(fake, "search_document_sections", {"filters": {}, "query": "bearing", "limit": limit})
    assert fake.calls == []


def test_search_with_allow_listed_filter_dispatches_and_is_result_limited() -> None:
    fake = _fake()
    parameters = {"filters": {"document_id": "doc_mbr001"}, "query": "bearing", "limit": 1}

    result = _dispatch(fake, "search_document_sections", parameters)

    assert result == (BEARING_SECTION,)
    assert fake.calls == [("search_document_sections", parameters)]
    assert "document_id" in SEARCH_FILTER_KEYS


def test_new_operation_is_a_new_registration_never_a_dispatcher_edit() -> None:
    """Open/closed: extending the allow-list means registering one more
    OperationSpec; the same dispatcher dispatches it untouched."""
    fake = _fake()
    registry = dict(build_registry(fake))
    seen: list[str] = []

    def summarize_section(document_id: str, section_path: str) -> str:
        seen.append(f"{document_id}/{section_path}")
        return "summary"

    registry["summarize_section"] = OperationSpec(
        name="summarize_section",
        parameters=(ParameterSpec("document_id", "string"), ParameterSpec("section_path", "string")),
        handler=summarize_section,
    )

    result = OperationDispatcher(registry).dispatch(
        "summarize_section", {"document_id": "doc_mbr001", "section_path": "13.4"}
    )

    assert result == "summary"
    assert seen == ["doc_mbr001/13.4"]
