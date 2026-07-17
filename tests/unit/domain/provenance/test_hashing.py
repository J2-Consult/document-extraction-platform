"""`domain.provenance.hashing.verify_source_hash` against real fixture PDFs."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from domain.artifacts.content import ContentArtifact
from domain.provenance.hashing import verify_source_hash


def _first_observation_provenance(load_fixture_artifact: Callable[[str], dict[str, Any]]) -> Any:
    content = ContentArtifact.model_validate(load_fixture_artifact("content_nv20260042.v1"))
    return content.body.observations[0].provenance


def test_verify_source_hash_is_true_for_the_matching_pdf(
    load_fixture_artifact: Callable[[str], dict[str, Any]],
    fixture_pdf_path: Callable[[str], Path],
) -> None:
    provenance = _first_observation_provenance(load_fixture_artifact)
    pdf_bytes = fixture_pdf_path("nv_invoice_20260042").read_bytes()

    assert verify_source_hash(provenance, pdf_bytes) is True


def test_verify_source_hash_is_false_for_tampered_bytes(
    load_fixture_artifact: Callable[[str], dict[str, Any]],
    fixture_pdf_path: Callable[[str], Path],
) -> None:
    provenance = _first_observation_provenance(load_fixture_artifact)
    pdf_bytes = fixture_pdf_path("nv_invoice_20260042").read_bytes()

    assert verify_source_hash(provenance, pdf_bytes + b"\x00") is False


def test_verify_source_hash_is_false_for_a_different_fixture_pdf(
    load_fixture_artifact: Callable[[str], dict[str, Any]],
    fixture_pdf_path: Callable[[str], Path],
) -> None:
    provenance = _first_observation_provenance(load_fixture_artifact)
    other_pdf_bytes = fixture_pdf_path("nv_invoice_20260043").read_bytes()

    assert verify_source_hash(provenance, other_pdf_bytes) is False
