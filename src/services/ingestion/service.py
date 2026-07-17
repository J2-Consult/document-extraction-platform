"""IngestionService (epic E03): the orchestration for one upload.

validate (magic bytes, size, PDF sanitization hook) -> sha256 -> deterministic
object key -> store -> register document + job + outbox row in one
transaction. All logic here is against ports (ObjectStore, IngestionRepository,
PdfSanitizer) — no FastAPI, no SQL — so it is unit-testable with in-memory
fakes (see `tests/unit/services/ingestion/`).

Security: only hashes, sizes, and ids are logged — never upload content
(CLAUDE.md).
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

from ports.ingestion_repo import IngestionRepository, UploadRegistration
from ports.objectstore import ObjectStore
from services.ingestion.identity import deterministic_object_key, idempotency_key, ingestion_identity
from services.ingestion.sanitizer import PdfSanitizer
from services.ingestion.validation import DEFAULT_MAX_UPLOAD_BYTES, detect_media_type, enforce_size_limit

logger = logging.getLogger(__name__)

JOB_KIND_PROCESS_DOCUMENT = "process_document"


@dataclass(frozen=True)
class IngestResult:
    document_id: str
    job_id: str
    source_sha256: str
    replayed: bool


class IngestionService:
    def __init__(
        self,
        object_store: ObjectStore,
        repository: IngestionRepository,
        sanitizer: PdfSanitizer,
        *,
        max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
    ) -> None:
        self._object_store = object_store
        self._repository = repository
        self._sanitizer = sanitizer
        self._max_upload_bytes = max_upload_bytes

    def ingest(self, *, tenant_id: str, intent: str, original_filename: str, data: bytes) -> IngestResult:
        enforce_size_limit(data, max_bytes=self._max_upload_bytes)
        media_type = detect_media_type(data)

        sanitized = self._sanitizer.sanitize(data) if media_type == "application/pdf" else data
        source_sha256 = hashlib.sha256(sanitized).hexdigest()
        object_key = deterministic_object_key(tenant_id, source_sha256)
        identity = ingestion_identity(tenant_id, source_sha256, intent)

        stored = self._object_store.put_if_absent(object_key, sanitized)
        logger.info(
            "ingestion object stored",
            extra={
                "tenant_id": tenant_id,
                "source_sha256": source_sha256,
                "size_bytes": len(sanitized),
                "stored": stored,
            },
        )

        registration = UploadRegistration(
            tenant_id=tenant_id,
            document_id=f"doc_{identity}",
            job_id=f"job_{identity}",
            outbox_id=f"outbox_{identity}",
            intent=intent,
            source_sha256=source_sha256,
            media_type=media_type,
            size_bytes=len(sanitized),
            original_filename=original_filename,
            object_key=object_key,
            job_kind=JOB_KIND_PROCESS_DOCUMENT,
            job_payload={
                "idempotency_key": idempotency_key(source_sha256, intent),
                "intent": intent,
                "object_key": object_key,
                "media_type": media_type,
            },
        )
        registered = self._repository.register_upload(registration)
        logger.info(
            "ingestion registered",
            extra={"tenant_id": tenant_id, "document_id": registered.document_id, "replayed": registered.replayed},
        )
        return IngestResult(
            document_id=registered.document_id,
            job_id=registered.job_id,
            source_sha256=source_sha256,
            replayed=registered.replayed,
        )
