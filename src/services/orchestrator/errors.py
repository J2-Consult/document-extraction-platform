"""Orchestrator errors and operation logging (epic E10).

Errors are GENERIC to clients (`client_message` never echoes operation names,
parameter names, or values) and ITEMIZED server-side (`server_detail`, which
is also `str(error)` so nothing is ever swallowed).

Operation logging carries IDs, states, and counts ONLY — never retrieved
text, values, or document content. `operation_log_record` enforces this
structurally: every id field must be id-shaped (no whitespace, bounded
length), so free document text cannot even be passed through it.
"""

from __future__ import annotations

import re

GENERIC_CLIENT_MESSAGE = "The retrieval request could not be completed."

_ID_SHAPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


class OrchestratorError(Exception):
    """Base error: generic client message, itemized server detail."""

    client_message: str = GENERIC_CLIENT_MESSAGE

    def __init__(self, server_detail: str) -> None:
        super().__init__(server_detail)
        self.server_detail = server_detail


class UnknownOperationError(OrchestratorError):
    """Operation name is not in the retrieval allow-list."""


class UnknownParameterError(OrchestratorError):
    """A parameter outside the operation's schema was supplied (e.g. tenant_id)."""


class MissingParameterError(OrchestratorError):
    """A required parameter of the operation's schema is absent."""


class InvalidParameterError(OrchestratorError):
    """A parameter is present but fails its schema (type, bounds, allowed keys)."""


def _require_id_shaped(field: str, value: str) -> str:
    if not _ID_SHAPE.fullmatch(value):
        raise ValueError(f"log field {field!r} must be id-shaped (ids/states only, never retrieved text)")
    return value


def operation_log_record(
    *,
    operation: str,
    outcome: str,
    document_id: str | None = None,
    element_ids: tuple[str, ...] = (),
    result_count: int = 0,
) -> dict[str, str | int | tuple[str, ...]]:
    """A structured log record for one dispatch: IDs and counts, never text."""
    record: dict[str, str | int | tuple[str, ...]] = {
        "operation": _require_id_shaped("operation", operation),
        "outcome": _require_id_shaped("outcome", outcome),
    }
    if document_id is not None:
        record["document_id"] = _require_id_shaped("document_id", document_id)
    record["element_ids"] = tuple(_require_id_shaped("element_ids", element_id) for element_id in element_ids)
    record["result_count"] = result_count
    return record
