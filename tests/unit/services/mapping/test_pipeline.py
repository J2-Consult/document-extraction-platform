"""MappingPipeline (E09): outcome semantics tested EXACTLY per the design doc.

Corpus: the real fixture artifacts (vendor mask + invoice content); the
smudged-total case derives in-test by lowering one confidence on the
all-confident content_nv20260043 — no synthetic artifacts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from domain.artifacts.content import Confidence, ContentArtifact, ContentBody
from domain.artifacts.mask import DecoderMaskArtifact, DecoderMaskBody
from domain.artifacts.template import TemplateArtifact, TemplateBody, TemplateRef
from domain.registry import default_registry
from services.mapping.constants import DEFAULT_CONFIDENCE_THRESHOLD
from services.mapping.outcome import (
    BusinessRuleViolation,
    MappingResult,
    RulesetVerdict,
    apply_ruleset_verdict,
)
from services.mapping.pipeline import MappingRequest, build_default_pipeline

ARTIFACTS_DIR = Path(__file__).resolve().parents[4] / "fixtures" / "artifacts"

SMUDGED_CONFIDENCE = 0.61  # the corpus's canonical smudged total (criterion 7)


def _load(name: str) -> dict[str, Any]:
    return dict(json.loads((ARTIFACTS_DIR / f"{name}.json").read_text(encoding="utf-8")))


def _content() -> ContentBody:
    return ContentArtifact.model_validate(_load("content_nv20260043.v1")).body


def _vendor_mask() -> DecoderMaskBody:
    return DecoderMaskArtifact.model_validate(_load("mask_nvvendor.v1")).body


def _template() -> TemplateBody:
    return TemplateArtifact.model_validate(_load("tmpl_nvinv.v1")).body


def _with_observation(content: ContentBody, element_id: str, **updates: object) -> ContentBody:
    observations = [
        observation.model_copy(update=updates) if observation.element_id == element_id else observation
        for observation in content.observations
    ]
    return content.model_copy(update={"observations": observations})


def _smudged(content: ContentBody, element_id: str) -> ContentBody:
    smudge = Confidence(raw=SMUDGED_CONFIDENCE, calibrated=SMUDGED_CONFIDENCE)
    return _with_observation(content, element_id, confidence=smudge)


def _request(
    content: ContentBody | None = None,
    mask: DecoderMaskBody | None = None,
    *,
    target_schema_version: int = 1,
) -> MappingRequest:
    return MappingRequest(
        content=content if content is not None else _content(),
        mask=mask if mask is not None else _vendor_mask(),
        template=_template(),
        target_schema_version=target_schema_version,
    )


def _pipeline() -> Any:
    return build_default_pipeline(registry=default_registry(), confidence_threshold=DEFAULT_CONFIDENCE_THRESHOLD)


# -- completed: clean invoice through the vendor mask ------------------------


def test_clean_invoice_maps_to_completed_record_that_validates() -> None:
    result = _pipeline().run(_request())

    assert result.outcome == "completed"
    assert result.contract_validation == "passed"
    assert result.error_category is None
    assert result.review_items == ()
    assert result.record is not None
    assert result.record["invoice_number"] == "2026-0043"
    assert result.record["invoice_date"] == "2026-02-20"
    assert result.record["due_date"] == "2026-03-22"
    assert result.record["currency"] == "NOK"
    assert result.record["payment_terms"] == "Net 30 days"
    assert result.record["total_amount"] == 13750.0
    assert result.record["vat_amount"] == 3125.0
    # notes is confidently blank (state=empty) and the schema permits absence.
    assert "notes" not in result.record


def test_enum_map_translates_ticked_yes_to_boolean_true() -> None:
    result = _pipeline().run(_request())

    assert result.record is not None
    assert result.record["approved"] is True


def test_table_element_coerces_into_line_item_array_per_template_columns() -> None:
    result = _pipeline().run(_request())

    assert result.record is not None
    assert result.record["line_items"] == [
        {"description": "Widget A", "qty": 2.0, "unit_price": 100.0, "amount": 200.0},
        {"description": "Widget B", "qty": 5.0, "unit_price": 120.0, "amount": 600.0},
    ]


# -- pending_review: required below threshold => NO partial records ----------


def test_required_low_confidence_value_yields_pending_review_and_null_record() -> None:
    result = _pipeline().run(_request(content=_smudged(_content(), "el_total_amount")))

    assert result.outcome == "pending_review"
    assert result.record is None, "NO partial records, ever"
    assert result.contract_validation == "not_evaluated"
    assert result.error_category == "extraction_uncertainty"

    assert len(result.review_items) == 1
    item = result.review_items[0]
    assert item.element == "el_total_amount"
    assert item.reason == "below_confidence_threshold"
    assert item.confidence == SMUDGED_CONFIDENCE
    assert item.provenance is not None
    smudged_observation = next(
        observation for observation in _content().observations if observation.element_id == "el_total_amount"
    )
    assert item.provenance == smudged_observation.provenance


# -- optional low-confidence: excluded only when the schema permits absence --


def test_optional_low_confidence_value_is_excluded_and_reported_but_record_proceeds() -> None:
    # el_notes maps to `notes`, which invoice_record_v1 does not require.
    content = _with_observation(
        _content(),
        "el_notes",
        value="smudged marginal note",
        state="present",
        confidence=Confidence(raw=SMUDGED_CONFIDENCE, calibrated=SMUDGED_CONFIDENCE),
    )

    result = _pipeline().run(_request(content=content))

    assert result.outcome == "completed"
    assert result.contract_validation == "passed"
    assert result.record is not None
    assert "notes" not in result.record, "excluded because the target schema permits absence"
    assert [item.element for item in result.review_items] == ["el_notes"]
    assert result.review_items[0].reason == "below_confidence_threshold"


# -- pending_template_review: mask/content template disagreement -------------


def test_mask_for_a_different_template_version_yields_pending_template_review() -> None:
    mask = _vendor_mask()
    mask = mask.model_copy(update={"template_ref": TemplateRef(template_id="tmpl_nvinv", version=2)})

    result = _pipeline().run(_request(mask=mask))

    assert result.outcome == "pending_template_review"
    assert result.record is None
    assert result.contract_validation == "not_evaluated"


# -- statelessness: same inputs twice => byte-identical result JSON ----------


def test_same_inputs_twice_yield_byte_identical_mapping_result_json() -> None:
    smudged = _smudged(_content(), "el_total_amount")

    first = _pipeline().run(_request(content=smudged)).model_dump_json()
    second = _pipeline().run(_request(content=smudged)).model_dump_json()

    assert first == second
    clean_first = _pipeline().run(_request()).model_dump_json()
    clean_second = _pipeline().run(_request()).model_dump_json()
    assert clean_first == clean_second


# -- the four error categories, distinct on four crafted inputs --------------


def test_four_error_categories_are_distinct_on_four_crafted_inputs() -> None:
    pipeline = _pipeline()

    # 1. extraction_uncertainty: the smudged required total.
    uncertain = pipeline.run(_request(content=_smudged(_content(), "el_total_amount")))
    assert uncertain.outcome == "pending_review"
    assert uncertain.error_category == "extraction_uncertainty"

    # 2. contract: a confidently-read value that violates its target datatype.
    unparseable = _with_observation(_content(), "el_total_amount", value="thirteen thousand")
    contract = pipeline.run(_request(content=unparseable))
    assert contract.outcome == "rejected"
    assert contract.error_category == "contract"
    assert contract.contract_validation == "failed"
    assert contract.record is None

    # 3. technical: the target schema version does not exist in the registry.
    technical = pipeline.run(_request(target_schema_version=99))
    assert technical.outcome == "failed"
    assert technical.error_category == "technical"
    assert technical.contract_validation == "not_evaluated"
    assert technical.record is None

    # 4. business_rule: the external Validation Service's verdict — rule
    # EVALUATION lives outside this codebase; only the verdict maps here.
    completed = pipeline.run(_request())
    verdict = RulesetVerdict(
        ok=False,
        violations=(
            BusinessRuleViolation(
                rule_id="total-equals-line-item-sum",
                message="ruleset violation reported by the external Validation Service",
                fields=("total_amount",),
            ),
        ),
    )
    business = apply_ruleset_verdict(completed, verdict)
    assert business.outcome == "rejected"
    assert business.error_category == "business_rule"

    categories = {uncertain.error_category, contract.error_category, technical.error_category, business.error_category}
    assert categories == {"extraction_uncertainty", "contract", "technical", "business_rule"}


def test_passing_ruleset_verdict_leaves_a_completed_result_unchanged() -> None:
    completed = _pipeline().run(_request())

    assert apply_ruleset_verdict(completed, RulesetVerdict(ok=True)) == completed


def test_result_is_a_mapping_result_with_component_versions() -> None:
    result = _pipeline().run(_request())

    assert isinstance(result, MappingResult)
    assert result.component_versions
