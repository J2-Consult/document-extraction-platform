"""Authorization placeholder hook (epic E03).

CLAUDE.md requires "every endpoint has an explicit authorization check";
real OAuth2/JWT verification at the API edge is cross-cutting infrastructure
well beyond this epic's scope (ingestion storage). This module gives the
route an explicit, testable seam for it: `Authorizer.authorize(request)`
returns the authenticated tenant id or raises `NotAuthorizedError`.

`HeaderTenantAuthorizer` is a PLACEHOLDER — it trusts an `X-Tenant-Id` header
verbatim. That is NOT authentication and must not be mistaken for it; it
exists only so the route has something real to call while the actual
OAuth2/JWT verifier is built (future work, disclosed in the E03 report).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from fastapi import Request

TENANT_HEADER = "X-Tenant-Id"


class NotAuthorizedError(Exception):
    """Raised when a request cannot be attributed to a tenant."""


@runtime_checkable
class Authorizer(Protocol):
    def authorize(self, request: Request) -> str:
        """Return the authenticated tenant id, or raise NotAuthorizedError."""
        ...


class HeaderTenantAuthorizer:
    """PLACEHOLDER ONLY — see module docstring. Not real authentication."""

    def authorize(self, request: Request) -> str:
        tenant_id = request.headers.get(TENANT_HEADER)
        if not tenant_id:
            raise NotAuthorizedError(f"missing {TENANT_HEADER} header")
        return tenant_id
