"""Least-privilege database roles for the platform (epic E02).

Four service roles, each mapped to one trust boundary:

- ``api_service``   — edge writes: full DML on operational tables, append-only
  insert on the versioned artifact tables.
- ``worker``        — background processing: read + progress writes, no deletes.
- ``orchestrator_readonly`` — retrieval/orchestration: SELECT only.
- ``synthesis``     — cross-tenant synthesis over shared knowledge ONLY. Row-level
  security restricts it to vendor templates (``tenant_id IS NULL``) and vendor
  masks (``scope = 'vendor'``); it can never read a customer-scope mask or a
  customer-private template, even with ``app.tenant_id`` set (architecture §7.4).

None of these roles is a superuser or carries ``BYPASSRLS``; that is the whole
point of the isolation suite (``tests/isolation/``), which connects AS these
roles and proves RLS holds at the SQL layer.

Passwords are read from the environment (``DOCEXT_ROLE_<ROLE>_PASSWORD``) with
dev-only defaults, mirroring the ``POSTGRES_*`` convention already used by the
harness. Defaults exist so local ``make test-isolation`` runs with zero setup;
real deployments set the env vars. Secrets are never logged.
"""

from __future__ import annotations

import os

ROLE_API_SERVICE = "api_service"
ROLE_WORKER = "worker"
ROLE_ORCHESTRATOR_READONLY = "orchestrator_readonly"
ROLE_SYNTHESIS = "synthesis"

ALL_ROLES: tuple[str, ...] = (
    ROLE_API_SERVICE,
    ROLE_WORKER,
    ROLE_ORCHESTRATOR_READONLY,
    ROLE_SYNTHESIS,
)

# Dev-only defaults; overridden per role via DOCEXT_ROLE_<ROLE>_PASSWORD.
_DEFAULT_PASSWORDS: dict[str, str] = {
    ROLE_API_SERVICE: "api_service_dev_password",
    ROLE_WORKER: "worker_dev_password",
    ROLE_ORCHESTRATOR_READONLY: "orchestrator_readonly_dev_password",
    ROLE_SYNTHESIS: "synthesis_dev_password",
}


def role_password(role: str) -> str:
    """Return the configured password for ``role`` (env override or dev default)."""
    if role not in _DEFAULT_PASSWORDS:
        raise KeyError(f"unknown role: {role!r}")
    env_key = f"DOCEXT_ROLE_{role.upper()}_PASSWORD"
    return os.environ.get(env_key, _DEFAULT_PASSWORDS[role])
