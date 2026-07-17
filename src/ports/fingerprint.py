"""Fingerprint port: cheap, content-blind geometry extraction for candidate
routing (epic E04).

`FingerprintFeatureExtractor` implementations live in
`src/adapters/fingerprint/` and may depend on pypdf/geometry helpers only —
OCR, region classification, and VLM/model-provider calls are excluded BY
CONSTRUCTION: no field on `FingerprintFeatures` can carry text content, and
an architecture test
(tests/unit/adapters/fingerprint/test_architecture_no_provider_imports.py)
asserts the adapter package never imports a provider/OCR module.

Pure interface: no I/O here, no framework imports.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class FingerprintPage(BaseModel):
    """One page's quantized line geometry. `lines` holds quantized
    `(x0, y0, x1, y1)` bbox tuples only — never text, never font metadata."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    w_bucket: int
    h_bucket: int
    lines: tuple[tuple[int, int, int, int], ...] = Field(default_factory=tuple)


class FingerprintFeatures(BaseModel):
    """Canonical, content-blind geometry structure a fpv algorithm hashes
    into a routing key (`fpvN:sha256:<hex>`, computed by
    `adapters.fingerprint.fpv.fingerprint_key`). Structurally excludes text:
    no field here can carry it, by construction."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    fpv: int = Field(ge=1)
    page_count: int = Field(ge=1)
    pages: tuple[FingerprintPage, ...] = Field(min_length=1)


@runtime_checkable
class FingerprintFeatureExtractor(Protocol):
    def extract(self, pdf_bytes: bytes) -> FingerprintFeatures:
        """Extract geometry-only features from raw PDF bytes.

        Hostile-file safe: implementations enforce their own hard wall-clock
        timeout and never shell out with file-derived strings.
        """
        ...
