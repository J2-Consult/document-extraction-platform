"""POST /ingest/documents (epic E03).

Thin by design (CLAUDE.md): parse -> authorize placeholder hook -> call
`IngestionService` -> shape response. No business logic lives here — upload
validation, hashing, storage, and registration are all in
`services/ingestion/service.py` and testable without any FastAPI import.

Errors to the client are generic (CLAUDE.md: "Errors: generic to clients,
itemized server-side; never swallow exceptions") — the specific validation
failure is mapped to a stable HTTP status, but the response body never
echoes upload content, and unexpected failures are logged with detail
server-side and returned as an opaque 500.

Body encoding: the raw upload is the request body (`application/octet-stream`),
not a `multipart/form-data` field. CLAUDE.md forbids adding a new dependency
without justification, and FastAPI's `UploadFile`/`Form` require the optional
`python-multipart` package, which is not in this project's dependency set —
so `intent` travels as a query parameter and the filename as an optional
header instead of multipart fields.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict

from api.authorization import Authorizer, NotAuthorizedError
from api.rate_limit import RateLimiter
from services.ingestion.service import IngestionService
from services.ingestion.validation import UnsupportedMediaTypeError, UploadRejectedError, UploadTooLargeError

logger = logging.getLogger(__name__)

FILENAME_HEADER = "X-Original-Filename"


class IngestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    document_id: str
    job_id: str
    replayed: bool


def build_ingest_router(
    service: IngestionService,
    *,
    authorizer: Authorizer,
    rate_limiter: RateLimiter,
) -> APIRouter:
    """Constructor-injected route factory — no globals, no service locator."""
    router = APIRouter(prefix="/ingest", tags=["ingest"])

    @router.post("/documents", status_code=202, response_model=IngestResponse)
    async def ingest_document(
        request: Request,
        intent: str = Query(..., min_length=1),
    ) -> IngestResponse:
        try:
            tenant_id = authorizer.authorize(request)
        except NotAuthorizedError:
            raise HTTPException(status_code=401, detail="not authorized") from None

        if not rate_limiter.allow(tenant_id):
            raise HTTPException(status_code=429, detail="rate limit exceeded")

        data = await request.body()
        original_filename = request.headers.get(FILENAME_HEADER, "upload")
        try:
            result = service.ingest(
                tenant_id=tenant_id,
                intent=intent,
                original_filename=original_filename,
                data=data,
            )
        except UnsupportedMediaTypeError:
            raise HTTPException(status_code=415, detail="unsupported file type") from None
        except UploadTooLargeError:
            raise HTTPException(status_code=413, detail="file too large") from None
        except UploadRejectedError:
            raise HTTPException(status_code=400, detail="upload rejected") from None
        except Exception:
            logger.exception("ingestion failed", extra={"tenant_id": tenant_id})
            raise HTTPException(status_code=500, detail="ingestion failed") from None

        return IngestResponse(document_id=result.document_id, job_id=result.job_id, replayed=result.replayed)

    return router
