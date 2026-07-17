"""EmbeddingBuildService (epic E11): version-paired embedding-set builds.

Version pairing (architecture §7.5, ADR 16): a mask activation schedules an
ASYNC build (an E03 `JobQueue` job) alongside the currently-serving set; the
retrieval default switches ONLY when the new set completes (`set_default`
itself refuses incomplete sets); older sets remain explicitly queryable by
their `EmbeddingSetKey` until GC'd. Builds are idempotent under job replay:
progress is upserted chunk-by-chunk and `entry_ids` is the resume cursor, so
a redelivered job re-embeds nothing it already indexed (pairs with the
criterion-14 redelivery semantics).

Retention: `RetentionPolicy(keep_complete_sets=N)` — GC keeps the N most
recent COMPLETE sets per document, never a still-building set and never the
current default. Tenant deletion cascades over EVERY set and version through
the port's `delete_tenant` (deletion is verified by read-after-delete in the
contract suite — forgotten embeddings are the classic retention leak).

Logging/observability note: nothing here logs; identifiers and states are in
job payloads and index keys only — chunk text never leaves the index entries.

Constructor injection only; all effects go through the `VectorIndex`,
`Embedder`, `JobQueue`, and `Clock` ports.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ports.clock import Clock
from ports.jobs import Job, JobQueue
from ports.vectorindex import Embedder, EmbeddingSetKey, IndexEntry, SetStatus, VectorIndex
from services.embedding.chunkers import Chunk, Chunker, DecodedElement, SemanticChunker, StructuralChunker

EMBEDDING_BUILD_JOB_KIND = "embedding_build"


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    """How many COMPLETE embedding sets to keep per document after GC."""

    keep_complete_sets: int

    def __post_init__(self) -> None:
        if self.keep_complete_sets < 1:
            raise ValueError(f"keep_complete_sets must be >= 1, got {self.keep_complete_sets}")


def _entry_from_chunk(chunk: Chunk, vector: tuple[float, ...]) -> IndexEntry:
    """Chunk text + metadata + provenance only — never document bytes."""
    return IndexEntry(
        chunk_id=chunk.chunk_id,
        vector=vector,
        text=chunk.text,
        page=chunk.page,
        bbox=chunk.bbox,
        provenance=chunk.provenance,
        section_path=chunk.section_path,
        semantic_role=chunk.semantic_role,
        system_context=chunk.system_context,
    )


def _idempotency_key(key: EmbeddingSetKey) -> str:
    if key.tier == "semantic":
        return f"embedding-build:{key.document_id}:mask:{key.mask_id}:{key.mask_version}"
    return f"embedding-build:{key.document_id}:structural:{key.template_id}:{key.template_version}"


def _payload(key: EmbeddingSetKey) -> dict[str, object]:
    return {
        "tenant_id": key.tenant_id,
        "document_id": key.document_id,
        "mask_id": key.mask_id,
        "mask_version": key.mask_version,
        "template_id": key.template_id,
        "template_version": key.template_version,
    }


def _key_from_payload(payload: dict[str, object]) -> EmbeddingSetKey:
    return EmbeddingSetKey(
        tenant_id=str(payload["tenant_id"]),
        document_id=str(payload["document_id"]),
        mask_id=str(payload["mask_id"]) if payload["mask_id"] is not None else None,
        mask_version=int(str(payload["mask_version"])) if payload["mask_version"] is not None else None,
        template_id=str(payload["template_id"]) if payload["template_id"] is not None else None,
        template_version=int(str(payload["template_version"])) if payload["template_version"] is not None else None,
    )


class EmbeddingBuildService:
    """Builds, pairs, serves, retains, and deletes embedding sets."""

    def __init__(
        self,
        *,
        index: VectorIndex,
        embedder: Embedder,
        jobs: JobQueue,
        clock: Clock,
        retention: RetentionPolicy,
        structural_window_tokens: int,
        structural_overlap_tokens: int,
    ) -> None:
        self._index = index
        self._embedder = embedder
        self._jobs = jobs
        self._clock = clock
        self._retention = retention
        self._semantic_chunker = SemanticChunker()
        self._structural_chunker = StructuralChunker(
            window_tokens=structural_window_tokens,
            overlap_tokens=structural_overlap_tokens,
        )

    def build_structural_set(self, key: EmbeddingSetKey, elements: Sequence[DecodedElement]) -> EmbeddingSetKey:
        """The unmasked path: build and serve the structural set immediately."""
        if key.tier != "structural":
            raise ValueError(f"structural build called with a {key.tier} key for {key.document_id}")
        self._index.register_set(key, created_at=self._clock.now())
        self._index_missing_chunks(key, self._structural_chunker.chunk(elements))
        self._complete_and_serve(key)
        return key

    def schedule_semantic_build(self, key: EmbeddingSetKey) -> Job:
        """Mask activation hook: enqueue an async build ALONGSIDE the serving
        set. The new set registers as BUILDING; the default does not move."""
        if key.tier != "semantic":
            raise ValueError(f"semantic build scheduled with a {key.tier} key for {key.document_id}")
        self._index.register_set(key, created_at=self._clock.now())
        return self._jobs.enqueue(
            tenant_id=key.tenant_id,
            kind=EMBEDDING_BUILD_JOB_KIND,
            idempotency_key=_idempotency_key(key),
            payload=_payload(key),
        )

    def run_build(self, job: Job, elements: Sequence[DecodedElement]) -> None:
        """Worker entry point: chunk, embed, and index — resumable at any chunk.

        Replay-safe by construction: an already-complete set short-circuits to
        `jobs.complete` (redelivery no-op); otherwise `entry_ids` is the
        resume cursor and only missing chunks are embedded.
        """
        key = _key_from_payload(job.payload)
        self._index.register_set(key, created_at=self._clock.now())  # replay: no-op
        if self._status(key) == SetStatus.COMPLETE:
            self._jobs.complete(job.job_id)
            return
        self._index_missing_chunks(key, self._chunker_for(key).chunk(elements))
        self._complete_and_serve(key)
        self._jobs.complete(job.job_id)

    def collect_garbage(self, *, tenant_id: str, document_id: str) -> None:
        """Retention: keep the N most recent COMPLETE sets; never a building
        set, never the current default."""
        records = self._index.list_sets(tenant_id=tenant_id, document_id=document_id)
        complete = [record for record in records if record.status == SetStatus.COMPLETE]
        complete.sort(key=lambda record: record.created_at, reverse=True)
        default = self._index.get_default(tenant_id=tenant_id, document_id=document_id)
        for record in complete[self._retention.keep_complete_sets :]:
            if record.key != default:
                self._index.delete_set(record.key)

    def delete_tenant(self, *, tenant_id: str) -> None:
        """Tenant-deletion cascade: every set, every version, every pointer."""
        self._index.delete_tenant(tenant_id=tenant_id)

    def _chunker_for(self, key: EmbeddingSetKey) -> Chunker:
        return self._semantic_chunker if key.tier == "semantic" else self._structural_chunker

    def _index_missing_chunks(self, key: EmbeddingSetKey, chunks: Sequence[Chunk]) -> None:
        already_indexed = self._index.entry_ids(key)
        for chunk in chunks:
            if chunk.chunk_id in already_indexed:
                continue  # resume: never re-embed indexed work
            vector = self._embedder.embed(chunk.text)
            self._index.upsert_entries(key, [_entry_from_chunk(chunk, vector)])

    def _complete_and_serve(self, key: EmbeddingSetKey) -> None:
        """Completion IS the switch point: the default moves here and only here."""
        self._index.mark_complete(key)
        self._index.set_default(key)

    def _status(self, key: EmbeddingSetKey) -> SetStatus | None:
        for record in self._index.list_sets(tenant_id=key.tenant_id, document_id=key.document_id):
            if record.key == key:
                return record.status
        return None
