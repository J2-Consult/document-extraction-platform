"""Postgres `IngestionRepository` adapter (epic E03).

Writes document + job + outbox row in one transaction via E02's
`tenant_transaction` (`adapters/postgres/session.py`) and E02's
`documents`/`jobs` tables plus the additive `ingestion_outbox` table
(migration 0003). Every statement is parameterized — no string-built SQL
(CLAUDE.md security rule). Replay-safety comes from `document_id`/`job_id`/
`outbox_id` being deterministic (see `services/ingestion/identity.py`):
inserts use `ON CONFLICT (<primary key>) DO NOTHING` against the tables'
existing primary keys, so a concurrent or repeated registration for the same
upload converges to one row instead of racing a check-then-insert in
application code.

Connects and writes as whatever role the injected `psycopg.Connection` was
opened with (expected: `api_service`, per E02's role grants) — this module
never elevates privilege and never bypasses RLS.
"""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.types.json import Json

from adapters.postgres.session import tenant_transaction
from ports.ingestion_repo import OutboxEntry, RegisteredUpload, UploadRegistration

_INSERT_DOCUMENT = """
INSERT INTO documents (tenant_id, document_id, version, source_sha256, state, body)
VALUES (%(tenant_id)s, %(document_id)s, 1, %(source_sha256)s, 'registered', %(body)s)
ON CONFLICT (tenant_id, document_id, version) DO NOTHING
"""

_INSERT_JOB = """
INSERT INTO jobs (tenant_id, job_id, document_id, kind, state, body)
VALUES (%(tenant_id)s, %(job_id)s, %(document_id)s, %(job_kind)s, 'queued', %(body)s)
ON CONFLICT (tenant_id, job_id) DO NOTHING
"""

_INSERT_OUTBOX = """
INSERT INTO ingestion_outbox (tenant_id, outbox_id, document_id, job_id, job_kind, idempotency_key, payload)
VALUES (%(tenant_id)s, %(outbox_id)s, %(document_id)s, %(job_id)s, %(job_kind)s, %(idempotency_key)s, %(payload)s)
ON CONFLICT (tenant_id, outbox_id) DO NOTHING
"""

_SELECT_OBJECT_KEYS = "SELECT body ->> 'object_key' FROM documents WHERE tenant_id = %s AND body ? 'object_key'"

_SELECT_PENDING_OUTBOX = """
SELECT outbox_id, tenant_id, job_kind, idempotency_key, payload
FROM ingestion_outbox
WHERE tenant_id = %s AND NOT relayed
ORDER BY created_at
LIMIT %s
"""

_MARK_RELAYED = "UPDATE ingestion_outbox SET relayed = true, relayed_at = now() WHERE tenant_id = %s AND outbox_id = %s"


class PostgresIngestionRepository:
    """`IngestionRepository` backed by a single, request-scoped `psycopg.Connection`."""

    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self._conn = conn

    def register_upload(self, registration: UploadRegistration) -> RegisteredUpload:
        document_body = Json(
            {
                "intent": registration.intent,
                "original_filename": registration.original_filename,
                "media_type": registration.media_type,
                "size_bytes": registration.size_bytes,
                "object_key": registration.object_key,
            }
        )
        with tenant_transaction(self._conn, registration.tenant_id) as conn:
            document_result = conn.execute(
                _INSERT_DOCUMENT,
                {
                    "tenant_id": registration.tenant_id,
                    "document_id": registration.document_id,
                    "source_sha256": registration.source_sha256,
                    "body": document_body,
                },
            )
            replayed = document_result.rowcount == 0
            conn.execute(
                _INSERT_JOB,
                {
                    "tenant_id": registration.tenant_id,
                    "job_id": registration.job_id,
                    "document_id": registration.document_id,
                    "job_kind": registration.job_kind,
                    "body": Json(registration.job_payload),
                },
            )
            conn.execute(
                _INSERT_OUTBOX,
                {
                    "tenant_id": registration.tenant_id,
                    "outbox_id": registration.outbox_id,
                    "document_id": registration.document_id,
                    "job_id": registration.job_id,
                    "job_kind": registration.job_kind,
                    "idempotency_key": registration.job_payload.get("idempotency_key", registration.outbox_id),
                    "payload": Json(registration.job_payload),
                },
            )
        return RegisteredUpload(
            document_id=registration.document_id,
            job_id=registration.job_id,
            outbox_id=registration.outbox_id,
            replayed=replayed,
        )

    def registered_object_keys(self, tenant_id: str) -> frozenset[str]:
        with tenant_transaction(self._conn, tenant_id) as conn:
            rows = conn.execute(_SELECT_OBJECT_KEYS, (tenant_id,)).fetchall()
        return frozenset(row[0] for row in rows if row[0] is not None)

    def fetch_pending_outbox(self, tenant_id: str, limit: int = 100) -> tuple[OutboxEntry, ...]:
        with tenant_transaction(self._conn, tenant_id) as conn:
            rows = conn.execute(_SELECT_PENDING_OUTBOX, (tenant_id, limit)).fetchall()
        return tuple(
            OutboxEntry(
                outbox_id=row[0],
                tenant_id=row[1],
                job_kind=row[2],
                idempotency_key=row[3],
                payload=dict(row[4]),
            )
            for row in rows
        )

    def mark_outbox_relayed(self, tenant_id: str, outbox_id: str) -> None:
        with tenant_transaction(self._conn, tenant_id) as conn:
            conn.execute(_MARK_RELAYED, (tenant_id, outbox_id))
