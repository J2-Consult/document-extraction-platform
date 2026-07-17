"""IngestionService behavior (epic E03 "Tests first" + criterion 14):

- replaying the same upload N times -> one object, one document, one job
- masquerading file (exe named .pdf) rejected by magic bytes
- oversized upload rejected
- sanitizer invoked for PDF uploads
"""

from __future__ import annotations

import pytest

from services.ingestion.service import IngestionService
from services.ingestion.validation import UnsupportedMediaTypeError, UploadTooLargeError
from tests.unit.services.ingestion.fakes import InMemoryIngestionRepository, InMemoryObjectStore, SpyPdfSanitizer

PDF_BYTES = b"%PDF-1.7\n%...\n1 0 obj\n<< >>\nendobj\n%%EOF"
EXE_MASQUERADING_AS_PDF = b"MZ\x90\x00\x03\x00\x00\x00not a pdf at all"
TENANT = "t-nordvik"


def _service(
    *, max_upload_bytes: int = 25 * 1024 * 1024
) -> tuple[IngestionService, InMemoryObjectStore, InMemoryIngestionRepository, SpyPdfSanitizer]:
    store = InMemoryObjectStore()
    repo = InMemoryIngestionRepository()
    sanitizer = SpyPdfSanitizer()
    service = IngestionService(store, repo, sanitizer, max_upload_bytes=max_upload_bytes)
    return service, store, repo, sanitizer


def test_replaying_the_same_upload_n_times_yields_one_object_one_document_one_job() -> None:
    service, store, repo, _sanitizer = _service()

    results = [
        service.ingest(tenant_id=TENANT, intent="extract", original_filename="invoice.pdf", data=PDF_BYTES)
        for _ in range(5)
    ]

    assert len({r.document_id for r in results}) == 1
    assert len({r.job_id for r in results}) == 1
    assert repo.document_count(TENANT) == 1
    assert len(store.list_all_keys()) == 1
    assert results[0].replayed is False
    assert all(r.replayed is True for r in results[1:])


def test_different_intent_for_the_same_bytes_yields_a_distinct_document() -> None:
    service, _store, repo, _sanitizer = _service()

    service.ingest(tenant_id=TENANT, intent="extract", original_filename="invoice.pdf", data=PDF_BYTES)
    service.ingest(tenant_id=TENANT, intent="reprocess", original_filename="invoice.pdf", data=PDF_BYTES)

    assert repo.document_count(TENANT) == 2


def test_exe_masquerading_as_pdf_is_rejected_and_nothing_is_stored_or_registered() -> None:
    service, store, repo, _sanitizer = _service()

    with pytest.raises(UnsupportedMediaTypeError):
        service.ingest(
            tenant_id=TENANT, intent="extract", original_filename="invoice.pdf", data=EXE_MASQUERADING_AS_PDF
        )

    assert store.list_all_keys() == frozenset()
    assert repo.document_count(TENANT) == 0


def test_oversized_upload_is_rejected() -> None:
    service, store, repo, _sanitizer = _service(max_upload_bytes=10)

    with pytest.raises(UploadTooLargeError):
        service.ingest(tenant_id=TENANT, intent="extract", original_filename="invoice.pdf", data=PDF_BYTES)

    assert store.list_all_keys() == frozenset()
    assert repo.document_count(TENANT) == 0


def test_sanitizer_is_invoked_for_pdf_uploads() -> None:
    service, _store, _repo, sanitizer = _service()

    service.ingest(tenant_id=TENANT, intent="extract", original_filename="invoice.pdf", data=PDF_BYTES)

    assert sanitizer.calls == [PDF_BYTES]


def test_object_is_stored_at_a_deterministic_sha256_derived_key() -> None:
    service, store, _repo, _sanitizer = _service()

    result = service.ingest(tenant_id=TENANT, intent="extract", original_filename="invoice.pdf", data=PDF_BYTES)

    (only_key,) = store.list_all_keys()
    assert result.source_sha256 in only_key
    assert only_key.startswith(f"{TENANT}/")
