"""Deterministic identity derivation for ingestion (epic E03).

Idempotency key = (tenant_id, source hash, intent). Both the object-store key
and the document/job/outbox row ids are pure functions of that triple, so
replaying the same upload N times computes byte-identical keys/ids every
time — the persistence layer never needs a read-before-write to detect a
replay, it just lets `ON CONFLICT DO NOTHING` (or the object store's
`put_if_absent`) absorb duplicates.

Pure functions: no I/O, no framework imports.
"""

from __future__ import annotations

import hashlib


def ingestion_identity(tenant_id: str, source_sha256: str, intent: str) -> str:
    """A 32-hex-char id derived from `(tenant_id, source_sha256, intent)`."""
    digest = hashlib.sha256(f"{tenant_id}\n{source_sha256}\n{intent}".encode()).hexdigest()
    return digest[:32]


def idempotency_key(source_sha256: str, intent: str) -> str:
    """Human-legible idempotency key, e.g. for `JobQueue.enqueue`."""
    return f"{source_sha256}:{intent}"


def deterministic_object_key(tenant_id: str, source_sha256: str) -> str:
    """Tenant-scoped, hash-sharded object-store key for `source_sha256`."""
    return f"{tenant_id}/{source_sha256[0:2]}/{source_sha256[2:4]}/{source_sha256}"
