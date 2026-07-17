"""Domain implementation of the `CanonicalSerializer` port (src/ports/canonical.py).

Must stay byte-for-byte identical to `fixtures/fpv1.py`'s `canonical_json` —
that module is the fixture bundle's single source of truth for fingerprinting,
and this is the platform-side implementation both fingerprinting and content
hashing are meant to share (see specs/epics/E01-artifact-contracts.md).

Pure domain: no I/O, no framework imports.
"""

from __future__ import annotations

import json
from collections.abc import Mapping


class JsonCanonicalSerializer:
    """Sorted keys, compact separators, UTF-8, NaN/Infinity rejected."""

    def canonical_bytes(self, obj: Mapping[str, object]) -> bytes:
        return json.dumps(
            obj,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
