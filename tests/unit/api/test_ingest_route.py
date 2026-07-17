"""POST /ingest/documents (epic E03): thin router over IngestionService,
wired entirely with fakes — no DB, no network."""

from __future__ import annotations

from fastapi import Request
from fastapi.testclient import TestClient

from api.app import create_app
from api.authorization import Authorizer
from api.rate_limit import AllowAllRateLimiter, RateLimiter
from services.ingestion.service import IngestionService
from tests.unit.services.ingestion.fakes import InMemoryIngestionRepository, InMemoryObjectStore, SpyPdfSanitizer

PDF_BYTES = b"%PDF-1.7\n%...\n1 0 obj\n<< >>\nendobj\n%%EOF"


class _FixedTenantAuthorizer:
    def authorize(self, request: Request) -> str:
        return "t-nordvik"


class _DenyAllRateLimiter:
    def allow(self, tenant_id: str) -> bool:
        return False


def _client(*, rate_limiter: RateLimiter | None = None, authorizer: Authorizer | None = None) -> TestClient:
    service = IngestionService(InMemoryObjectStore(), InMemoryIngestionRepository(), SpyPdfSanitizer())
    app = create_app(
        service,
        authorizer=authorizer or _FixedTenantAuthorizer(),
        rate_limiter=rate_limiter or AllowAllRateLimiter(),
    )
    return TestClient(app)


def test_ingest_document_returns_202_with_document_and_job_ids() -> None:
    client = _client()

    response = client.post(
        "/ingest/documents",
        params={"intent": "extract"},
        headers={"X-Original-Filename": "invoice.pdf"},
        content=PDF_BYTES,
    )

    assert response.status_code == 202
    body = response.json()
    assert body["document_id"].startswith("doc_")
    assert body["job_id"].startswith("job_")
    assert body["replayed"] is False


def test_ingest_masquerading_exe_is_rejected_with_415() -> None:
    client = _client()

    response = client.post(
        "/ingest/documents",
        params={"intent": "extract"},
        headers={"X-Original-Filename": "invoice.pdf"},
        content=b"MZ\x90\x00 not really a pdf",
    )

    assert response.status_code == 415


def test_ingest_replay_returns_replayed_true() -> None:
    client = _client()

    first = client.post("/ingest/documents", params={"intent": "extract"}, content=PDF_BYTES)
    second = client.post("/ingest/documents", params={"intent": "extract"}, content=PDF_BYTES)

    assert first.json()["document_id"] == second.json()["document_id"]
    assert second.json()["replayed"] is True


def test_ingest_rate_limited_tenant_gets_429() -> None:
    client = _client(rate_limiter=_DenyAllRateLimiter())

    response = client.post("/ingest/documents", params={"intent": "extract"}, content=PDF_BYTES)

    assert response.status_code == 429


def test_ingest_without_tenant_header_via_default_authorizer_is_401() -> None:
    service = IngestionService(InMemoryObjectStore(), InMemoryIngestionRepository(), SpyPdfSanitizer())
    from api.authorization import HeaderTenantAuthorizer

    app = create_app(service, authorizer=HeaderTenantAuthorizer(), rate_limiter=AllowAllRateLimiter())
    client = TestClient(app)

    response = client.post("/ingest/documents", params={"intent": "extract"}, content=PDF_BYTES)

    assert response.status_code == 401
