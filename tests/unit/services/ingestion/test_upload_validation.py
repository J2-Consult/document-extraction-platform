"""Magic-byte allow-listing and size-limit enforcement (epic E03)."""

from __future__ import annotations

import pytest

from services.ingestion.validation import (
    UnsupportedMediaTypeError,
    UploadTooLargeError,
    detect_media_type,
    enforce_size_limit,
)

PDF_BYTES = b"%PDF-1.7\n%...\n1 0 obj\n<< >>\nendobj\n%%EOF"
EXE_MASQUERADING_AS_PDF = b"MZ\x90\x00\x03\x00\x00\x00this is a windows executable, not a pdf"


def test_pdf_magic_bytes_are_recognized() -> None:
    assert detect_media_type(PDF_BYTES) == "application/pdf"


def test_exe_masquerading_as_pdf_is_rejected_by_magic_bytes() -> None:
    with pytest.raises(UnsupportedMediaTypeError):
        detect_media_type(EXE_MASQUERADING_AS_PDF)


def test_extension_and_content_type_are_irrelevant_only_bytes_matter() -> None:
    # No filename/content-type parameter exists on detect_media_type at all —
    # this test documents that the function's *signature* enforces the rule.
    with pytest.raises(UnsupportedMediaTypeError):
        detect_media_type(b"not a real pdf even though someone will call it invoice.pdf")


def test_empty_upload_is_rejected() -> None:
    with pytest.raises(UnsupportedMediaTypeError):
        detect_media_type(b"")


def test_within_size_limit_is_accepted() -> None:
    enforce_size_limit(b"x" * 100, max_bytes=1000)  # must not raise


def test_oversized_upload_is_rejected() -> None:
    with pytest.raises(UploadTooLargeError) as exc_info:
        enforce_size_limit(b"x" * 1001, max_bytes=1000)
    assert exc_info.value.size_bytes == 1001
    assert exc_info.value.max_bytes == 1000
