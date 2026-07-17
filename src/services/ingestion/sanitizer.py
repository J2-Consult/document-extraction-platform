"""PdfSanitizer hook (epic E03): strip active content from uploaded PDFs.

A port-shaped hook, not a full port module, because it is narrow and
ingestion-specific (unlike ObjectStore/JobQueue/Clock, nothing else in the
platform depends on it). `PassThroughPdfSanitizer` is the only implementation
shipped with this epic — real sanitization (stripping JavaScript, embedded
files, launch actions, ...) is explicitly future work; the hook exists so the
ingestion pipeline already calls it on every PDF and swapping in a real
implementation later touches one constructor argument, not the service.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class PdfSanitizer(Protocol):
    def sanitize(self, data: bytes) -> bytes:
        """Return sanitized PDF bytes. Must be safe to call on any allow-listed
        PDF upload, including hostile ones."""
        ...


class PassThroughPdfSanitizer:
    """No-op sanitizer: returns `data` unchanged. Real sanitization is future work."""

    def sanitize(self, data: bytes) -> bytes:
        return data
