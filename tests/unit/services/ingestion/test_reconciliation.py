"""Reconciliation (epic E03 "Tests first"):

Kill-between-steps: object stored but the registration transaction rolled
back (process crash) -> reconciliation converges by deleting the orphan.
"""

from __future__ import annotations

import pytest

from services.ingestion.reconciliation import ReconciliationService
from services.ingestion.service import IngestionService
from tests.unit.services.ingestion.fakes import (
    CrashingIngestionRepository,
    InMemoryIngestionRepository,
    InMemoryObjectStore,
    SpyPdfSanitizer,
)

PDF_BYTES = b"%PDF-1.7\n%...\n1 0 obj\n<< >>\nendobj\n%%EOF"
TENANT = "t-nordvik"


def test_orphaned_object_from_a_rolled_back_registration_is_deleted_on_reconciliation() -> None:
    store = InMemoryObjectStore()
    real_repo = InMemoryIngestionRepository()
    crashing_repo = CrashingIngestionRepository(real_repo)
    service = IngestionService(store, crashing_repo, SpyPdfSanitizer())

    with pytest.raises(RuntimeError, match="simulated crash"):
        service.ingest(tenant_id=TENANT, intent="extract", original_filename="invoice.pdf", data=PDF_BYTES)

    # object survived the crash; no document was ever registered for it
    assert len(store.list_all_keys()) == 1
    assert real_repo.document_count(TENANT) == 0

    reconciliation = ReconciliationService(store, real_repo)
    report = reconciliation.reconcile(TENANT, store.list_all_keys)

    assert report.candidates_examined == 1
    assert len(report.orphans_deleted) == 1
    assert store.list_all_keys() == frozenset()


def test_reconciliation_leaves_correctly_registered_objects_alone() -> None:
    store = InMemoryObjectStore()
    repo = InMemoryIngestionRepository()
    service = IngestionService(store, repo, SpyPdfSanitizer())

    service.ingest(tenant_id=TENANT, intent="extract", original_filename="invoice.pdf", data=PDF_BYTES)

    reconciliation = ReconciliationService(store, repo)
    report = reconciliation.reconcile(TENANT, store.list_all_keys)

    assert report.orphans_deleted == ()
    assert len(store.list_all_keys()) == 1


def test_reconciliation_only_touches_the_given_tenants_keys() -> None:
    store = InMemoryObjectStore()
    repo = InMemoryIngestionRepository()
    crashing_repo = CrashingIngestionRepository(repo)
    service = IngestionService(store, crashing_repo, SpyPdfSanitizer())

    with pytest.raises(RuntimeError):
        service.ingest(tenant_id="t-other", intent="extract", original_filename="invoice.pdf", data=PDF_BYTES)

    reconciliation = ReconciliationService(store, repo)
    report = reconciliation.reconcile(TENANT, store.list_all_keys)

    assert report.candidates_examined == 0
    assert len(store.list_all_keys()) == 1  # t-other's orphan is untouched by a t-nordvik sweep
