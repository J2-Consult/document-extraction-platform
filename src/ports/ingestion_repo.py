"""IngestionRepository port (epic E03): transactional registration.

Registers a document + its processing job + an outbox row in one atomic unit
of work. Concrete adapters: `adapters/postgres/ingestion_repo.py` (real,
against E02's `documents`/`jobs` tables plus the additive `ingestion_outbox`
table from migration 0003) and an in-memory fake used by unit tests
(`tests/unit/services/ingestion/fakes.py` — a pure test double, never shipped).

`document_id`/`job_id`/`outbox_id` are computed by the caller (see
`services/ingestion/identity.py`) as deterministic hashes of
`(tenant_id, source_sha256, intent)`, so replaying the same upload N times
submits N structurally-identical `UploadRegistration`s and every insert past
the first is a safe no-op — the repository never has to run a
read-then-decide query to detect a replay, which is what keeps this a single
round-trip, single-transaction write under real concurrency (two racing
requests for the same file resolve via ON CONFLICT DO NOTHING, not via a
check-then-act race).

Pure interface + data shapes: no I/O here, no framework imports.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class UploadRegistration(BaseModel):
    """Everything one `register_upload` call needs to write; ids are
    deterministic (see module docstring), so this is safe to submit repeatedly."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    tenant_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    outbox_id: str = Field(min_length=1)
    intent: str = Field(min_length=1)
    source_sha256: str = Field(min_length=64, max_length=64)
    media_type: str = Field(min_length=1)
    size_bytes: int = Field(ge=0)
    original_filename: str
    object_key: str = Field(min_length=1)
    job_kind: str = Field(min_length=1)
    job_payload: dict[str, object] = Field(default_factory=dict)


class RegisteredUpload(BaseModel):
    """Result of `register_upload`: the (possibly pre-existing) identity."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    document_id: str
    job_id: str
    outbox_id: str
    replayed: bool = Field(description="True iff this call found a prior registration instead of creating one.")


class OutboxEntry(BaseModel):
    """One not-yet-relayed outbox row."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    outbox_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    job_kind: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    payload: dict[str, object] = Field(default_factory=dict)


@runtime_checkable
class IngestionRepository(Protocol):
    def register_upload(self, registration: UploadRegistration) -> RegisteredUpload:
        """Insert document + job + outbox row atomically. See module docstring
        for the idempotency contract."""
        ...

    def registered_object_keys(self, tenant_id: str) -> frozenset[str]:
        """Object-store keys already referenced by a registered document for
        this tenant. Used by reconciliation to find store objects that were
        written but never got a matching record (kill-between-steps)."""
        ...

    def fetch_pending_outbox(self, tenant_id: str, limit: int = 100) -> tuple[OutboxEntry, ...]:
        """Not-yet-relayed outbox rows for this tenant, oldest first."""
        ...

    def mark_outbox_relayed(self, tenant_id: str, outbox_id: str) -> None:
        """Mark an outbox row relayed. Idempotent: marking twice is a no-op.
        `tenant_id` is required (not derivable from `outbox_id` alone) because
        every write goes through a tenant-scoped RLS-gated transaction."""
        ...
