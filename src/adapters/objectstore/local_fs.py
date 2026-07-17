"""Local-filesystem ObjectStore adapter (dev/test).

Design constraints from the deployment environment this repo runs on:

- The data directory MUST live outside anything served as a web root — it is
  a plain configured path (`root`), never derived from request input.
- Writes are atomic: content is written to a sibling temp file in the same
  directory (same filesystem, so the final step is a same-fs rename/link —
  never partial writes visible to readers).
- `put_if_absent` genuinely means "create iff absent", not "overwrite" — the
  temp file is atomically **linked** to the destination name (`os.link`),
  which fails with `FileExistsError` if the destination already exists. That
  gives race-safe exclusive creation without a TOCTOU window between an
  `exists()` check and the write.
- Files are NEVER created read-only: the host filesystem (NFS) rejects
  read-only file creation outright, so this adapter relies on directory
  immutability (append-only object keys, no update path in the port) rather
  than file permissions for tamper-resistance.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from ports.objectstore import ObjectNotFoundError

_SAFE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-/]*$")


def _validate_key(key: str) -> None:
    if not key or not _SAFE_KEY.match(key) or ".." in key.split("/"):
        raise ValueError(f"unsafe object key: {key!r}")


class LocalFileSystemObjectStore:
    """Dev/test `ObjectStore`: one file per key under `root`."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, key: str) -> Path:
        _validate_key(key)
        path = (self._root / key).resolve()
        if self._root.resolve() not in path.parents and path != self._root.resolve():
            raise ValueError(f"object key escapes store root: {key!r}")
        return path

    def put_if_absent(self, key: str, data: bytes) -> bool:
        path = self._path_for(key)
        if path.exists():
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(tmp_name, path)  # atomic create-iff-absent
            except FileExistsError:
                return False  # a concurrent writer won the race (same content, by construction)
            return True
        finally:
            os.unlink(tmp_name)

    def get(self, key: str) -> bytes:
        path = self._path_for(key)
        try:
            return path.read_bytes()
        except FileNotFoundError as exc:
            raise ObjectNotFoundError(key) from exc

    def exists(self, key: str) -> bool:
        return self._path_for(key).exists()

    def delete(self, key: str) -> None:
        path = self._path_for(key)
        path.unlink(missing_ok=True)

    def list_all_keys(self) -> frozenset[str]:
        """Adapter-specific listing capability (not part of the `ObjectStore`
        port) used by out-of-band reconciliation sweeps to enumerate what is
        actually on disk."""
        root = self._root.resolve()
        return frozenset(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file())
