"""Model-provider port (epic E05): regional calls only, responses untrusted.

`ModelProvider` is the raw transport to an external model. Its payload is a
page image + ONE region + an opaque `job_ref` — never tenant identifiers,
never whole documents. What comes back is UNTRUSTED DATA: a raw mapping the
caller must validate into `ProviderResponse` (`extra="forbid"`, bounded
confidence, non-negative cost) before using — `adapters.providers.guarded.
GuardedProvider` is the wrapper that does this, adding timeout, circuit
breaker, rate limit, and per-tenant cost caps, and exposes the validated
surface (`ValidatedModelProvider`).

Pure interfaces: no I/O here, no framework imports beyond the domain
vocabulary and Pydantic for the response schema.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from domain.extraction import PageImage, Region


class ProviderResponse(BaseModel):
    """Schema a raw provider payload must validate against before use.
    `text` may be null (the model could not read the region)."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    text: str | None
    raw_confidence: float = Field(ge=0, le=1)
    cost: float = Field(ge=0)
    model_version: str = Field(min_length=1)


@runtime_checkable
class ModelProvider(Protocol):
    """Raw transport to one external model. Returns an UNVALIDATED payload."""

    def read_region(self, image: PageImage, region: Region, job_ref: str) -> Mapping[str, object]: ...


@runtime_checkable
class ValidatedModelProvider(Protocol):
    """The guarded surface passes consume: same regional-only signature, but
    the response has already been schema-validated."""

    def read_region(self, image: PageImage, region: Region, job_ref: str) -> ProviderResponse: ...


class ProviderError(RuntimeError):
    """Base for all provider-call failures."""


class ProviderCallError(ProviderError):
    """The underlying provider call raised."""


class ProviderTimeoutError(ProviderError):
    """The provider call exceeded its wall-clock budget."""


class InvalidProviderResponseError(ProviderError):
    """The provider's payload failed `ProviderResponse` schema validation."""


class CircuitOpenError(ProviderError):
    """The circuit breaker is open — the call was refused without reaching
    the provider."""


class RateLimitExceededError(ProviderError):
    """The client-side rate limit refused the call before it was made."""
