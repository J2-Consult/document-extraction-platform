"""Canonicalization port: stable, deterministic JSON encoding.

Shared by fingerprinting (fpv1 and successors) and content hashing so that
"same structure -> same bytes" holds regardless of caller. Interface only —
see `src/domain/artifacts/canonical.py` for the implementation that reproduces
`fixtures/fpv1.py`'s `canonical_json` byte-for-byte.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable


@runtime_checkable
class CanonicalSerializer(Protocol):
    def canonical_bytes(self, obj: Mapping[str, object]) -> bytes:
        """Deterministic JSON encoding: sorted keys, compact separators, UTF-8, no NaN/Inf."""
        ...
