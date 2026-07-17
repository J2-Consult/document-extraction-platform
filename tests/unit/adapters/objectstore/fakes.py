"""In-memory fake S3 client (`S3ClientLike`) for the objectstore contract suite.

Not shipped — a pure test double standing in for a real boto3-compatible
client so `S3CompatibleObjectStore` gets the same contract coverage as
`LocalFileSystemObjectStore` without a real S3-compatible service.
"""

from __future__ import annotations

import io
from typing import Any

from adapters.objectstore.s3 import S3NotFoundError, S3ReadableBody


class InMemoryS3Client:
    """PascalCase kwargs mirror boto3's real client — noqa: N803 throughout,
    same rationale as `S3ClientLike` in `adapters/objectstore/s3.py`."""

    def __init__(self) -> None:
        self._objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ServerSideEncryption: str) -> Any:  # noqa: N803
        assert ServerSideEncryption, "encryption at rest is mandatory"
        self._objects[(Bucket, Key)] = bytes(Body)
        return {}

    def head_object(self, *, Bucket: str, Key: str) -> Any:  # noqa: N803
        if (Bucket, Key) not in self._objects:
            raise S3NotFoundError(Key)
        return {}

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, S3ReadableBody]:  # noqa: N803
        try:
            data = self._objects[(Bucket, Key)]
        except KeyError as exc:
            raise S3NotFoundError(Key) from exc
        return {"Body": io.BytesIO(data)}

    def delete_object(self, *, Bucket: str, Key: str) -> Any:  # noqa: N803
        if (Bucket, Key) not in self._objects:
            raise S3NotFoundError(Key)
        del self._objects[(Bucket, Key)]
        return {}
