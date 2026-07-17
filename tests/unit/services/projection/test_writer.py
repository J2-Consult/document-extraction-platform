"""Unit tests for the E07 `ProjectionWriter` against an in-memory sink.

The writer's contract: idempotent (projecting twice converges to the same
rows), order-independent across artifacts, and partial-failure re-runs
converge because every write is a delete-and-reinsert of one whole
(tenant, document/mask, version) scope.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from services.projection.rows import (
    DocumentValuesScope,
    ExtractedValueRow,
    MaskEntriesScope,
    MaskEntryRow,
)
from services.projection.writer import ProjectionWriter

ARTIFACTS_DIR = Path(__file__).resolve().parents[4] / "fixtures" / "artifacts"


def _load_artifact(name: str) -> dict[str, Any]:
    return dict(json.loads((ARTIFACTS_DIR / f"{name}.json").read_text(encoding="utf-8")))


class RecordingSink:
    """In-memory ProjectionSink fake: replace-by-scope, like the Postgres sink."""

    def __init__(self) -> None:
        self.document_values: dict[DocumentValuesScope, tuple[ExtractedValueRow, ...]] = {}
        self.mask_entries: dict[MaskEntriesScope, tuple[MaskEntryRow, ...]] = {}
        self.replace_calls: int = 0

    def replace_document_values(self, scope: DocumentValuesScope, rows: Sequence[ExtractedValueRow]) -> None:
        self.replace_calls += 1
        self.document_values[scope] = tuple(rows)

    def replace_mask_entries(self, scope: MaskEntriesScope, rows: Sequence[MaskEntryRow]) -> None:
        self.replace_calls += 1
        self.mask_entries[scope] = tuple(rows)


class FlakyOnceSink(RecordingSink):
    """Fails the first document-values write, then behaves; models a partial failure."""

    def __init__(self) -> None:
        super().__init__()
        self._failed_once = False

    def replace_document_values(self, scope: DocumentValuesScope, rows: Sequence[ExtractedValueRow]) -> None:
        if not self._failed_once:
            self._failed_once = True
            raise RuntimeError("simulated write failure before any row landed")
        super().replace_document_values(scope, rows)


def test_projecting_twice_converges_to_identical_sink_state() -> None:
    sink = RecordingSink()
    writer = ProjectionWriter(sink)
    content = _load_artifact("content_nv20260042.v1")
    mask = _load_artifact("mask_nvcust.v1")

    writer.project_content(content)
    writer.project_mask(mask)
    first_values = dict(sink.document_values)
    first_entries = dict(sink.mask_entries)

    writer.project_content(content)
    writer.project_mask(mask)

    assert sink.document_values == first_values
    assert sink.mask_entries == first_entries
    assert len(sink.document_values) == 1  # one scope, replaced not appended
    assert len(sink.mask_entries) == 1


def test_projection_is_order_independent_across_artifacts() -> None:
    content = _load_artifact("content_nv20260042.v1")
    mask = _load_artifact("mask_nvvendor.v1")

    forward = RecordingSink()
    writer = ProjectionWriter(forward)
    writer.project_content(content)
    writer.project_mask(mask)

    reverse = RecordingSink()
    writer = ProjectionWriter(reverse)
    writer.project_mask(mask)
    writer.project_content(content)

    assert forward.document_values == reverse.document_values
    assert forward.mask_entries == reverse.mask_entries


def test_partial_failure_rerun_converges() -> None:
    sink = FlakyOnceSink()
    writer = ProjectionWriter(sink)
    content = _load_artifact("content_nv20260043.v1")

    with pytest.raises(RuntimeError):
        writer.project_content(content)
    assert sink.document_values == {}  # nothing landed from the failed run

    rows = writer.project_content(content)

    scope = DocumentValuesScope(
        tenant_id="t-nordvik",
        document_id="doc_nv20260043",
        content_id="content_nv20260043",
        content_version=1,
    )
    assert sink.document_values == {scope: tuple(rows)}


def test_project_content_returns_rows_and_scopes_the_replace() -> None:
    sink = RecordingSink()
    writer = ProjectionWriter(sink)

    rows = writer.project_content(_load_artifact("content_mbr001.v1"))

    scope = DocumentValuesScope(
        tenant_id="t-nordvik",
        document_id="doc_mbr001",
        content_id="content_mbr001",
        content_version=1,
    )
    assert scope in sink.document_values
    assert sink.document_values[scope] == tuple(rows)
    assert len(rows) == 6


def test_project_mask_scopes_by_mask_identity_including_vendor_null_tenant() -> None:
    sink = RecordingSink()
    writer = ProjectionWriter(sink)

    rows = writer.project_mask(_load_artifact("mask_mbrvendor.v1"))

    scope = MaskEntriesScope(tenant_id=None, mask_id="mask_mbrvendor", mask_version=1)
    assert sink.mask_entries == {scope: tuple(rows)}
    assert len(rows) == 6
