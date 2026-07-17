"""ObjectStore port: content-addressed binary storage (epic E03).

Callers derive the key (see `services/ingestion/identity.py`'s
`deterministic_object_key`) — the store itself never inspects or hashes
content, it just persists bytes under a caller-chosen key exactly once.

Two adapters implement this port: `adapters/objectstore/local_fs.py` (dev/test)
and `adapters/objectstore/s3.py` (S3-compatible, prod). Both pass the same
contract-test suite (`tests/unit/adapters/objectstore/test_contract.py`), so
either is safely substitutable (Liskov) behind the `IngestionService`.

Pure interface: no I/O here, no framework imports.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class ObjectNotFoundError(Exception):
    """Raised by `ObjectStore.get` when `key` has never been written."""

    def __init__(self, key: str) -> None:
        super().__init__(f"object not found: {key!r}")
        self.key = key


@runtime_checkable
class ObjectStore(Protocol):
    def put_if_absent(self, key: str, data: bytes) -> bool:
        """Write `data` at `key` iff nothing is stored there yet.

        Returns True if this call performed the write, False if `key` was
        already present (in which case the existing bytes are left
        untouched). Because keys are content-addressed, a "loser" of a race
        between two writers with identical `key` is by construction writing
        identical bytes, so callers never need to distinguish "I wrote it"
        from "someone else already had").
        """
        ...

    def get(self, key: str) -> bytes:
        """Return the bytes stored at `key`. Raises ObjectNotFoundError if absent."""
        ...

    def exists(self, key: str) -> bool:
        """True iff `key` has been written."""
        ...

    def delete(self, key: str) -> None:
        """Remove `key` if present. Idempotent: deleting a missing key is a no-op
        (compensating deletes — e.g. from reconciliation — must not fail on a key
        that was already cleaned up by a previous, possibly-crashed, attempt)."""
        ...
