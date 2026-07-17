"""Allow-listed retrieval dispatch (epic E10).

THE ALLOW-LIST IS DATA: `build_registry` maps operation name -> handler +
parameter schema (`OperationSpec`). `OperationDispatcher` validates the
operation name against the registry and the parameters against that
operation's schema, then calls the handler — it contains no per-operation
logic and NEVER changes to add an operation (open/closed: a new operation is
a new `OperationSpec` registration plus review).

Security properties:
- Unknown operation -> `UnknownOperationError` before any handler runs. Text
  retrieved from documents can therefore never name an operation into
  existence ("delete_all_documents" is not a thing, no matter what a PDF says).
- Unknown parameter -> `UnknownParameterError`; this is what rejects a
  smuggled `tenant_id` — tenant scope is bound to the session by the
  composition root, outside model control, and is not in any schema.
- `search_document_sections` is result-limited (`limit` bounded to
  `MAX_SEARCH_LIMIT`) and its `filters` keys are allow-listed
  (`SEARCH_FILTER_KEYS`).
- Read-only by construction: handlers are the four `ports.retrieval`
  operations, served by the SELECT-only `orchestrator_readonly` role.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal

from ports.retrieval import RetrievalOperations
from services.orchestrator.errors import (
    InvalidParameterError,
    MissingParameterError,
    UnknownOperationError,
    UnknownParameterError,
)

MAX_SEARCH_LIMIT = 20
SEARCH_FILTER_KEYS = frozenset({"document_id"})

ParameterKind = Literal["string", "integer", "string_map"]


@dataclass(frozen=True, slots=True)
class ParameterSpec:
    """Schema of one operation parameter (the validation is generic over these)."""

    name: str
    kind: ParameterKind
    min_value: int | None = None
    max_value: int | None = None
    allowed_keys: frozenset[str] | None = None


@dataclass(frozen=True, slots=True)
class OperationSpec:
    """One allow-list entry: operation name, parameter schema, handler."""

    name: str
    parameters: tuple[ParameterSpec, ...]
    handler: Callable[..., object]


def build_registry(operations: RetrievalOperations) -> dict[str, OperationSpec]:
    """The retrieval allow-list, as data (see ports.retrieval for the contract)."""
    specs = (
        OperationSpec(
            name="get_document_value",
            parameters=(
                ParameterSpec("document_id", "string"),
                ParameterSpec("system_context", "string"),
                ParameterSpec("semantic_role", "string"),
            ),
            handler=operations.get_document_value,
        ),
        OperationSpec(
            name="get_document_section",
            parameters=(
                ParameterSpec("document_id", "string"),
                ParameterSpec("section_path", "string"),
            ),
            handler=operations.get_document_section,
        ),
        OperationSpec(
            name="search_document_sections",
            parameters=(
                ParameterSpec("filters", "string_map", allowed_keys=SEARCH_FILTER_KEYS),
                ParameterSpec("query", "string"),
                ParameterSpec("limit", "integer", min_value=1, max_value=MAX_SEARCH_LIMIT),
            ),
            handler=operations.search_document_sections,
        ),
        OperationSpec(
            name="get_provenance",
            parameters=(
                ParameterSpec("document_id", "string"),
                ParameterSpec("element_id", "string"),
            ),
            handler=operations.get_provenance,
        ),
    )
    return {spec.name: spec for spec in specs}


def _validate_string(spec: ParameterSpec, value: object) -> None:
    if not isinstance(value, str):
        raise InvalidParameterError(f"parameter {spec.name!r} must be a string, got {type(value).__name__}")


def _validate_integer(spec: ParameterSpec, value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise InvalidParameterError(f"parameter {spec.name!r} must be an integer, got {type(value).__name__}")
    if spec.min_value is not None and value < spec.min_value:
        raise InvalidParameterError(f"parameter {spec.name!r} below minimum {spec.min_value}: {value}")
    if spec.max_value is not None and value > spec.max_value:
        raise InvalidParameterError(f"parameter {spec.name!r} above maximum {spec.max_value}: {value}")


def _validate_string_map(spec: ParameterSpec, value: object) -> None:
    if not isinstance(value, Mapping):
        raise InvalidParameterError(f"parameter {spec.name!r} must be a mapping, got {type(value).__name__}")
    allowed = spec.allowed_keys if spec.allowed_keys is not None else frozenset()
    disallowed = sorted(set(value) - allowed)
    if disallowed:
        raise InvalidParameterError(f"parameter {spec.name!r} has non-allow-listed keys: {disallowed}")
    non_string = sorted(str(key) for key, item in value.items() if not isinstance(item, str))
    if non_string:
        raise InvalidParameterError(f"parameter {spec.name!r} has non-string values for keys: {non_string}")


_VALIDATORS: dict[ParameterKind, Callable[[ParameterSpec, object], None]] = {
    "string": _validate_string,
    "integer": _validate_integer,
    "string_map": _validate_string_map,
}


def _validate_parameters(spec: OperationSpec, parameters: Mapping[str, object]) -> None:
    known = {parameter.name for parameter in spec.parameters}
    unknown = sorted(set(parameters) - known)
    if unknown:
        raise UnknownParameterError(f"operation {spec.name!r} rejected unknown parameters: {unknown}")
    missing = sorted(known - set(parameters))
    if missing:
        raise MissingParameterError(f"operation {spec.name!r} is missing required parameters: {missing}")
    for parameter in spec.parameters:
        _VALIDATORS[parameter.kind](parameter, parameters[parameter.name])


class OperationDispatcher:
    """Validates against the registry and dispatches; knows no operation by name."""

    def __init__(self, registry: Mapping[str, OperationSpec]) -> None:
        self._registry = dict(registry)

    def dispatch(self, operation: str, parameters: Mapping[str, object]) -> object:
        spec = self._registry.get(operation)
        if spec is None:
            known = sorted(self._registry)
            raise UnknownOperationError(f"operation {operation!r} is not in the retrieval allow-list {known}")
        _validate_parameters(spec, parameters)
        return spec.handler(**dict(parameters))
