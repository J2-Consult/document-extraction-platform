"""Shared VectorIndex contract suite (epic E11).

This ONE suite is the port contract: the in-memory reference adapter runs
under it today, and any future real backend adapter (pgvector, a managed
vector DB, ...) is added to the `vector_index` fixture params and must pass
the identical tests — the same pattern as the E03 ObjectStore contract suite.

The security-critical assertions live here so every backend inherits them:
tenant partition mandatory (cross-tenant queries return nothing), deletion
verified by read-after-delete (a forgotten embedding is the classic
retention leak), and set defaults that can only point at COMPLETE sets.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from adapters.vectorindex.in_memory import InMemoryVectorIndex
from ports.vectorindex import (
    EmbeddingSetKey,
    IncompleteSetError,
    IndexEntry,
    SetStatus,
    UnknownSetError,
    VectorIndex,
)

TENANT_A = "t-nordvik"
TENANT_B = "t-other"

_PROVENANCE: Mapping[str, Any] = {
    "source": {"artifact_sha256": "b" * 64, "page": 1},
    "working": {"artifact_sha256": "b" * 64, "coordinate_space": "page-1"},
    "bbox": [56.0, 496.0, 540.0, 528.0],
    "method": "pdf_text",
    "component_version": "fixture-1.0.0",
    "transform_to_source": [1, 0, 0, 1, 0, 0],
}


@pytest.fixture(params=["in_memory"])
def vector_index(request: pytest.FixtureRequest) -> VectorIndex:
    """Every real-backend-shaped adapter registers here and shares the suite."""
    return InMemoryVectorIndex()


def structural_key(tenant_id: str = TENANT_A, document_id: str = "doc_mbr001") -> EmbeddingSetKey:
    return EmbeddingSetKey(
        tenant_id=tenant_id,
        document_id=document_id,
        mask_id=None,
        mask_version=None,
        template_id="tmpl_mbr",
        template_version=1,
    )


def semantic_key(tenant_id: str = TENANT_A, mask_version: int = 1) -> EmbeddingSetKey:
    return EmbeddingSetKey(
        tenant_id=tenant_id,
        document_id="doc_mbr001",
        mask_id="mask_mbrvendor",
        mask_version=mask_version,
        template_id="tmpl_mbr",
        template_version=1,
    )


def entry(chunk_id: str, vector: tuple[float, ...], *, section_path: str | None = None, text: str = "x") -> IndexEntry:
    return IndexEntry(
        chunk_id=chunk_id,
        vector=vector,
        text=text,
        page=1,
        bbox=(56.0, 496.0, 540.0, 528.0),
        provenance=_PROVENANCE,
        section_path=section_path,
    )


class TestEmbeddingSetKeyInvariants:
    def test_tenant_id_is_required_and_non_empty(self) -> None:
        with pytest.raises(ValueError):
            EmbeddingSetKey(
                tenant_id="",
                document_id="doc_mbr001",
                mask_id=None,
                mask_version=None,
                template_id="tmpl_mbr",
                template_version=1,
            )

    def test_mask_id_and_mask_version_must_pair(self) -> None:
        with pytest.raises(ValueError):
            EmbeddingSetKey(
                tenant_id=TENANT_A,
                document_id="doc_mbr001",
                mask_id="mask_mbrvendor",
                mask_version=None,
                template_id="tmpl_mbr",
                template_version=1,
            )
        with pytest.raises(ValueError):
            EmbeddingSetKey(
                tenant_id=TENANT_A,
                document_id="doc_mbr001",
                mask_id=None,
                mask_version=1,
                template_id="tmpl_mbr",
                template_version=1,
            )

    def test_structural_tier_is_null_mask_and_semantic_tier_is_mask_keyed(self) -> None:
        assert structural_key().tier == "structural"
        assert semantic_key().tier == "semantic"


class TestSetLifecycle:
    def test_register_set_is_idempotent_and_starts_building(self, vector_index: VectorIndex) -> None:
        key = structural_key()
        vector_index.register_set(key, created_at=1.0)
        vector_index.register_set(key, created_at=2.0)  # replay: no error, no reset

        records = vector_index.list_sets(tenant_id=TENANT_A, document_id="doc_mbr001")
        assert [record.key for record in records] == [key]
        assert records[0].status == SetStatus.BUILDING
        assert records[0].created_at == 1.0

    def test_upsert_to_unregistered_set_is_rejected(self, vector_index: VectorIndex) -> None:
        with pytest.raises(UnknownSetError):
            vector_index.upsert_entries(structural_key(), [entry("c0", (1.0, 0.0))])

    def test_upsert_is_idempotent_per_chunk_id(self, vector_index: VectorIndex) -> None:
        key = structural_key()
        vector_index.register_set(key, created_at=0.0)
        vector_index.upsert_entries(key, [entry("c0", (1.0, 0.0))])
        vector_index.upsert_entries(key, [entry("c0", (1.0, 0.0)), entry("c1", (0.0, 1.0))])

        assert vector_index.entry_ids(key) == frozenset({"c0", "c1"})

    def test_mark_complete_flips_status(self, vector_index: VectorIndex) -> None:
        key = structural_key()
        vector_index.register_set(key, created_at=0.0)
        vector_index.mark_complete(key)

        records = vector_index.list_sets(tenant_id=TENANT_A, document_id="doc_mbr001")
        assert records[0].status == SetStatus.COMPLETE


class TestDefaultPointer:
    def test_no_default_until_one_is_set(self, vector_index: VectorIndex) -> None:
        assert vector_index.get_default(tenant_id=TENANT_A, document_id="doc_mbr001") is None

    def test_default_cannot_point_at_an_incomplete_set(self, vector_index: VectorIndex) -> None:
        key = structural_key()
        vector_index.register_set(key, created_at=0.0)
        with pytest.raises(IncompleteSetError):
            vector_index.set_default(key)
        assert vector_index.get_default(tenant_id=TENANT_A, document_id="doc_mbr001") is None

    def test_default_switches_to_a_complete_set(self, vector_index: VectorIndex) -> None:
        structural, semantic = structural_key(), semantic_key()
        for key in (structural, semantic):
            vector_index.register_set(key, created_at=0.0)
        vector_index.mark_complete(structural)
        vector_index.set_default(structural)
        vector_index.mark_complete(semantic)
        vector_index.set_default(semantic)

        assert vector_index.get_default(tenant_id=TENANT_A, document_id="doc_mbr001") == semantic


class TestQuery:
    def test_query_returns_hits_by_descending_similarity_with_payload(self, vector_index: VectorIndex) -> None:
        key = structural_key()
        vector_index.register_set(key, created_at=0.0)
        vector_index.upsert_entries(
            key,
            [
                entry("c0", (1.0, 0.0), text="bearing inspection", section_path="13.4"),
                entry("c1", (0.0, 1.0), text="corrective actions", section_path="16.3"),
            ],
        )

        hits = vector_index.query(key, (1.0, 0.1), limit=2)

        assert [hit.entry.chunk_id for hit in hits] == ["c0", "c1"]
        assert hits[0].score >= hits[1].score
        assert hits[0].entry.text == "bearing inspection"
        assert hits[0].entry.page == 1
        assert hits[0].entry.bbox == (56.0, 496.0, 540.0, 528.0)
        assert hits[0].entry.provenance == _PROVENANCE

    def test_query_respects_limit(self, vector_index: VectorIndex) -> None:
        key = structural_key()
        vector_index.register_set(key, created_at=0.0)
        vector_index.upsert_entries(key, [entry(f"c{i}", (float(i), 1.0)) for i in range(5)])

        assert len(vector_index.query(key, (1.0, 1.0), limit=3)) == 3

    def test_query_rejects_non_positive_limit(self, vector_index: VectorIndex) -> None:
        key = structural_key()
        vector_index.register_set(key, created_at=0.0)
        with pytest.raises(ValueError):
            vector_index.query(key, (1.0, 0.0), limit=0)

    def test_section_path_filter_returns_only_matching_chunks(self, vector_index: VectorIndex) -> None:
        key = structural_key()
        vector_index.register_set(key, created_at=0.0)
        vector_index.upsert_entries(
            key,
            [
                entry("c0", (1.0, 0.0), section_path="13.4"),
                entry("c1", (1.0, 0.0), section_path="16.3"),
                entry("c2", (1.0, 0.0), section_path=None),
            ],
        )

        hits = vector_index.query(key, (1.0, 0.0), limit=10, section_path="13.4")

        assert [hit.entry.chunk_id for hit in hits] == ["c0"]

    def test_query_on_unknown_set_is_rejected(self, vector_index: VectorIndex) -> None:
        with pytest.raises(UnknownSetError):
            vector_index.query(structural_key(), (1.0, 0.0), limit=1)


class TestTenantPartition:
    def test_cross_tenant_retrieval_is_impossible_at_the_port_level(self, vector_index: VectorIndex) -> None:
        key_a, key_b = structural_key(TENANT_A), structural_key(TENANT_B)
        vector_index.register_set(key_a, created_at=0.0)
        vector_index.upsert_entries(key_a, [entry("c0", (1.0, 0.0), text="tenant A secret")])

        # Tenant B addressing the SAME document_id sees an unknown set, never data.
        with pytest.raises(UnknownSetError):
            vector_index.query(key_b, (1.0, 0.0), limit=10)
        assert vector_index.list_sets(tenant_id=TENANT_B, document_id="doc_mbr001") == ()
        assert vector_index.get_default(tenant_id=TENANT_B, document_id="doc_mbr001") is None

    def test_tenant_partitions_are_disjoint_even_for_identical_keys_but_tenant(self, vector_index: VectorIndex) -> None:
        key_a, key_b = structural_key(TENANT_A), structural_key(TENANT_B)
        for key, text in ((key_a, "alpha"), (key_b, "beta")):
            vector_index.register_set(key, created_at=0.0)
            vector_index.upsert_entries(key, [entry("c0", (1.0, 0.0), text=text)])

        hits_a = vector_index.query(key_a, (1.0, 0.0), limit=10)
        hits_b = vector_index.query(key_b, (1.0, 0.0), limit=10)
        assert [hit.entry.text for hit in hits_a] == ["alpha"]
        assert [hit.entry.text for hit in hits_b] == ["beta"]


class TestDeletion:
    def test_delete_set_verified_by_read_after_delete(self, vector_index: VectorIndex) -> None:
        key = structural_key()
        vector_index.register_set(key, created_at=0.0)
        vector_index.upsert_entries(key, [entry("c0", (1.0, 0.0))])
        vector_index.mark_complete(key)
        vector_index.set_default(key)

        vector_index.delete_set(key)

        with pytest.raises(UnknownSetError):
            vector_index.query(key, (1.0, 0.0), limit=1)
        with pytest.raises(UnknownSetError):
            vector_index.entry_ids(key)
        assert vector_index.list_sets(tenant_id=TENANT_A, document_id="doc_mbr001") == ()
        assert vector_index.get_default(tenant_id=TENANT_A, document_id="doc_mbr001") is None

    def test_delete_tenant_removes_every_set_and_version(self, vector_index: VectorIndex) -> None:
        keys = (structural_key(), semantic_key(mask_version=1), semantic_key(mask_version=2))
        for key in keys:
            vector_index.register_set(key, created_at=0.0)
            vector_index.upsert_entries(key, [entry("c0", (1.0, 0.0))])
            vector_index.mark_complete(key)
        vector_index.set_default(keys[-1])
        untouched = structural_key(TENANT_B, document_id="doc_other")
        vector_index.register_set(untouched, created_at=0.0)
        vector_index.upsert_entries(untouched, [entry("c0", (0.0, 1.0))])

        vector_index.delete_tenant(tenant_id=TENANT_A)

        # Read-after-delete verification across ALL versions (retention leak guard).
        assert vector_index.list_sets(tenant_id=TENANT_A, document_id="doc_mbr001") == ()
        assert vector_index.get_default(tenant_id=TENANT_A, document_id="doc_mbr001") is None
        for key in keys:
            with pytest.raises(UnknownSetError):
                vector_index.query(key, (1.0, 0.0), limit=1)
            with pytest.raises(UnknownSetError):
                vector_index.entry_ids(key)
        # The other tenant's data is untouched.
        assert vector_index.entry_ids(untouched) == frozenset({"c0"})

    def test_delete_missing_set_is_idempotent_no_op(self, vector_index: VectorIndex) -> None:
        vector_index.delete_set(structural_key())  # must not raise
        vector_index.delete_tenant(tenant_id="t-never-seen")  # must not raise
