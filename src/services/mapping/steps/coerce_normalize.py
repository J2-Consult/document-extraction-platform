"""Step 3 — CoerceNormalize: decoded text to `target_datatype` values.

Mechanical, deterministic coercion only — parse a number, validate an ISO
date, split a table's text into typed rows per the template's declared
columns. NO business rules: whether the numbers ADD UP is the external
Validation Service's question, never this step's.
"""

from __future__ import annotations

from datetime import date

from domain.artifacts.template import TableColumn, TemplateBody
from services.mapping.steps.shapes import (
    CoercedField,
    CoercionResult,
    ContractIssue,
    DecodedValue,
    MaskApplication,
)

DATATYPE_MISMATCH_CODE = "datatype-mismatch"


class _CoercionError(ValueError):
    """Internal: a value does not parse as its target datatype."""


class CoerceNormalize:
    def coerce(self, application: MaskApplication, template: TemplateBody) -> CoercionResult:
        columns_by_element = {
            element.element_id: element.columns for element in template.elements if element.columns is not None
        }
        fields: list[CoercedField] = []
        issues: list[ContractIssue] = []
        for decoded in application.decoded:
            try:
                value = self._coerce_one(decoded, columns_by_element.get(decoded.entry.element_id))
            except _CoercionError as error:
                issues.append(
                    ContractIssue(
                        element_id=decoded.entry.element_id,
                        field=decoded.entry.target.field,
                        code=DATATYPE_MISMATCH_CODE,
                        message=f"element '{decoded.entry.element_id}': {error}",
                    )
                )
                continue
            fields.append(CoercedField(entry=decoded.entry, observation=decoded.observation, value=value))
        return CoercionResult(fields=tuple(fields), issues=tuple(issues))

    def _coerce_one(self, decoded: DecodedValue, columns: list[TableColumn] | None) -> object:
        datatype = decoded.entry.target.datatype
        if datatype == "array":
            if columns is None:
                raise _CoercionError("array target without declared table columns in the template")
            if isinstance(decoded.value, bool):
                raise _CoercionError("boolean cannot coerce to array")
            return _parse_table(decoded.value, columns)
        return _coerce_scalar(decoded.value, datatype)


def _coerce_scalar(value: str | bool, datatype: str) -> object:
    if datatype == "boolean":
        if isinstance(value, bool):
            return value
        raise _CoercionError("value is not boolean (add an enum_map entry to translate it)")
    if isinstance(value, bool):
        raise _CoercionError(f"boolean cannot coerce to {datatype}")
    if datatype == "string":
        return value
    if datatype == "number":
        return _parse_number(value)
    if datatype == "date":
        return _parse_date(value)
    raise _CoercionError(f"unsupported target datatype '{datatype}'")


def _parse_number(text: str) -> float:
    try:
        return float(text)
    except ValueError:
        raise _CoercionError("value does not parse as a number") from None


def _parse_date(text: str) -> str:
    try:
        date.fromisoformat(text)
    except ValueError:
        raise _CoercionError("value does not parse as an ISO date") from None
    return text


def _parse_table(text: str, columns: list[TableColumn]) -> list[dict[str, object]]:
    """Table text to typed rows. The template declares the columns; the first
    non-blank line is the header row (per the template's layout note)."""
    lines = [line for line in text.splitlines() if line.strip()]
    return [_parse_row(line, columns) for line in lines[1:]]


def _parse_row(line: str, columns: list[TableColumn]) -> dict[str, object]:
    """Tokens assign right-to-left for every column after the first, so a
    multi-word leading string column keeps its remaining tokens."""
    tokens = line.split()
    if len(tokens) < len(columns):
        raise _CoercionError("table row has fewer cells than declared columns")
    row: dict[str, object] = {}
    for column in reversed(columns[1:]):
        row[column.name] = _coerce_cell(tokens.pop(), column.datatype)
    first = columns[0]
    row[first.name] = _coerce_cell(" ".join(tokens), first.datatype)
    return {column.name: row[column.name] for column in columns}


def _coerce_cell(text: str, datatype: str) -> object:
    if datatype == "number":
        return _parse_number(text)
    if datatype == "string":
        if not text:
            raise _CoercionError("table row has an empty string cell")
        return text
    raise _CoercionError(f"unsupported table column datatype '{datatype}'")
