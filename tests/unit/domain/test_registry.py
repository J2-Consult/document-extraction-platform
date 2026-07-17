"""TargetSchemaRegistry (src/domain/registry.py): versioned target schemas
backed by packaged JSON Schema resources.
"""

from __future__ import annotations

import json

import pytest

from domain.registry import TargetSchemaRegistry, UnknownTargetSchemaError, default_registry


def test_get_returns_invoice_record_v1_schema() -> None:
    schema = TargetSchemaRegistry().get("invoice_record_v1", 1)

    assert schema["title"] == "invoice_record_v1"
    assert schema["required"] == ["invoice_number", "invoice_date", "total_amount", "currency"]


def test_packaged_invoice_record_v1_copy_matches_fixtures_source_of_truth(load_fixture_schema: object) -> None:
    fixture_schema = load_fixture_schema("invoice_record_v1.schema")  # type: ignore[operator]
    packaged_schema = TargetSchemaRegistry().get("invoice_record_v1", 1)

    assert packaged_schema == fixture_schema


def test_get_raises_for_unregistered_schema_id() -> None:
    with pytest.raises(UnknownTargetSchemaError):
        TargetSchemaRegistry().get("nonexistent_schema", 1)


def test_get_raises_for_unregistered_version() -> None:
    with pytest.raises(UnknownTargetSchemaError):
        TargetSchemaRegistry().get("invoice_record_v1", 99)


def test_get_result_is_cached_across_repeated_calls() -> None:
    registry = TargetSchemaRegistry()

    first = registry.get("invoice_record_v1", 1)
    second = registry.get("invoice_record_v1", 1)

    assert first is second


def test_default_registry_factory_returns_a_usable_registry() -> None:
    registry = default_registry()

    assert isinstance(registry, TargetSchemaRegistry)
    assert registry.get("invoice_record_v1", 1)["type"] == "object"


def test_registry_result_is_valid_json_serializable_data() -> None:
    schema = TargetSchemaRegistry().get("invoice_record_v1", 1)

    # Round-trips cleanly — proves it's plain JSON-safe data, not something
    # tied to the file it was loaded from.
    assert json.loads(json.dumps(schema)) == schema
