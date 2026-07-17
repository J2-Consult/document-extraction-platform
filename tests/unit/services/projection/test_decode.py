"""Unit tests for the E07 projection decode step (no DB, no network).

The decode functions turn immutable artifact JSON (fixtures/artifacts/) into
relational projection rows via the E01 typed models — they are the single
source of truth for what lands in `extracted_values` and `mask_entries`.
Criterion 12's "rows equal the values decoded straight from the JSON
artifacts" is anchored on these functions, so they are covered here directly
against the fixture corpus.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from services.projection.decode import decode_document_values, decode_mask_entries

ARTIFACTS_DIR = Path(__file__).resolve().parents[4] / "fixtures" / "artifacts"

NV_CUSTOMER_OVERRIDDEN_ELEMENTS = {"el_currency", "el_payment_terms", "el_notes"}


def _load_artifact(name: str) -> dict[str, Any]:
    return dict(json.loads((ARTIFACTS_DIR / f"{name}.json").read_text(encoding="utf-8")))


def test_decode_document_values_emits_one_row_per_observation_with_provenance() -> None:
    artifact = _load_artifact("content_nv20260042.v1")

    rows = decode_document_values(artifact)

    observations = artifact["body"]["observations"]
    assert len(rows) == len(observations) == 12
    by_element = {row.element_id: row for row in rows}
    for observation in observations:
        row = by_element[observation["element_id"]]
        assert row.tenant_id == "t-nordvik"
        assert row.document_id == "doc_nv20260042"
        assert row.content_id == "content_nv20260042"
        assert row.content_version == 1
        assert row.value == observation["value"]
        assert row.state == observation["state"]
        assert row.confidence_raw == observation["confidence"]["raw"]
        assert row.confidence_calibrated == observation["confidence"]["calibrated"]
        # Provenance travels with every value, byte-for-byte in wire form.
        assert row.provenance == observation["provenance"]


def test_decode_document_values_preserves_null_value_states() -> None:
    invoice_rows = decode_document_values(_load_artifact("content_nv20260042.v1"))
    mbr_rows = decode_document_values(_load_artifact("content_mbr001.v1"))

    empty = next(row for row in invoice_rows if row.element_id == "el_notes")
    assert empty.state == "empty"
    assert empty.value is None

    unreadable = next(row for row in mbr_rows if row.element_id == "el_sec_9_7")
    assert unreadable.state == "unreadable"
    assert unreadable.value is None
    assert unreadable.provenance  # blank assertions carry provenance too


def test_decode_document_values_rejects_artifact_without_tenant() -> None:
    artifact = _load_artifact("content_nv20260042.v1")
    artifact["tenant_id"] = None

    with pytest.raises(ValueError, match="tenant"):
        decode_document_values(artifact)


def test_decode_mask_entries_parses_wire_schema_key_and_attribution() -> None:
    rows = decode_mask_entries(_load_artifact("mask_nvcust.v1"))

    assert len(rows) == 10
    # WIRE form uses key "schema"; the E01 model exposes it as target_schema.
    assert {row.target_schema for row in rows} == {"invoice_record_v1"}

    overridden = {row.element_id for row in rows if row.overridden}
    assert overridden == NV_CUSTOMER_OVERRIDDEN_ELEMENTS
    for row in rows:
        assert row.tenant_id == "t-nordvik"
        assert row.scope == "customer"
        assert row.mask_id == "mask_nvcust"
        assert row.mask_version == 1
        assert row.template_id == "tmpl_nvinv"
        assert row.template_version == 1
        assert row.system_context == "erp_invoice"
        # Materialized effective mask: every entry attributes its inheritance.
        assert row.inherited_from_mask_id == "mask_nvvendor"
        assert row.inherited_from_version == 1
        if row.overridden:
            assert row.origin == "customer"

    currency = next(row for row in rows if row.element_id == "el_currency")
    assert currency.enum_map == {"NOK": "NOK", "Kr": "NOK"}


def test_decode_mask_entries_vendor_baseline_and_section_paths() -> None:
    vendor_rows = decode_mask_entries(_load_artifact("mask_nvvendor.v1"))
    mbr_rows = decode_mask_entries(_load_artifact("mask_mbrvendor.v1"))

    assert all(row.tenant_id is None and row.scope == "vendor" for row in vendor_rows)
    assert all(not row.overridden and row.inherited_from_mask_id is None for row in vendor_rows)
    assert all(row.validated_by == "vendor-consultant-1" for row in vendor_rows)

    section_paths = {row.element_id: row.section_path for row in mbr_rows}
    assert section_paths["el_sec_13_4"] == "13.4"
    assert section_paths["el_sec_16_3"] == "16.3"
    assert mbr_rows[0].system_context == "cmms"


def test_decode_is_deterministic() -> None:
    content = _load_artifact("content_nv20260043.v1")
    mask = _load_artifact("mask_nvcust.v1")

    assert decode_document_values(content) == decode_document_values(content)
    assert decode_mask_entries(mask) == decode_mask_entries(mask)
