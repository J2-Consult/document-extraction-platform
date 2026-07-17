"""In-memory test doubles for the ingestion unit-test suite. Never shipped."""

from __future__ import annotations

from ports.ingestion_repo import IngestionRepository, OutboxEntry, RegisteredUpload, UploadRegistration
from ports.objectstore import ObjectNotFoundError


class InMemoryObjectStore:
    """Pure in-memory `ObjectStore` — faster than `LocalFileSystemObjectStore`
    for service-level unit tests that don't care about disk atomicity (that is
    covered separately by the objectstore contract suite)."""

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    def put_if_absent(self, key: str, data: bytes) -> bool:
        if key in self._objects:
            return False
        self._objects[key] = bytes(data)
        return True

    def get(self, key: str) -> bytes:
        try:
            return self._objects[key]
        except KeyError as exc:
            raise ObjectNotFoundError(key) from exc

    def exists(self, key: str) -> bool:
        return key in self._objects

    def delete(self, key: str) -> None:
        self._objects.pop(key, None)

    def list_all_keys(self) -> frozenset[str]:
        return frozenset(self._objects.keys())


class InMemoryIngestionRepository:
    """Pure in-memory `IngestionRepository`. Mirrors the ON-CONFLICT-DO-NOTHING
    semantics the real Postgres adapter implements: deterministic ids make
    every insert past the first a safe no-op."""

    def __init__(self) -> None:
        self._documents: dict[tuple[str, str], UploadRegistration] = {}
        self._outbox: dict[str, OutboxEntry] = {}
        self._relayed: set[str] = set()

    def register_upload(self, registration: UploadRegistration) -> RegisteredUpload:
        key = (registration.tenant_id, registration.document_id)
        if key in self._documents:
            existing = self._documents[key]
            return RegisteredUpload(
                document_id=existing.document_id, job_id=existing.job_id, outbox_id=existing.outbox_id, replayed=True
            )
        self._documents[key] = registration
        self._outbox[registration.outbox_id] = OutboxEntry(
            outbox_id=registration.outbox_id,
            tenant_id=registration.tenant_id,
            job_kind=registration.job_kind,
            idempotency_key=registration.job_payload.get("idempotency_key", registration.outbox_id),  # type: ignore[arg-type]
            payload=registration.job_payload,
        )
        return RegisteredUpload(
            document_id=registration.document_id,
            job_id=registration.job_id,
            outbox_id=registration.outbox_id,
            replayed=False,
        )

    def registered_object_keys(self, tenant_id: str) -> frozenset[str]:
        return frozenset(reg.object_key for (tid, _document_id), reg in self._documents.items() if tid == tenant_id)

    def fetch_pending_outbox(self, tenant_id: str, limit: int = 100) -> tuple[OutboxEntry, ...]:
        pending = [
            entry
            for outbox_id, entry in self._outbox.items()
            if entry.tenant_id == tenant_id and outbox_id not in self._relayed
        ]
        return tuple(pending[:limit])

    def mark_outbox_relayed(self, tenant_id: str, outbox_id: str) -> None:
        del tenant_id  # unused: this fake keys the outbox by id alone
        self._relayed.add(outbox_id)

    def document_count(self, tenant_id: str) -> int:
        """Test-only helper: number of distinct documents registered for `tenant_id`."""
        return sum(1 for (tid, _document_id) in self._documents if tid == tenant_id)


class CrashingIngestionRepository:
    """Wraps a real `IngestionRepository` but raises before persisting anything
    — simulates the process dying mid-transaction (kill-between-steps)."""

    def __init__(self, delegate: IngestionRepository) -> None:
        self._delegate = delegate

    def register_upload(self, registration: UploadRegistration) -> RegisteredUpload:
        raise RuntimeError("simulated crash: transaction never committed")

    def registered_object_keys(self, tenant_id: str) -> frozenset[str]:
        return self._delegate.registered_object_keys(tenant_id)

    def fetch_pending_outbox(self, tenant_id: str, limit: int = 100) -> tuple[OutboxEntry, ...]:
        return self._delegate.fetch_pending_outbox(tenant_id, limit=limit)

    def mark_outbox_relayed(self, tenant_id: str, outbox_id: str) -> None:
        self._delegate.mark_outbox_relayed(tenant_id, outbox_id)


class SpyPdfSanitizer:
    """Records every call; pass-through behavior (spies on the real hook contract)."""

    def __init__(self) -> None:
        self.calls: list[bytes] = []

    def sanitize(self, data: bytes) -> bytes:
        self.calls.append(data)
        return data
