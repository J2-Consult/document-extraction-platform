"""Shared ObjectStore contract suite (epic E03).

Both adapters — `LocalFileSystemObjectStore` (dev/test) and
`S3CompatibleObjectStore` (prod, exercised here against an in-memory fake
client) — must satisfy the identical `ObjectStore` port contract (Liskov:
either is substitutable behind `IngestionService`). Parametrizing one suite
over both adapters is what proves that, rather than writing two suites that
could silently drift apart.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import pytest

from adapters.objectstore.local_fs import LocalFileSystemObjectStore
from adapters.objectstore.s3 import S3CompatibleObjectStore
from ports.objectstore import ObjectNotFoundError, ObjectStore
from tests.unit.adapters.objectstore.fakes import InMemoryS3Client


class ObjectStoreFactory(Protocol):
    def __call__(self) -> ObjectStore: ...


@pytest.fixture(params=["local_fs", "s3_fake"])
def object_store(request: pytest.FixtureRequest, tmp_path: Path) -> ObjectStore:
    if request.param == "local_fs":
        return LocalFileSystemObjectStore(root=tmp_path / "objects")
    return S3CompatibleObjectStore(client=InMemoryS3Client(), bucket="docext-test")


def test_put_if_absent_first_write_returns_true_and_is_retrievable(object_store: ObjectStore) -> None:
    assert object_store.put_if_absent("k1", b"hello") is True
    assert object_store.exists("k1") is True
    assert object_store.get("k1") == b"hello"


def test_put_if_absent_second_write_same_key_returns_false_and_keeps_original(object_store: ObjectStore) -> None:
    object_store.put_if_absent("k1", b"hello")
    assert object_store.put_if_absent("k1", b"different bytes") is False
    assert object_store.get("k1") == b"hello"


def test_get_missing_key_raises_object_not_found(object_store: ObjectStore) -> None:
    with pytest.raises(ObjectNotFoundError):
        object_store.get("does-not-exist")


def test_exists_false_for_missing_key(object_store: ObjectStore) -> None:
    assert object_store.exists("does-not-exist") is False


def test_delete_removes_object(object_store: ObjectStore) -> None:
    object_store.put_if_absent("k1", b"hello")
    object_store.delete("k1")
    assert object_store.exists("k1") is False


def test_delete_missing_key_is_idempotent_no_op(object_store: ObjectStore) -> None:
    object_store.delete("never-written")  # must not raise


def test_put_if_absent_after_delete_recreates_object(object_store: ObjectStore) -> None:
    object_store.put_if_absent("k1", b"hello")
    object_store.delete("k1")
    assert object_store.put_if_absent("k1", b"hello again") is True
    assert object_store.get("k1") == b"hello again"


def test_keys_are_namespaced_independently(object_store: ObjectStore) -> None:
    object_store.put_if_absent("a/b/c", b"one")
    object_store.put_if_absent("a/b/d", b"two")
    assert object_store.get("a/b/c") == b"one"
    assert object_store.get("a/b/d") == b"two"
