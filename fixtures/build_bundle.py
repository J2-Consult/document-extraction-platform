#!/usr/bin/env python3
"""Regenerate the fixture PDFs and stamp real hashes/sizes/fingerprints into the
JSON artifacts that reference them.

Stdlib only. Idempotent by construction: PDF generation is deterministic
(`generate_pdfs.py`), so the sha256/size/fingerprint values recomputed on any
run are always the same real values; running this script twice in a row is a
byte-identical no-op (`git status` shows nothing after the second run).

What gets stamped:
  - tmpl_nvinv.v1.json / tmpl_mbr.v1.json: body.fingerprint (fpv1, computed
    from the actual rendered PDF geometry - never hand-written).
  - doc_*.json: source.sha256, source.size_bytes.
  - content_*.v1.json: body.source.sha256, and every observation's /
    unmapped_content entry's provenance.source.artifact_sha256 and
    provenance.working.artifact_sha256.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

FIXTURES_DIR = Path(__file__).resolve().parent
PDFS_DIR = FIXTURES_DIR / "pdfs"
ARTIFACTS_DIR = FIXTURES_DIR / "artifacts"

sys.path.insert(0, str(FIXTURES_DIR))
sys.path.insert(0, str(PDFS_DIR))

import fpv1  # noqa: E402
import generate_pdfs  # noqa: E402


def _sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _dump(path: Path, data: dict[str, Any]) -> None:
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return
    path.write_text(text, encoding="utf-8")


def _invoice_fingerprint(data: generate_pdfs.InvoiceData) -> str:
    """fpv1 fingerprint computed from an invoice's actual drawn text geometry."""
    lines = [fpv1.line_bbox(op.x, op.y, op.text, op.font_size) for op in generate_pdfs.invoice_text_ops(data)]
    features = fpv1.build_features(
        page_count=1,
        pages=[{"width": generate_pdfs.PAGE_WIDTH, "height": generate_pdfs.PAGE_HEIGHT, "lines": lines}],
    )
    return fpv1.fingerprint(features)


def _mbr_fingerprint() -> str:
    pages = []
    for page in (1, 2):
        lines = [fpv1.line_bbox(op.x, op.y, op.text, op.font_size) for op in generate_pdfs.mbr_text_ops(page)]
        pages.append({"width": generate_pdfs.PAGE_WIDTH, "height": generate_pdfs.PAGE_HEIGHT, "lines": lines})
    features = fpv1.build_features(page_count=2, pages=pages)
    return fpv1.fingerprint(features)


def _stamp_provenance_sha256(node: Any, sha256: str) -> None:
    """Recursively rewrite every provenance source/working artifact_sha256 in place."""
    if isinstance(node, dict):
        if "artifact_sha256" in node:
            node["artifact_sha256"] = sha256
        for value in node.values():
            _stamp_provenance_sha256(value, sha256)
    elif isinstance(node, list):
        for item in node:
            _stamp_provenance_sha256(item, sha256)


def stamp_template_fingerprint(path: Path, fingerprint: str) -> None:
    data = _load(path)
    data["body"]["fingerprint"] = fingerprint
    _dump(path, data)


def stamp_document(path: Path, sha256: str, size_bytes: int) -> None:
    data = _load(path)
    data["source"]["sha256"] = sha256
    data["source"]["size_bytes"] = size_bytes
    _dump(path, data)


def stamp_content(path: Path, sha256: str) -> None:
    data = _load(path)
    data["body"]["source"]["sha256"] = sha256
    _stamp_provenance_sha256(data["body"]["observations"], sha256)
    _stamp_provenance_sha256(data["body"]["unmapped_content"], sha256)
    _dump(path, data)


def main() -> None:
    generate_pdfs.generate_all(PDFS_DIR)

    sha_0042 = _sha256_of(PDFS_DIR / "nv_invoice_20260042.pdf")
    sha_0043 = _sha256_of(PDFS_DIR / "nv_invoice_20260043.pdf")
    sha_mbr = _sha256_of(PDFS_DIR / "mbr_report_001.pdf")

    size_0042 = (PDFS_DIR / "nv_invoice_20260042.pdf").stat().st_size
    size_0043 = (PDFS_DIR / "nv_invoice_20260043.pdf").stat().st_size
    size_mbr = (PDFS_DIR / "mbr_report_001.pdf").stat().st_size

    stamp_template_fingerprint(ARTIFACTS_DIR / "tmpl_nvinv.v1.json", _invoice_fingerprint(generate_pdfs.NV_20260042))
    stamp_template_fingerprint(ARTIFACTS_DIR / "tmpl_mbr.v1.json", _mbr_fingerprint())

    stamp_document(ARTIFACTS_DIR / "doc_nv20260042.json", sha_0042, size_0042)
    stamp_document(ARTIFACTS_DIR / "doc_nv20260043.json", sha_0043, size_0043)
    stamp_document(ARTIFACTS_DIR / "doc_mbr001.json", sha_mbr, size_mbr)

    stamp_content(ARTIFACTS_DIR / "content_nv20260042.v1.json", sha_0042)
    stamp_content(ARTIFACTS_DIR / "content_nv20260043.v1.json", sha_0043)
    stamp_content(ARTIFACTS_DIR / "content_mbr001.v1.json", sha_mbr)

    print("build_bundle: PDFs regenerated; sha256/size/fingerprint fields stamped.")


if __name__ == "__main__":
    main()
