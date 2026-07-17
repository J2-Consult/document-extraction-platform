"""VectorIndex + Embedder ports (epic E11): version-paired embedding sets.

The unit of storage is an embedding SET addressed by `EmbeddingSetKey` —
`(tenant_id, document_id, mask_id | None, mask_version | None)`, with the
structural tier keyed by template version and a null mask. TENANT PARTITION
IS IMPOSSIBLE TO OMIT AT THE TYPE LEVEL: every port method takes either an
`EmbeddingSetKey` (whose `tenant_id` is a required, validated, non-empty
`str`) or an explicit `tenant_id` keyword — there is no unscoped read, write,
or delete anywhere on this interface, so cross-tenant retrieval cannot be
expressed, only rejected.

Entries carry chunk text + metadata + provenance ONLY — never a whole
document, never document bytes (E11 security note).

Set lifecycle is part of the contract because version pairing depends on it:
sets register as BUILDING, become COMPLETE, and only a COMPLETE set may be
made the retrieval default (`IncompleteSetError` otherwise) — "the default
switches only when the new set completes" is enforced here, not by caller
discipline. Older sets remain explicitly queryable by their key until
deleted; `delete_tenant` cascades over every set and version.

Pure interface + data shapes: stdlib only; no I/O, no framework imports.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal, Protocol, runtime_checkable

Tier = Literal["semantic", "structural"]


class UnknownSetError(Exception):
    """Addressed an embedding set that does not exist in this tenant's partition."""


class IncompleteSetError(Exception):
    """Tried to make a still-building set the retrieval default."""


@dataclass(frozen=True, slots=True)
class EmbeddingSetKey:
    """Identity of one embedding set: tenant-first, version-paired.

    Semantic tier: `mask_id` + `mask_version` set (the mask version the set
    was built against). Structural tier: both None, keyed by the template
    version used for heading-hierarchy addressing (or None for a document
    with no template at all).
    """

    tenant_id: str
    document_id: str
    mask_id: str | None
    mask_version: int | None
    template_id: str | None
    template_version: int | None

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("EmbeddingSetKey.tenant_id must be a non-empty tenant identifier")
        if not self.document_id:
            raise ValueError("EmbeddingSetKey.document_id must be non-empty")
        if (self.mask_id is None) != (self.mask_version is None):
            raise ValueError("mask_id and mask_version must be both set (semantic) or both None (structural)")
        if (self.template_id is None) != (self.template_version is None):
            raise ValueError("template_id and template_version must be both set or both None")

    @property
    def tier(self) -> Tier:
        return "structural" if self.mask_id is None else "semantic"


class SetStatus(StrEnum):
    BUILDING = "building"
    COMPLETE = "complete"


@dataclass(frozen=True, slots=True)
class IndexEntry:
    """One indexed chunk: vector + text + metadata + provenance, nothing more."""

    chunk_id: str
    vector: tuple[float, ...]
    text: str
    page: int
    bbox: tuple[float, float, float, float]
    provenance: Mapping[str, Any]
    section_path: str | None = None
    semantic_role: str | None = None
    system_context: str | None = None


@dataclass(frozen=True, slots=True)
class SearchHit:
    """One query result: the stored entry plus its similarity score."""

    entry: IndexEntry
    score: float


@dataclass(frozen=True, slots=True)
class SetRecord:
    """One embedding set's identity + lifecycle state, as listed per document."""

    key: EmbeddingSetKey
    status: SetStatus
    created_at: float


@runtime_checkable
class Embedder(Protocol):
    """Text -> embedding vector. The test/reference implementation is the
    deterministic hash-based fake; a real model provider is a future adapter."""

    def embed(self, text: str) -> tuple[float, ...]: ...


@runtime_checkable
class VectorIndex(Protocol):
    def register_set(self, key: EmbeddingSetKey, *, created_at: float) -> None:
        """Create the set in BUILDING state. Idempotent: re-registering an
        existing set (job replay) changes nothing."""
        ...

    def upsert_entries(self, key: EmbeddingSetKey, entries: Sequence[IndexEntry]) -> None:
        """Add entries to a registered set, idempotent per `chunk_id` (replay
        never duplicates). Raises `UnknownSetError` for an unregistered key."""
        ...

    def entry_ids(self, key: EmbeddingSetKey) -> frozenset[str]:
        """Chunk ids already indexed in the set (the resume cursor for an
        interrupted build). Raises `UnknownSetError` for an unknown key."""
        ...

    def mark_complete(self, key: EmbeddingSetKey) -> None:
        """Transition the set to COMPLETE. Raises `UnknownSetError` if absent."""
        ...

    def query(
        self,
        key: EmbeddingSetKey,
        vector: Sequence[float],
        *,
        limit: int,
        section_path: str | None = None,
    ) -> tuple[SearchHit, ...]:
        """Nearest entries of ONE set by descending similarity, bounded by
        `limit` (>= 1), optionally filtered to an exact `section_path`.
        Older sets stay explicitly queryable by their key. Raises
        `UnknownSetError` for an unknown key."""
        ...

    def list_sets(self, *, tenant_id: str, document_id: str) -> tuple[SetRecord, ...]:
        """Every embedding set of one document in one tenant partition."""
        ...

    def set_default(self, key: EmbeddingSetKey) -> None:
        """Make `key` the document's retrieval default. Raises
        `IncompleteSetError` while the set is still building (the default
        switches ONLY when a build completes) and `UnknownSetError` if absent."""
        ...

    def get_default(self, *, tenant_id: str, document_id: str) -> EmbeddingSetKey | None:
        """The document's current retrieval-default set, if any."""
        ...

    def delete_set(self, key: EmbeddingSetKey) -> None:
        """Remove one set and all its entries (idempotent no-op if absent);
        clears the default pointer if it pointed here."""
        ...

    def delete_tenant(self, *, tenant_id: str) -> None:
        """Tenant-deletion cascade: remove EVERY set, entry, and default
        pointer of the tenant, across all versions. Idempotent."""
        ...
