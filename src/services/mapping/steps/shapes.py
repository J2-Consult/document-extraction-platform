"""Intermediate data shapes handed between mapping steps (E09).

One frozen dataclass per hand-off; the step classes themselves live one per
module (resolve_refs.py, apply_mask.py, coerce_normalize.py,
bind_target_schema.py, decide_outcome.py). Pure data: no I/O, no adapter
imports, and no document content in any message field — `ContractIssue`
carries identifiers and coded reasons only.
"""

from __future__ import annotations

from dataclasses import dataclass

from domain.artifacts.content import Observation
from domain.artifacts.mask import MaskEntry


@dataclass(frozen=True, slots=True)
class ResolvedEntry:
    """One mask entry joined to the content observation for its element (if any)."""

    entry: MaskEntry
    observation: Observation | None


@dataclass(frozen=True, slots=True)
class ResolvedRefs:
    entries: tuple[ResolvedEntry, ...]


@dataclass(frozen=True, slots=True)
class ContractIssue:
    """One target-contract problem. Identifiers only — never observed text."""

    element_id: str | None
    field: str
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class DecodedValue:
    """A present observation after the mask's semantic decoding (enum_map applied)."""

    entry: MaskEntry
    observation: Observation
    value: str | bool


@dataclass(frozen=True, slots=True)
class MaskApplication:
    """ApplyMask's output: decoded values, absence buckets, and enum issues."""

    decoded: tuple[DecodedValue, ...]
    unreadable: tuple[ResolvedEntry, ...]
    blank: tuple[ResolvedEntry, ...]
    issues: tuple[ContractIssue, ...]


@dataclass(frozen=True, slots=True)
class CoercedField:
    """One decoded value coerced to its target datatype."""

    entry: MaskEntry
    observation: Observation
    value: object


@dataclass(frozen=True, slots=True)
class CoercionResult:
    fields: tuple[CoercedField, ...]
    issues: tuple[ContractIssue, ...]


@dataclass(frozen=True, slots=True)
class BoundRecord:
    """The assembled candidate record plus the target schema's verdict on it."""

    record: dict[str, object]
    required_fields: frozenset[str]
    issues: tuple[ContractIssue, ...]
