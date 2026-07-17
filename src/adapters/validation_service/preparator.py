"""Preparator (E09): flatten the decoded record, attach `_bboxes`, invoke.

The mapped record is nested JSON (arrays of row objects); rulesets address
scalar paths, so the preparator flattens to JSON-pointer-ish keys
("line_items/0/qty") and attaches each TOP-LEVEL field's source page + bbox
from observation provenance under "_bboxes" — the Validation Service can
point a human at exactly where a failing value was read. Rule EVALUATION
stays external: this module builds the request and relays the verdict,
nothing more.
"""

from __future__ import annotations

from collections.abc import Mapping

from adapters.validation_service.client import (
    FieldBox,
    FlatValue,
    ValidationRequest,
    ValidationServiceClient,
)
from domain.artifacts.provenance import Provenance
from services.mapping.outcome import RulesetVerdict


class RecordPreparator:
    def __init__(self, client: ValidationServiceClient) -> None:
        self._client = client

    def invoke(
        self,
        *,
        ruleset_id: str,
        target_schema: str,
        target_schema_version: int,
        record: Mapping[str, object],
        provenance_by_field: Mapping[str, Provenance],
    ) -> RulesetVerdict:
        request = ValidationRequest(
            ruleset_id=ruleset_id,
            target_schema=target_schema,
            target_schema_version=target_schema_version,
            record=_flatten(record),
            _bboxes=_field_boxes(record, provenance_by_field),
        )
        return self._client.evaluate(request)


def _flatten(record: Mapping[str, object]) -> dict[str, FlatValue]:
    flat: dict[str, FlatValue] = {}
    for field, value in record.items():
        _flatten_into(flat, field, value)
    return flat


def _flatten_into(flat: dict[str, FlatValue], path: str, value: object) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            _flatten_into(flat, f"{path}/{key}", nested)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _flatten_into(flat, f"{path}/{index}", item)
        return
    if not isinstance(value, str | float | int | bool):
        raise ValueError(f"record field '{path}' is not JSON-scalar-flattenable")
    flat[path] = value


def _field_boxes(record: Mapping[str, object], provenance_by_field: Mapping[str, Provenance]) -> dict[str, FieldBox]:
    missing = sorted(set(record) - set(provenance_by_field))
    if missing:
        raise ValueError(f"record fields without provenance: {', '.join(missing)} — a value never travels without it")
    return {
        field: FieldBox(page=provenance_by_field[field].source.page, bbox=list(provenance_by_field[field].bbox))
        for field in record
    }
