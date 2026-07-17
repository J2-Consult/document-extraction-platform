"""Integration coverage for `PostgresIngestionRepository` (epic E03).

Connects as the restricted `api_service` role (never superuser) with tenant
context set via `tenant_transaction`, against the live Postgres started by
`docker-compose up -d`. Skips (per `tests/conftest.py`'s `skip_if_no_postgres`)
when no database is reachable.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import psycopg
import pytest

from adapters.postgres.ingestion_repo import PostgresIngestionRepository
from adapters.postgres.migrator import admin_conninfo, apply_migrations
from adapters.postgres.roles import ROLE_API_SERVICE, role_password
from ports.ingestion_repo import UploadRegistration
from tests.isolation.helpers import conninfo_for_role

pytestmark = pytest.mark.integration


@pytest.fixture
def tenant_id() -> str:
    # Fresh per test run: document/job ids are deterministic hashes of
    # (tenant_id, source_sha256, intent), so a fresh tenant namespace keeps
    # each test hermetic across repeated runs against a persistent database.
    return f"t-ingestion-{uuid4().hex[:8]}"


@pytest.fixture
def api_service_conn(skip_if_no_postgres: None) -> Iterator[psycopg.Connection[Any]]:
    apply_migrations(admin_conninfo())
    conninfo = conninfo_for_role(ROLE_API_SERVICE, role_password(ROLE_API_SERVICE))
    with psycopg.connect(conninfo) as conn:
        yield conn


def _registration(tenant_id: str, *, intent: str = "extract") -> UploadRegistration:
    return UploadRegistration(
        tenant_id=tenant_id,
        document_id=f"doc_{tenant_id}_{intent}",
        job_id=f"job_{tenant_id}_{intent}",
        outbox_id=f"outbox_{tenant_id}_{intent}",
        intent=intent,
        source_sha256="a" * 64,
        media_type="application/pdf",
        size_bytes=1234,
        original_filename="invoice.pdf",
        object_key=f"{tenant_id}/aa/bb/{'a' * 64}",
        job_kind="process_document",
        job_payload={"idempotency_key": f"{'a' * 64}:{intent}", "intent": intent},
    )


def test_register_upload_is_transactional_and_idempotent_against_live_postgres(
    api_service_conn: psycopg.Connection[Any], tenant_id: str
) -> None:
    repo = PostgresIngestionRepository(api_service_conn)
    registration = _registration(tenant_id)

    first = repo.register_upload(registration)
    second = repo.register_upload(registration)

    assert first.replayed is False
    assert second.replayed is True
    assert first.document_id == second.document_id == registration.document_id

    assert repo.registered_object_keys(tenant_id) == {registration.object_key}


def test_fetch_and_mark_pending_outbox_against_live_postgres(
    api_service_conn: psycopg.Connection[Any], tenant_id: str
) -> None:
    repo = PostgresIngestionRepository(api_service_conn)
    registration = _registration(tenant_id)
    repo.register_upload(registration)

    pending = repo.fetch_pending_outbox(tenant_id)
    assert len(pending) == 1
    assert pending[0].outbox_id == registration.outbox_id

    repo.mark_outbox_relayed(tenant_id, registration.outbox_id)

    assert repo.fetch_pending_outbox(tenant_id) == ()


def test_different_intent_yields_a_distinct_document_row(
    api_service_conn: psycopg.Connection[Any], tenant_id: str
) -> None:
    repo = PostgresIngestionRepository(api_service_conn)
    first = repo.register_upload(_registration(tenant_id, intent="extract"))
    second = repo.register_upload(_registration(tenant_id, intent="reprocess"))

    assert first.document_id != second.document_id
    assert first.replayed is False
    assert second.replayed is False
