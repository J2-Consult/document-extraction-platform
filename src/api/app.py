"""Minimal FastAPI app factory (epic E03).

No `src/api/app.py` existed before this epic; disclosed in the E03 report as
a small addition needed to mount `ingest.py`'s router at all. Deliberately
thin: constructor injection only (CLAUDE.md — "dependencies passed
explicitly, no globals, no service locator"), no default/prod wiring here
(that needs real DB connections, secrets, and a connection-pool lifecycle
that is out of this epic's scope).
"""

from __future__ import annotations

from fastapi import FastAPI

from api.authorization import Authorizer
from api.rate_limit import RateLimiter
from api.routes.ingest import build_ingest_router
from services.ingestion.service import IngestionService


def create_app(
    ingestion_service: IngestionService,
    *,
    authorizer: Authorizer,
    rate_limiter: RateLimiter,
) -> FastAPI:
    app = FastAPI(title="Document Extraction Platform")
    app.include_router(build_ingest_router(ingestion_service, authorizer=authorizer, rate_limiter=rate_limiter))
    return app
