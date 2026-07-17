"""Review corrections (E09): a human correction is a NEW observation with
provenance method='human' + corrector identity, appended (never mutated in
place), that re-enters mapping and completes. Authenticated + audited: the
actor is recorded on both the provenance and the audit record.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from domain.artifacts.content import Confidence, ContentArtifact, ContentBody
from domain.artifacts.mask import DecoderMaskArtifact, DecoderMaskBody
from domain.artifacts.template import TemplateArtifact, TemplateBody
from domain.registry import default_registry
from services.mapping.pipeline import MappingPipeline, MappingRequest, build_default_pipeline
from services.review.corrections import (
    CorrectionService,
    Corrector,
    UnknownReviewElementError,
)
from tests.unit.fakes.clock import FakeClock

ARTIFACTS_DIR = Path(__file__).resolve().parents[4] / "fixtures" / "artifacts"

SMUDGED_CONFIDENCE = 0.61


def _load(name: str) -> dict[str, Any]:
    return dict(json.loads((ARTIFACTS_DIR / f"{name}.json").read_text(encoding="utf-8")))


def _template() -> TemplateBody:
    return TemplateArtifact.model_validate(_load("tmpl_nvinv.v1")).body


def _vendor_mask() -> DecoderMaskBody:
    return DecoderMaskArtifact.model_validate(_load("mask_nvvendor.v1")).body


def _smudged_content() -> ContentBody:
    content = ContentArtifact.model_validate(_load("content_nv20260043.v1")).body
    smudge = Confidence(raw=SMUDGED_CONFIDENCE, calibrated=SMUDGED_CONFIDENCE)
    observations = [
        observation.model_copy(update={"confidence": smudge})
        if observation.element_id == "el_total_amount"
        else observation
        for observation in content.observations
    ]
    return content.model_copy(update={"observations": observations})


def _pipeline() -> MappingPipeline:
    return build_default_pipeline(registry=default_registry())


def _request(content: ContentBody) -> MappingRequest:
    return MappingRequest(content=content, mask=_vendor_mask(), template=_template(), target_schema_version=1)


def _pending_review_item() -> Any:
    result = _pipeline().run(_request(_smudged_content()))
    assert result.outcome == "pending_review"
    return result.review_items[0]


def test_correction_re_enters_mapping_and_completes_with_the_corrected_value() -> None:
    service = CorrectionService(_pipeline(), FakeClock(start=1_700.0))

    correction = service.apply_correction(
        review_item=_pending_review_item(),
        corrected_value="13750.00",
        corrector=Corrector(actor="reviewer-1"),
        request=_request(_smudged_content()),
    )

    assert correction.result.outcome == "completed"
    assert correction.result.contract_validation == "passed"
    assert correction.result.record is not None
    assert correction.result.record["total_amount"] == 13750.0
    assert correction.result.review_items == ()


def test_correction_observation_carries_human_method_and_corrector_identity() -> None:
    service = CorrectionService(_pipeline(), FakeClock())
    original = next(
        observation for observation in _smudged_content().observations if observation.element_id == "el_total_amount"
    )

    correction = service.apply_correction(
        review_item=_pending_review_item(),
        corrected_value="13750.00",
        corrector=Corrector(actor="reviewer-1"),
        request=_request(_smudged_content()),
    )

    observation = correction.observation
    assert observation.element_id == "el_total_amount"
    assert observation.value == "13750.00"
    assert observation.state == "present"
    assert observation.provenance.method == "human"
    assert observation.provenance.corrected_by == "reviewer-1"
    # The correction still points at WHERE the smudged value was read.
    assert observation.provenance.source == original.provenance.source
    assert observation.provenance.working == original.provenance.working
    assert observation.provenance.bbox == original.provenance.bbox


def test_correction_appends_a_new_content_version_never_mutating_the_input() -> None:
    service = CorrectionService(_pipeline(), FakeClock())
    smudged = _smudged_content()

    correction = service.apply_correction(
        review_item=_pending_review_item(),
        corrected_value="13750.00",
        corrector=Corrector(actor="reviewer-1"),
        request=_request(smudged),
    )

    assert correction.content.version == smudged.version + 1
    corrected = next(
        observation for observation in correction.content.observations if observation.element_id == "el_total_amount"
    )
    assert corrected.provenance.method == "human"
    # The input body is untouched — versioned artifacts are appended, not mutated.
    untouched = next(observation for observation in smudged.observations if observation.element_id == "el_total_amount")
    assert untouched.provenance.method == "pdf_text"
    assert untouched.value == "13750.00"


def test_correction_is_audited_with_actor_and_clock_timestamp() -> None:
    service = CorrectionService(_pipeline(), FakeClock(start=42.0))

    correction = service.apply_correction(
        review_item=_pending_review_item(),
        corrected_value="13750.00",
        corrector=Corrector(actor="reviewer-1"),
        request=_request(_smudged_content()),
    )

    audit = correction.audit
    assert audit.actor == "reviewer-1"
    assert audit.element_id == "el_total_amount"
    assert audit.document_id == "doc_nv20260043"
    assert audit.content_id == "content_nv20260043"
    assert audit.content_version == 2
    assert audit.at == 42.0


def test_unauthenticated_corrector_is_rejected() -> None:
    with pytest.raises(ValueError):
        Corrector(actor="")


def test_correction_for_an_element_the_content_never_observed_is_rejected() -> None:
    service = CorrectionService(_pipeline(), FakeClock())
    ghost_item = _pending_review_item().model_copy(update={"element": "el_ghost"})

    with pytest.raises(UnknownReviewElementError):
        service.apply_correction(
            review_item=ghost_item,
            corrected_value="13750.00",
            corrector=Corrector(actor="reviewer-1"),
            request=_request(_smudged_content()),
        )
