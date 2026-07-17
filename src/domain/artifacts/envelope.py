"""Generic artifact envelope shared by template, content, and decoder-mask artifacts.

Every versioned artifact is `{artifact_type, artifact_id, version, tenant_id,
created_at, body}`. The envelope never carries business meaning of its own —
that lives in `body`, and for contextual meaning specifically, in mask bodies.

Pure domain: no I/O, no framework imports.
"""

from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

BodyT = TypeVar("BodyT", bound=BaseModel)


class ArtifactEnvelope(BaseModel, Generic[BodyT]):
    """Envelope common to every versioned artifact kind.

    Concrete artifact modules narrow `artifact_type` to a single `Literal`
    value and bind `BodyT` to their body model (see `template.py`,
    `content.py`, `mask.py`).
    """

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    artifact_type: str
    artifact_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    tenant_id: str | None
    # `strict=False` here only: JSON has no native datetime literal, so a
    # timestamp always arrives as an ISO-8601 string. Every other field on
    # every model in this package keeps the class-level strict=True.
    created_at: datetime = Field(strict=False)
    body: BodyT
