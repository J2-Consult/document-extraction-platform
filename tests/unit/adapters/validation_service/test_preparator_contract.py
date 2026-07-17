"""Validation Service preparator (E09): recorded-request contract test.

The service itself is FAKED — rule evaluation (totals, cross-field
arithmetic) never happens in this codebase. What is tested here is the
hand-off: the preparator flattens the decoded record, attaches `_bboxes`
from provenance, invokes the ruleset through the injected client Protocol,
and the recorded request validates against the PINNED schema at
tests/contracts/validation_service_request.schema.json. Business-rule
violations map to the `business_rule` category, distinct from the other
three.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Dev-only dependency without bundled stubs; adding types-jsonschema would be
# a new dependency (CLAUDE.md), so the untyped import is acknowledged instead.
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from adapters.validation_service.client import ValidationRequest, ValidationServiceClient
from adapters.validation_service.preparator import RecordPreparator
from domain.artifacts.content import ContentArtifact
from domain.artifacts.mask import DecoderMaskArtifact
from domain.artifacts.provenance import Provenance
from domain.artifacts.template import TemplateArtifact
from domain.registry import default_registry
from services.mapping.outcome import BusinessRuleViolation, RulesetVerdict, apply_ruleset_verdict
from services.mapping.pipeline import MappingRequest, build_default_pipeline

REPO_ROOT = Path(__file__).resolve().parents[4]
ARTIFACTS_DIR = REPO_ROOT / "fixtures" / "artifacts"
PINNED_SCHEMA_PATH = REPO_ROOT / "tests" / "contracts" / "validation_service_request.schema.json"


def _load(name: str) -> dict[str, Any]:
    return dict(json.loads((ARTIFACTS_DIR / f"{name}.json").read_text(encoding="utf-8")))


class RecordingFakeClient:
    """Fake Validation Service: records the request, returns a scripted verdict."""

    def __init__(self, verdict: RulesetVerdict) -> None:
        self._verdict = verdict
        self.requests: list[ValidationRequest] = []

    def evaluate(self, request: ValidationRequest) -> RulesetVerdict:
        self.requests.append(request)
        return self._verdict


def _mapped_record_and_provenance() -> tuple[dict[str, Any], dict[str, Provenance]]:
    content = ContentArtifact.model_validate(_load("content_nv20260043.v1")).body
    mask = DecoderMaskArtifact.model_validate(_load("mask_nvvendor.v1")).body
    template = TemplateArtifact.model_validate(_load("tmpl_nvinv.v1")).body
    result = build_default_pipeline(registry=default_registry()).run(
        MappingRequest(content=content, mask=mask, template=template, target_schema_version=1)
    )
    assert result.outcome == "completed" and result.record is not None
    observations = {observation.element_id: observation for observation in content.observations}
    provenance_by_field = {
        entry.target.field: observations[entry.element_id].provenance
        for entry in mask.entries
        if entry.target.field in result.record and entry.element_id in observations
    }
    return result.record, provenance_by_field


def test_recorded_request_validates_against_the_pinned_contract_schema() -> None:
    fake = RecordingFakeClient(RulesetVerdict(ok=True))
    record, provenance_by_field = _mapped_record_and_provenance()

    RecordPreparator(fake).invoke(
        ruleset_id="erp_invoice",
        target_schema="invoice_record_v1",
        target_schema_version=1,
        record=record,
        provenance_by_field=provenance_by_field,
    )

    assert len(fake.requests) == 1
    payload = fake.requests[0].model_dump(by_alias=True)
    schema = json.loads(PINNED_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)


def test_flattened_record_expands_arrays_to_scalar_paths() -> None:
    fake = RecordingFakeClient(RulesetVerdict(ok=True))
    record, provenance_by_field = _mapped_record_and_provenance()

    RecordPreparator(fake).invoke(
        ruleset_id="erp_invoice",
        target_schema="invoice_record_v1",
        target_schema_version=1,
        record=record,
        provenance_by_field=provenance_by_field,
    )

    flat = fake.requests[0].record
    assert flat["invoice_number"] == "2026-0043"
    assert flat["total_amount"] == 13750.0
    assert flat["approved"] is True
    assert flat["line_items/0/description"] == "Widget A"
    assert flat["line_items/0/qty"] == 2.0
    assert flat["line_items/1/amount"] == 600.0
    assert all(not isinstance(value, dict | list) for value in flat.values()), "flattened means scalars only"


def test_bboxes_attach_page_and_bbox_from_provenance_per_top_level_field() -> None:
    fake = RecordingFakeClient(RulesetVerdict(ok=True))
    record, provenance_by_field = _mapped_record_and_provenance()

    RecordPreparator(fake).invoke(
        ruleset_id="erp_invoice",
        target_schema="invoice_record_v1",
        target_schema_version=1,
        record=record,
        provenance_by_field=provenance_by_field,
    )

    bboxes = fake.requests[0].bboxes
    assert set(bboxes) == set(record)
    assert bboxes["total_amount"]["page"] == 1
    assert bboxes["total_amount"]["bbox"] == [206.0, 612.0, 346.0, 624.0]
    assert bboxes["line_items"]["bbox"] == [56.0, 432.0, 500.0, 494.0]


def test_wire_payload_uses_the_underscore_bboxes_key() -> None:
    fake = RecordingFakeClient(RulesetVerdict(ok=True))
    record, provenance_by_field = _mapped_record_and_provenance()

    RecordPreparator(fake).invoke(
        ruleset_id="erp_invoice",
        target_schema="invoice_record_v1",
        target_schema_version=1,
        record=record,
        provenance_by_field=provenance_by_field,
    )

    payload = fake.requests[0].model_dump(by_alias=True)
    assert "_bboxes" in payload
    assert "bboxes" not in payload


def test_business_rule_violation_verdict_maps_to_the_distinct_business_rule_category() -> None:
    failing = RulesetVerdict(
        ok=False,
        violations=(
            BusinessRuleViolation(
                rule_id="total-equals-line-item-sum",
                message="external ruleset violation",
                fields=("total_amount",),
            ),
        ),
    )
    fake = RecordingFakeClient(failing)
    record, provenance_by_field = _mapped_record_and_provenance()

    verdict = RecordPreparator(fake).invoke(
        ruleset_id="erp_invoice",
        target_schema="invoice_record_v1",
        target_schema_version=1,
        record=record,
        provenance_by_field=provenance_by_field,
    )
    content = ContentArtifact.model_validate(_load("content_nv20260043.v1")).body
    mask = DecoderMaskArtifact.model_validate(_load("mask_nvvendor.v1")).body
    template = TemplateArtifact.model_validate(_load("tmpl_nvinv.v1")).body
    completed = build_default_pipeline(registry=default_registry()).run(
        MappingRequest(content=content, mask=mask, template=template, target_schema_version=1)
    )

    rejected = apply_ruleset_verdict(completed, verdict)

    assert rejected.outcome == "rejected"
    assert rejected.error_category == "business_rule"
    assert rejected.error_category not in ("contract", "extraction_uncertainty", "technical")


def test_client_protocol_is_satisfied_structurally_by_the_fake() -> None:
    client: ValidationServiceClient = RecordingFakeClient(RulesetVerdict(ok=True))
    assert hasattr(client, "evaluate")
