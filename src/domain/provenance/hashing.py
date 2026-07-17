"""Hash-integrity: prove a `Provenance.source.artifact_sha256` matches the
actual source PDF bytes. CLAUDE.md: "hashes make the audit trail
tamper-evident" — read paths that surface provenance externally call this
before trusting a citation.

Pure function: no I/O — the caller supplies bytes already read from storage.
"""

from __future__ import annotations

import hashlib

from domain.artifacts.provenance import Provenance


def verify_source_hash(provenance: Provenance, pdf_bytes: bytes) -> bool:
    return hashlib.sha256(pdf_bytes).hexdigest() == provenance.source.artifact_sha256
