"""Versioned target-schema registry.

Target schemas (e.g. `invoice_record_v1`) describe the shape of a MAPPED
record that mask resolution produces — they are what `MaskEntry.target`
(src/domain/artifacts/mask.py) points into. The registry ships its own
packaged copy of each schema under `src/domain/artifacts/schemas/` so this
module has no dependency on the `fixtures/` bundle at runtime; `fixtures/`
remains the test-data source of truth, and a test
(tests/unit/domain/test_registry.py) asserts the two copies never diverge.

Pure domain: the only I/O is reading a small packaged resource file that
ships with this module, not an external system; no framework imports.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

_SCHEMAS_DIR = Path(__file__).resolve().parent / "artifacts" / "schemas"

# schema_id, version -> packaged filename. New schema version = new entry
# here, never an edit to an existing one (open/closed).
_PACKAGED_SCHEMAS: dict[tuple[str, int], str] = {
    ("invoice_record_v1", 1): "invoice_record_v1.schema.json",
}


class UnknownTargetSchemaError(KeyError):
    """Raised when `TargetSchemaRegistry.get` is asked for an unregistered schema/version."""


class TargetSchemaRegistry:
    """Looks up packaged JSON Schema documents for mask resolution targets."""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, int], Mapping[str, object]] = {}

    def get(self, schema_id: str, version: int) -> Mapping[str, object]:
        key = (schema_id, version)
        if key in self._cache:
            return self._cache[key]
        filename = _PACKAGED_SCHEMAS.get(key)
        if filename is None:
            raise UnknownTargetSchemaError(f"no target schema registered for {schema_id!r} v{version}")
        schema: Mapping[str, object] = json.loads((_SCHEMAS_DIR / filename).read_text(encoding="utf-8"))
        self._cache[key] = schema
        return schema


def default_registry() -> TargetSchemaRegistry:
    """Factory mirroring the InvariantValidator's `default_validator()` convention."""
    return TargetSchemaRegistry()
