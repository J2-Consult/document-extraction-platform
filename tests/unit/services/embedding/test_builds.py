"""EmbeddingBuildService: version-paired, async, idempotently-resumable builds.

Version pairing (criterion 15 semantics at unit scale): activation schedules
an ASYNC build alongside the currently-serving set; the retrieval default
switches ONLY when the new set completes; older sets remain explicitly
queryable; an interrupted build resumes idempotently on job replay (pairs
with criterion 14); GC honors the retention policy; tenant deletion removes
ALL versions, verified by read-after-delete.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pytest

from adapters.jobs.in_memory import InMemoryJobQueue
from adapters.vectorindex.in_memory import HashEmbedder, InMemoryVectorIndex
from ports.jobs import JobStatus
from ports.vectorindex import Embedder, EmbeddingSetKey, SetStatus, UnknownSetError
from services.embedding.chunkers import DecodedElement
from tests.unit.fakes.clock import FakeClock

TENANT = "t-nordvik"
DOCUMENT = "doc_mbr001"
BEARING_TEXT = "Main rotor bearing inspected per AMM."
GASKET_TEXT = "Replaced worn gasket per work order."

_PROVENANCE: Mapping[str, Any] = {
    "source": {"artifact_sha256": "e" * 64, "page": 1},
    "working": {"artifact_sha256": "e" * 64, "coordinate_space": "page-1"},
    "bbox": [56.0, 496.0, 540.0, 528.0],
    "method": "pdf_text",
    "component_version": "fixture-1.0.0",
    "transform_to_source": [1, 0, 0, 1, 0, 0],
}


class CountingEmbedder:
    """Wraps HashEmbedder, counting embeds per text (proves resume skips work)."""

    def __init__(self) -> None:
        self._inner = HashEmbedder(dimensions=8)
        self.calls: dict[str, int] = {}

    def embed(self, text: str) -> tuple[float, ...]:
        self.calls[text] = self.calls.get(text, 0) + 1
        return self._inner.embed(text)


class InterruptingEmbedder(CountingEmbedder):
    """Raises once after `succeed_before` successful embeds (a crashed worker)."""

    def __init__(self, *, succeed_before: int) -> None:
        super().__init__()
        self._remaining = succeed_before
        self._tripped = False

    def embed(self, text: str) -> tuple[float, ...]:
        if not self._tripped and self._remaining == 0:
            self._tripped = True
            raise RuntimeError("simulated worker crash mid-build")
        if not self._tripped:
            self._remaining -= 1
        return super().embed(text)


def structural_key() -> EmbeddingSetKey:
    return EmbeddingSetKey(
        tenant_id=TENANT,
        document_id=DOCUMENT,
        mask_id=None,
        mask_version=None,
        template_id="tmpl_mbr",
        template_version=1,
    )


def semantic_key(mask_version: int = 1) -> EmbeddingSetKey:
    return EmbeddingSetKey(
        tenant_id=TENANT,
        document_id=DOCUMENT,
        mask_id="mask_mbrvendor",
        mask_version=mask_version,
        template_id="tmpl_mbr",
        template_version=1,
    )


def element(
    element_id: str, text: str, *, semantic_role: str | None = None, section_path: str | None = None
) -> DecodedElement:
    return DecodedElement(
        document_id=DOCUMENT,
        element_id=element_id,
        text=text,
        page=1,
        bbox=(56.0, 496.0, 540.0, 528.0),
        provenance=_PROVENANCE,
        semantic_role=semantic_role,
        system_context="cmms" if semantic_role else None,
        section_path=section_path,
    )


STRUCTURAL_ELEMENTS = (
    element("el_sec_13_4", BEARING_TEXT, section_path="13.4"),
    element("el_sec_16_3", GASKET_TEXT, section_path="16.3"),
)
SEMANTIC_ELEMENTS = (
    element("el_sec_13_4", BEARING_TEXT, semantic_role="bearing_inspection_notes", section_path="13.4"),
    element("el_sec_16_3", GASKET_TEXT, semantic_role="corrective_actions_notes", section_path="16.3"),
)


@dataclass
class Harness:
    service: Any
    index: InMemoryVectorIndex
    jobs: InMemoryJobQueue
    clock: FakeClock

    def with_embedder(self, embedder: Embedder) -> Any:
        """A second service instance over the SAME index/jobs/clock (constructor
        injection makes this trivial — no globals to fight)."""
        return _make_service(embedder, self.index, self.jobs, self.clock)


def _make_service(embedder: Embedder, index: InMemoryVectorIndex, jobs: InMemoryJobQueue, clock: FakeClock) -> Any:
    from services.embedding.builds import EmbeddingBuildService, RetentionPolicy

    return EmbeddingBuildService(
        index=index,
        embedder=embedder,
        jobs=jobs,
        clock=clock,
        retention=RetentionPolicy(keep_complete_sets=2),
        structural_window_tokens=32,
        structural_overlap_tokens=8,
    )


def build_harness(embedder: Embedder | None = None) -> Harness:
    clock = FakeClock()
    index = InMemoryVectorIndex()
    jobs = InMemoryJobQueue(clock=clock)
    return Harness(
        service=_make_service(embedder or CountingEmbedder(), index, jobs, clock),
        index=index,
        jobs=jobs,
        clock=clock,
    )


class TestStructuralImmediateBuild:
    def test_unmasked_document_gets_a_complete_default_structural_set_immediately(self) -> None:
        harness = build_harness()

        key = harness.service.build_structural_set(structural_key(), STRUCTURAL_ELEMENTS)

        records = harness.index.list_sets(tenant_id=TENANT, document_id=DOCUMENT)
        assert [record.key for record in records] == [key]
        assert records[0].status == SetStatus.COMPLETE
        assert harness.index.get_default(tenant_id=TENANT, document_id=DOCUMENT) == key
        assert harness.index.entry_ids(key) != frozenset()


class TestAsyncSemanticBuildPairing:
    def test_activation_schedules_an_async_job_and_does_not_touch_the_serving_default(self) -> None:
        harness = build_harness()
        serving = harness.service.build_structural_set(structural_key(), STRUCTURAL_ELEMENTS)

        job = harness.service.schedule_semantic_build(semantic_key())

        assert harness.jobs.get(job.job_id) is not None
        assert job.status == JobStatus.QUEUED
        # The new set is registered BUILDING alongside the serving set...
        statuses = {
            record.key: record.status for record in harness.index.list_sets(tenant_id=TENANT, document_id=DOCUMENT)
        }
        assert statuses == {serving: SetStatus.COMPLETE, semantic_key(): SetStatus.BUILDING}
        # ...and the default still points at the old set (structural keeps serving).
        assert harness.index.get_default(tenant_id=TENANT, document_id=DOCUMENT) == serving

    def test_scheduling_the_same_build_twice_yields_one_job(self) -> None:
        harness = build_harness()

        first = harness.service.schedule_semantic_build(semantic_key())
        second = harness.service.schedule_semantic_build(semantic_key())

        assert first.job_id == second.job_id

    def test_default_switches_only_when_the_new_set_completes_and_old_set_stays_queryable(self) -> None:
        harness = build_harness()
        serving = harness.service.build_structural_set(structural_key(), STRUCTURAL_ELEMENTS)
        harness.service.schedule_semantic_build(semantic_key())

        leased = harness.jobs.lease(kind="embedding_build")
        assert leased is not None
        harness.service.run_build(leased, SEMANTIC_ELEMENTS)

        # Both sets coexist keyed by version; default = the newly complete semantic set.
        statuses = {
            record.key: record.status for record in harness.index.list_sets(tenant_id=TENANT, document_id=DOCUMENT)
        }
        assert statuses == {serving: SetStatus.COMPLETE, semantic_key(): SetStatus.COMPLETE}
        assert harness.index.get_default(tenant_id=TENANT, document_id=DOCUMENT) == semantic_key()
        job = harness.jobs.get(leased.job_id)
        assert job is not None and job.status == JobStatus.COMPLETED
        # The older set remains EXPLICITLY queryable by its key.
        old_hits = harness.index.query(serving, HashEmbedder(dimensions=8).embed(BEARING_TEXT), limit=1)
        assert old_hits[0].entry.text == BEARING_TEXT


class TestInterruptedBuildResumesIdempotently:
    def test_job_replay_resumes_without_reembedding_indexed_chunks(self) -> None:
        harness = build_harness()
        harness.service.build_structural_set(structural_key(), STRUCTURAL_ELEMENTS)
        embedder = InterruptingEmbedder(succeed_before=1)
        service = harness.with_embedder(embedder)
        service.schedule_semantic_build(semantic_key())

        leased = harness.jobs.lease(kind="embedding_build")
        assert leased is not None
        with pytest.raises(RuntimeError):
            service.run_build(leased, SEMANTIC_ELEMENTS)  # crashes after chunk 1
        harness.jobs.fail(leased.job_id, reason="worker crash")

        # Partial progress persisted; default untouched (set incomplete).
        assert len(harness.index.entry_ids(semantic_key())) == 1
        assert harness.index.get_default(tenant_id=TENANT, document_id=DOCUMENT) == structural_key()

        harness.clock.advance(60.0)  # past backoff
        redelivered = harness.jobs.lease(kind="embedding_build")
        assert redelivered is not None and redelivered.job_id == leased.job_id
        service.run_build(redelivered, SEMANTIC_ELEMENTS)

        assert len(harness.index.entry_ids(semantic_key())) == 2
        assert harness.index.get_default(tenant_id=TENANT, document_id=DOCUMENT) == semantic_key()
        # The chunk indexed before the crash was embedded exactly once, ever.
        assert embedder.calls[BEARING_TEXT] == 1

    def test_running_an_already_completed_build_job_is_a_no_op(self) -> None:
        embedder = CountingEmbedder()
        harness = build_harness(embedder)
        harness.service.schedule_semantic_build(semantic_key())
        leased = harness.jobs.lease(kind="embedding_build")
        assert leased is not None
        harness.service.run_build(leased, SEMANTIC_ELEMENTS)
        calls_after_first = dict(embedder.calls)

        harness.service.run_build(leased, SEMANTIC_ELEMENTS)  # worker redelivery of a done job

        assert embedder.calls == calls_after_first
        assert len(harness.index.entry_ids(semantic_key())) == 2


class TestRetentionAndDeletion:
    def _complete_semantic_build(self, harness: Harness, version: int) -> None:
        harness.service.schedule_semantic_build(semantic_key(version))
        leased = harness.jobs.lease(kind="embedding_build")
        assert leased is not None
        harness.service.run_build(leased, SEMANTIC_ELEMENTS)

    def test_gc_honors_the_retention_policy_and_never_deletes_the_default(self) -> None:
        harness = build_harness()
        harness.service.build_structural_set(structural_key(), STRUCTURAL_ELEMENTS)
        for version in (1, 2, 3):
            harness.clock.advance(1.0)
            self._complete_semantic_build(harness, version)

        harness.service.collect_garbage(tenant_id=TENANT, document_id=DOCUMENT)

        # keep_complete_sets=2: the two most recent complete sets survive
        # (semantic v2, v3 — v3 is also the default); older ones are gone.
        remaining = {record.key for record in harness.index.list_sets(tenant_id=TENANT, document_id=DOCUMENT)}
        assert remaining == {semantic_key(2), semantic_key(3)}
        assert harness.index.get_default(tenant_id=TENANT, document_id=DOCUMENT) == semantic_key(3)

    def test_gc_never_deletes_a_building_set(self) -> None:
        harness = build_harness()
        harness.service.build_structural_set(structural_key(), STRUCTURAL_ELEMENTS)
        for version in (1, 2):
            harness.clock.advance(1.0)
            self._complete_semantic_build(harness, version)
        harness.clock.advance(1.0)
        harness.service.schedule_semantic_build(semantic_key(3))  # still BUILDING

        harness.service.collect_garbage(tenant_id=TENANT, document_id=DOCUMENT)

        remaining = {record.key for record in harness.index.list_sets(tenant_id=TENANT, document_id=DOCUMENT)}
        assert semantic_key(3) in remaining  # building set untouched
        assert remaining == {semantic_key(1), semantic_key(2), semantic_key(3)}

    def test_tenant_deletion_cascades_over_all_versions_with_read_after_delete_verification(self) -> None:
        harness = build_harness()
        structural = harness.service.build_structural_set(structural_key(), STRUCTURAL_ELEMENTS)
        for version in (1, 2):
            harness.clock.advance(1.0)
            self._complete_semantic_build(harness, version)

        harness.service.delete_tenant(tenant_id=TENANT)

        # Read-after-delete: EVERY version is gone (the classic retention leak).
        assert harness.index.list_sets(tenant_id=TENANT, document_id=DOCUMENT) == ()
        assert harness.index.get_default(tenant_id=TENANT, document_id=DOCUMENT) is None
        for key in (structural, semantic_key(1), semantic_key(2)):
            with pytest.raises(UnknownSetError):
                harness.index.entry_ids(key)
            with pytest.raises(UnknownSetError):
                harness.index.query(key, HashEmbedder(dimensions=8).embed("x"), limit=1)
