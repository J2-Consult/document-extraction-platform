"""Adapter-specific coverage for `LocalFileSystemObjectStore` beyond the shared
`ObjectStore` contract: path-traversal rejection, atomic-write behavior, and
the `list_all_keys` reconciliation helper (not part of the `ObjectStore`
port — see `services/ingestion/reconciliation.py`)."""

from __future__ import annotations

from pathlib import Path

import pytest

from adapters.objectstore.local_fs import LocalFileSystemObjectStore


@pytest.mark.parametrize("bad_key", ["../escape", "a/../../escape", "/absolute", "", "a b"])
def test_unsafe_keys_are_rejected(tmp_path: Path, bad_key: str) -> None:
    store = LocalFileSystemObjectStore(root=tmp_path / "objects")
    with pytest.raises(ValueError):
        store.put_if_absent(bad_key, b"x")


def test_no_files_are_ever_created_read_only(tmp_path: Path) -> None:
    store = LocalFileSystemObjectStore(root=tmp_path / "objects")
    store.put_if_absent("t-nordvik/ab/cd/abcd", b"hello")
    written = next(p for p in (tmp_path / "objects").rglob("*") if p.is_file())
    assert written.stat().st_mode & 0o200, "file must remain owner-writable (NFS rejects read-only creates)"


def test_no_leftover_temp_files_after_write(tmp_path: Path) -> None:
    store = LocalFileSystemObjectStore(root=tmp_path / "objects")
    store.put_if_absent("k1", b"hello")
    store.put_if_absent("k1", b"hello")  # second call hits the already-exists fast path
    leftovers = list((tmp_path / "objects").rglob(".tmp-*"))
    assert leftovers == []


def test_list_all_keys_reflects_stored_objects(tmp_path: Path) -> None:
    store = LocalFileSystemObjectStore(root=tmp_path / "objects")
    store.put_if_absent("a/1", b"one")
    store.put_if_absent("a/2", b"two")
    assert store.list_all_keys() == frozenset({"a/1", "a/2"})
