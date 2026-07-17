"""E09's narrow, disclosed addition to E01's Provenance shape (CLAUDE.md
PROVENANCE MODEL NOTE): a correction observation (`method == "human"`) must
carry who made it. `corrected_by` is additive and optional so every existing
fixture/provenance construction (method != "human") is unaffected.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from domain.artifacts.provenance import Provenance, SourceRef, WorkingRef


def _base_kwargs() -> dict[str, object]:
    return {
        "source": SourceRef(artifact_sha256="0" * 64, page=1),
        "working": WorkingRef(artifact_sha256="0" * 64, coordinate_space="page-1"),
        "bbox": [0, 0, 10, 10],
        "component_version": "fixture-1.0.0",
        "transform_to_source": [1, 0, 0, 1, 0, 0],
    }


def test_corrected_by_defaults_to_none_for_non_human_provenance() -> None:
    provenance = Provenance(method="pdf_text", **_base_kwargs())  # type: ignore[arg-type]
    assert provenance.corrected_by is None


def test_corrected_by_accepts_a_corrector_identity_on_human_method() -> None:
    provenance = Provenance(method="human", corrected_by="reviewer-1", **_base_kwargs())  # type: ignore[arg-type]
    assert provenance.corrected_by == "reviewer-1"


def test_corrected_by_rejects_empty_string() -> None:
    with pytest.raises(ValidationError):
        Provenance(method="human", corrected_by="", **_base_kwargs())  # type: ignore[arg-type]
