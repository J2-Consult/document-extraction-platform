"""Reconciliation (epic E03): converge orphaned objects after a kill-between-steps.

`IngestionService.ingest` stores the object BEFORE registering the document,
because the object store and Postgres are two separate systems with no shared
transaction. If the process dies (or `register_upload` raises) after the
store write but before the registration commits, the store is left holding an
object with no matching document row.

Since the original upload bytes are gone by the time reconciliation runs
(only the hash/key survive, in the object store itself), the only safe
convergence action is to delete the orphan: a future re-upload of the same
file recreates it via `put_if_absent`, so deleting it loses nothing.

Listing "everything actually in the store" is intentionally NOT part of the
narrow `ObjectStore` port (`put_if_absent`/`get`/`exists`/`delete` only) — the
port only needs to serve the ingestion hot path. This service instead takes
the candidate key listing as an explicit collaborator (e.g.
`LocalFileSystemObjectStore.list_all_keys`, or an S3 bucket listing driven
out-of-band), keeping that operational concern decoupled from the transactional one.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from ports.ingestion_repo import IngestionRepository
from ports.objectstore import ObjectStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReconciliationReport:
    tenant_id: str
    candidates_examined: int
    orphans_deleted: tuple[str, ...]


class ReconciliationService:
    def __init__(self, object_store: ObjectStore, repository: IngestionRepository) -> None:
        self._object_store = object_store
        self._repository = repository

    def reconcile(self, tenant_id: str, list_stored_keys: Callable[[], Iterable[str]]) -> ReconciliationReport:
        """Delete any stored object under `tenant_id` that no registered
        document references. `list_stored_keys` is adapter-specific (see
        module docstring) and expected to return ALL keys currently in the
        store, not just this tenant's — keys are prefixed by tenant, so this
        filters accordingly."""
        known = self._repository.registered_object_keys(tenant_id)
        candidates = [key for key in list_stored_keys() if key.startswith(f"{tenant_id}/")]
        orphans = [key for key in candidates if key not in known]

        for key in orphans:
            self._object_store.delete(key)
            logger.info("reconciliation deleted orphaned object", extra={"tenant_id": tenant_id, "object_key": key})

        return ReconciliationReport(
            tenant_id=tenant_id,
            candidates_examined=len(candidates),
            orphans_deleted=tuple(orphans),
        )
