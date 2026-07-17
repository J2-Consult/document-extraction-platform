"""S3-compatible ObjectStore adapter (prod).

No `boto3` dependency is added (CLAUDE.md: no new dependency without
justification). Instead this module defines a minimal, boto3-shaped client
`Protocol` (`S3ClientLike`) — the same keyword-argument surface
(`Bucket=`, `Key=`, `Body=`) any boto3-compatible S3 client already exposes.
The real client is constructed and injected by the deployment (prod wiring is
out of scope for E03); tests inject an in-memory fake
(`tests/unit/adapters/objectstore/fakes.py`).

Encryption at rest: every `put_object` call passes `ServerSideEncryption`
(default `AES256`), matching CLAUDE.md's "encrypt at rest" requirement.

Existence is checked via `head_object` before a conditional put — this is a
best-effort `put_if_absent` (a TOCTOU window exists between the check and the
write; S3-compatible object stores without conditional-write support cannot
close it without a native "if-none-match" primitive). Because keys are
content-addressed, two racing writers for the same key write identical bytes,
so the window is harmless in practice; a future adapter revision can tighten
this to a conditional PUT (`IfNoneMatch: "*"`) once the injected client
surface guarantees it.
"""

from __future__ import annotations

import contextlib
from typing import Any, Protocol, runtime_checkable

from ports.objectstore import ObjectNotFoundError

DEFAULT_SERVER_SIDE_ENCRYPTION = "AES256"


class S3NotFoundError(Exception):
    """Raised by an `S3ClientLike` implementation when the key does not exist."""


@runtime_checkable
class S3ReadableBody(Protocol):
    def read(self) -> bytes: ...


# boto3's real S3 client keyword arguments are PascalCase (Bucket=, Key=, ...);
# this Protocol mirrors that surface verbatim so any boto3-compatible client
# satisfies it structurally, hence noqa: N803 (ruff's lowercase-argument rule)
# on every method below.
@runtime_checkable
class S3ClientLike(Protocol):
    """Minimal boto3-shaped S3 client surface this adapter depends on."""

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ServerSideEncryption: str) -> Any:  # noqa: N803
        ...

    def head_object(self, *, Bucket: str, Key: str) -> Any:  # noqa: N803
        """Raise S3NotFoundError if `Key` does not exist in `Bucket`."""
        ...

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, S3ReadableBody]:  # noqa: N803
        """Raise S3NotFoundError if `Key` does not exist; else a mapping with a
        'Body' entry exposing `.read() -> bytes`."""
        ...

    def delete_object(self, *, Bucket: str, Key: str) -> Any: ...  # noqa: N803


class S3CompatibleObjectStore:
    """Prod `ObjectStore`, backed by an injected `S3ClientLike`."""

    def __init__(
        self,
        client: S3ClientLike,
        bucket: str,
        *,
        server_side_encryption: str = DEFAULT_SERVER_SIDE_ENCRYPTION,
    ) -> None:
        self._client = client
        self._bucket = bucket
        self._sse = server_side_encryption

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
        except S3NotFoundError:
            return False
        return True

    def put_if_absent(self, key: str, data: bytes) -> bool:
        if self.exists(key):
            return False
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data, ServerSideEncryption=self._sse)
        return True

    def get(self, key: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except S3NotFoundError as exc:
            raise ObjectNotFoundError(key) from exc
        return response["Body"].read()

    def delete(self, key: str) -> None:
        with contextlib.suppress(S3NotFoundError):
            self._client.delete_object(Bucket=self._bucket, Key=key)
