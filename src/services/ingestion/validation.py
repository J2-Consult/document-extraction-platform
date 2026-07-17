"""Upload validation: allow-listed types by magic bytes, size limit (epic E03).

Security: uploads are hostile (CLAUDE.md). File type is decided ONLY by
inspecting the leading bytes of the content — never by filename extension or
a client-supplied `Content-Type`, both of which are attacker-controlled. A
masquerading executable renamed to `.pdf` fails here regardless of its name.

Open/closed: a new allow-listed type is a new `MagicByteSignature` entry in
`ALLOWED_MEDIA_TYPES` — never an edit to `detect_media_type`.
"""

from __future__ import annotations

from dataclasses import dataclass


class UploadRejectedError(Exception):
    """Base class for upload validation failures. Message never quotes upload content."""


class UnsupportedMediaTypeError(UploadRejectedError):
    def __init__(self) -> None:
        super().__init__("unsupported or unrecognized file type")


class UploadTooLargeError(UploadRejectedError):
    def __init__(self, size_bytes: int, max_bytes: int) -> None:
        super().__init__(f"upload of {size_bytes} bytes exceeds the {max_bytes}-byte limit")
        self.size_bytes = size_bytes
        self.max_bytes = max_bytes


@dataclass(frozen=True)
class MagicByteSignature:
    media_type: str
    header: bytes

    def matches(self, data: bytes) -> bool:
        return data.startswith(self.header)


# Allow-list: extend by adding a signature, never by editing detect_media_type.
ALLOWED_MEDIA_TYPES: tuple[MagicByteSignature, ...] = (MagicByteSignature("application/pdf", b"%PDF-"),)

DEFAULT_MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MiB


def detect_media_type(data: bytes) -> str:
    """Return the allow-listed media type whose magic bytes match `data`.

    Raises UnsupportedMediaTypeError if no allow-listed signature matches —
    this is the sole gate against masquerading uploads (e.g. an executable
    renamed to `something.pdf`).
    """
    for signature in ALLOWED_MEDIA_TYPES:
        if signature.matches(data):
            return signature.media_type
    raise UnsupportedMediaTypeError


def enforce_size_limit(data: bytes, *, max_bytes: int = DEFAULT_MAX_UPLOAD_BYTES) -> None:
    if len(data) > max_bytes:
        raise UploadTooLargeError(len(data), max_bytes)
