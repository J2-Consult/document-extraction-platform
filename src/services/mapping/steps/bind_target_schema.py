"""Step 4 — BindTargetSchema: assemble the record and validate its contract.

The versioned target schema comes from the injected `TargetSchemaRegistry`
(constructor injection; an unknown schema/version raises the registry's
`UnknownTargetSchemaError`, which the pipeline reports as a `technical`
failure). Validation is a deliberately small structural checker for the
JSON-Schema subset the packaged target schemas use (type, required,
additionalProperties, properties, items, minLength) rather than a new
runtime dependency: `jsonschema` is a dev-only dependency in this project
and CLAUDE.md forbids new runtime dependencies without necessity — dates
and numbers were already normalized by CoerceNormalize.
"""

from __future__ import annotations

from collections.abc import Mapping

from domain.registry import TargetSchemaRegistry
from services.mapping.steps.shapes import BoundRecord, CoercionResult, ContractIssue

REQUIRED_FIELD_MISSING_CODE = "required-field-missing"
UNKNOWN_FIELD_CODE = "unknown-field"
TYPE_MISMATCH_CODE = "schema-type-mismatch"

_Schema = Mapping[str, object]


class BindTargetSchema:
    def __init__(self, registry: TargetSchemaRegistry) -> None:
        self._registry = registry

    def bind(self, coercion: CoercionResult, schema_id: str, schema_version: int) -> BoundRecord:
        schema = self._registry.get(schema_id, schema_version)
        record = {field.entry.target.field: field.value for field in coercion.fields}
        elements = {field.entry.target.field: field.entry.element_id for field in coercion.fields}
        issues = [
            ContractIssue(element_id=elements.get(field), field=field, code=code, message=message)
            for field, code, message in _validate_object(record, schema, path="")
        ]
        return BoundRecord(record=record, required_fields=_required(schema), issues=tuple(issues))


def _required(schema: _Schema) -> frozenset[str]:
    required = schema.get("required", [])
    return frozenset(name for name in required if isinstance(name, str)) if isinstance(required, list) else frozenset()


def _properties(schema: _Schema) -> Mapping[str, object]:
    properties = schema.get("properties", {})
    return properties if isinstance(properties, Mapping) else {}


def _validate_object(record: Mapping[str, object], schema: _Schema, path: str) -> list[tuple[str, str, str]]:
    """(field, code, message) triples; message carries identifiers only."""
    findings: list[tuple[str, str, str]] = []
    properties = _properties(schema)
    for name in sorted(_required(schema)):
        if name not in record:
            findings.append((f"{path}{name}", REQUIRED_FIELD_MISSING_CODE, f"required field '{path}{name}' is absent"))
    for name, value in record.items():
        spec = properties.get(name)
        if spec is None:
            if schema.get("additionalProperties") is False:
                findings.append(
                    (f"{path}{name}", UNKNOWN_FIELD_CODE, f"field '{path}{name}' is not in the target schema")
                )
            continue
        if isinstance(spec, Mapping):
            findings.extend(_validate_value(value, spec, f"{path}{name}"))
    return findings


def _validate_value(value: object, spec: _Schema, path: str) -> list[tuple[str, str, str]]:
    declared = spec.get("type")
    if declared == "array":
        return _validate_array(value, spec, path)
    if not _matches_scalar(value, declared):
        return [(path, TYPE_MISMATCH_CODE, f"field '{path}' is not of schema type '{declared}'")]
    min_length = spec.get("minLength")
    if isinstance(value, str) and isinstance(min_length, int) and len(value) < min_length:
        return [(path, TYPE_MISMATCH_CODE, f"field '{path}' is shorter than minLength {min_length}")]
    return []


def _validate_array(value: object, spec: _Schema, path: str) -> list[tuple[str, str, str]]:
    if not isinstance(value, list):
        return [(path, TYPE_MISMATCH_CODE, f"field '{path}' is not of schema type 'array'")]
    items = spec.get("items")
    if not isinstance(items, Mapping):
        return []
    findings: list[tuple[str, str, str]] = []
    for index, item in enumerate(value):
        if isinstance(item, Mapping):
            findings.extend(_validate_object(item, items, path=f"{path}/{index}/"))
        else:
            findings.append((f"{path}/{index}", TYPE_MISMATCH_CODE, f"item '{path}/{index}' is not an object"))
    return findings


def _matches_scalar(value: object, declared: object) -> bool:
    if declared == "string":
        return isinstance(value, str)
    if declared == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if declared == "boolean":
        return isinstance(value, bool)
    if declared == "object":
        return isinstance(value, Mapping)
    return True  # no/unknown type constraint: nothing to check structurally
