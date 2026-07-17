"""Unit tests for `NativePdfTemplateVerifier` against the real fixture
invoice (accepted), a moved-label decoy (rejected — see criterion 2), and an
unparseable file (inconclusive — never force-matched).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from adapters.fingerprint.born_digital import BornDigitalFingerprintExtractor
from adapters.fingerprint.verifier import NativePdfTemplateVerifier
from benchmarks.routing import decoys
from domain.artifacts.template import TemplateArtifact, TemplateBody
from ports.fingerprint import FingerprintFeatures, FingerprintPage


def _load_template_body(load_fixture_artifact: Callable[[str], dict[str, Any]]) -> TemplateBody:
    return TemplateArtifact.model_validate(load_fixture_artifact("tmpl_nvinv.v1")).body


def test_real_invoice_is_accepted(
    load_fixture_artifact: Callable[[str], dict[str, Any]], fixture_pdf_path: Callable[[str], Path]
) -> None:
    body = _load_template_body(load_fixture_artifact)
    pdf_bytes = fixture_pdf_path("nv_invoice_20260042").read_bytes()
    features = BornDigitalFingerprintExtractor().extract(pdf_bytes)

    result = NativePdfTemplateVerifier().verify(features, pdf_bytes, body)

    assert result.status == "accepted"
    assert all(check.passed is True for check in result.checks)
    check_ids = {check.check_id for check in result.checks}
    assert {"page_geometry", "label_anchors", "major_regions", "table_boundaries"} <= check_ids


def test_decoy_with_rotated_labels_is_rejected_on_label_anchors(
    load_fixture_artifact: Callable[[str], dict[str, Any]],
) -> None:
    body = _load_template_body(load_fixture_artifact)
    pdf_bytes = decoys.render_decoy_invoice_pdf(decoys.generate_pdfs.NV_20260042, rotate_by=1)
    features = BornDigitalFingerprintExtractor().extract(pdf_bytes)

    result = NativePdfTemplateVerifier().verify(features, pdf_bytes, body)

    assert result.status == "rejected"
    by_id = {check.check_id: check for check in result.checks}
    assert by_id["label_anchors"].passed is False
    # page geometry is untouched by the decoy generator, by construction.
    assert by_id["page_geometry"].passed is True


def test_unparseable_pdf_bytes_is_inconclusive_never_accepted_or_silently_rejected(
    load_fixture_artifact: Callable[[str], dict[str, Any]],
) -> None:
    body = _load_template_body(load_fixture_artifact)
    fake_features = FingerprintFeatures(fpv=1, page_count=1, pages=(FingerprintPage(w_bucket=596, h_bucket=840),))

    result = NativePdfTemplateVerifier().verify(fake_features, b"not a pdf at all", body)

    assert result.status == "inconclusive"
    assert any(check.passed is None for check in result.checks)
