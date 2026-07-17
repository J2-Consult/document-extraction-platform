"""In-memory `VectorIndex` adapter + deterministic hash `Embedder` (epic E11).

The reference implementation the shared contract suite
(`tests/unit/adapters/vectorindex/test_contract.py`) runs against; a real
backend adapter must pass the identical suite. Similarity is cosine over
plain Python floats — no numpy, no model calls, no new dependencies.

Tenant partition: all state is keyed by `EmbeddingSetKey` (tenant-first) or
`(tenant_id, document_id)`, so a lookup under the wrong tenant is an
`UnknownSetError`/empty result by construction, never someone else's data.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from math import sqrt

from ports.vectorindex import (
    EmbeddingSetKey,
    IncompleteSetError,
    IndexEntry,
    SearchHit,
    SetRecord,
    SetStatus,
    UnknownSetError,
)

_HASH_BYTES_PER_COMPONENT = 4
_COMPONENT_SCALE = float(2 ** (8 * _HASH_BYTES_PER_COMPONENT))


class HashEmbedder:
    """Deterministic fake `Embedder`: sha256-derived floats in [0, 1]."""

    def __init__(self, *, dimensions: int) -> None:
        if dimensions < 1:
            raise ValueError(f"dimensions must be >= 1, got {dimensions}")
        self._dimensions = dimensions

    def embed(self, text: str) -> tuple[float, ...]:
        components: list[float] = []
        block = 0
        while len(components) < self._dimensions:
            digest = hashlib.sha256(f"{block}:{text}".encode()).digest()
            for offset in range(0, len(digest), _HASH_BYTES_PER_COMPONENT):
                word = digest[offset : offset + _HASH_BYTES_PER_COMPONENT]
                components.append(int.from_bytes(word, "big") / _COMPONENT_SCALE)
            block += 1
        return tuple(components[: self._dimensions])


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    """Cosine similarity over plain floats; 0.0 when either vector is zero."""
    if len(left) != len(right):
        raise ValueError(f"vector dimensions differ: {len(left)} vs {len(right)}")
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = sqrt(sum(a * a for a in left))
    right_norm = sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


class InMemoryVectorIndex:
    """`VectorIndex` backed by plain dicts; one process, no persistence."""

    def __init__(self) -> None:
        self._sets: dict[EmbeddingSetKey, SetRecord] = {}
        self._entries: dict[EmbeddingSetKey, dict[str, IndexEntry]] = {}
        self._defaults: dict[tuple[str, str], EmbeddingSetKey] = {}

    def register_set(self, key: EmbeddingSetKey, *, created_at: float) -> None:
        if key in self._sets:
            return  # idempotent replay: never reset an existing set
        self._sets[key] = SetRecord(key=key, status=SetStatus.BUILDING, created_at=created_at)
        self._entries[key] = {}

    def upsert_entries(self, key: EmbeddingSetKey, entries: Sequence[IndexEntry]) -> None:
        stored = self._entries_or_raise(key)
        for entry in entries:
            stored[entry.chunk_id] = entry

    def entry_ids(self, key: EmbeddingSetKey) -> frozenset[str]:
        return frozenset(self._entries_or_raise(key))

    def mark_complete(self, key: EmbeddingSetKey) -> None:
        record = self._record_or_raise(key)
        self._sets[key] = SetRecord(key=key, status=SetStatus.COMPLETE, created_at=record.created_at)

    def query(
        self,
        key: EmbeddingSetKey,
        vector: Sequence[float],
        *,
        limit: int,
        section_path: str | None = None,
    ) -> tuple[SearchHit, ...]:
        if limit < 1:
            raise ValueError(f"limit must be >= 1, got {limit}")
        candidates = (
            entry
            for entry in self._entries_or_raise(key).values()
            if section_path is None or entry.section_path == section_path
        )
        hits = [SearchHit(entry=entry, score=cosine_similarity(vector, entry.vector)) for entry in candidates]
        hits.sort(key=lambda hit: (-hit.score, hit.entry.chunk_id))
        return tuple(hits[:limit])

    def list_sets(self, *, tenant_id: str, document_id: str) -> tuple[SetRecord, ...]:
        records = [
            record
            for record in self._sets.values()
            if record.key.tenant_id == tenant_id and record.key.document_id == document_id
        ]
        records.sort(key=lambda record: record.created_at)
        return tuple(records)

    def set_default(self, key: EmbeddingSetKey) -> None:
        record = self._record_or_raise(key)
        if record.status != SetStatus.COMPLETE:
            raise IncompleteSetError(
                f"set for {key.document_id} (tier={key.tier}) is still building — "
                "the retrieval default switches only when a build completes"
            )
        self._defaults[(key.tenant_id, key.document_id)] = key

    def get_default(self, *, tenant_id: str, document_id: str) -> EmbeddingSetKey | None:
        return self._defaults.get((tenant_id, document_id))

    def delete_set(self, key: EmbeddingSetKey) -> None:
        self._sets.pop(key, None)
        self._entries.pop(key, None)
        pointer = (key.tenant_id, key.document_id)
        if self._defaults.get(pointer) == key:
            del self._defaults[pointer]

    def delete_tenant(self, *, tenant_id: str) -> None:
        for key in [key for key in self._sets if key.tenant_id == tenant_id]:
            del self._sets[key]
            del self._entries[key]
        for pointer in [pointer for pointer in self._defaults if pointer[0] == tenant_id]:
            del self._defaults[pointer]

    def _record_or_raise(self, key: EmbeddingSetKey) -> SetRecord:
        record = self._sets.get(key)
        if record is None:
            raise UnknownSetError(f"no embedding set for document {key.document_id} (tier={key.tier})")
        return record

    def _entries_or_raise(self, key: EmbeddingSetKey) -> dict[str, IndexEntry]:
        self._record_or_raise(key)
        return self._entries[key]
