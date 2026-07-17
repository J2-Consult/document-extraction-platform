"""EffectiveMaskMaterializer (ADR 20): vendor baseline + customer deltas ->
ONE complete, attributed, materialized customer mask.

Golden test: materializing fixtures/artifacts/mask_nvvendor.v1's body with the
customer's 3 overrides must reproduce fixtures/artifacts/mask_nvcust.v1.json's
body exactly (typed equality AND wire form), and the result must be
validator-clean. Re-materialization on baseline adoption is an explicit
reviewable event naming its trigger and actor — never silent.
"""

from __future__ import annotations

import pytest

from domain.artifacts.mask import DecoderMaskArtifact, DecoderMaskBody, MaskRef, TargetBinding
from services.lifecycle.errors import LifecycleError
from services.lifecycle.materializer import CustomerOverride, EffectiveMaskMaterializer
from services.validation.bundle import ArtifactBundle
from services.validation.validator import default_validator
from tests.unit.services.lifecycle._fixtures import load_artifact_json, load_mask, load_template

TENANT = "t-nordvik"


def _target(field: str) -> TargetBinding:
    # model_validate with the WIRE key "schema": mypy's dataclass_transform view
    # of TargetBinding only accepts the alias, which shadows BaseModel.schema.
    return TargetBinding.model_validate({"schema": "invoice_record_v1", "field": field, "datatype": "string"})


def nordvik_overrides() -> tuple[CustomerOverride, ...]:
    """The customer's 3 overrides that produce mask_nvcust.v1 (FIXTURES-SPEC)."""
    return (
        CustomerOverride(
            element_id="el_currency",
            semantic_role="currency",
            target=_target("currency"),
            enum_map={"NOK": "NOK", "Kr": "NOK"},
            validated_by="customer-analyst-1",
        ),
        CustomerOverride(
            element_id="el_payment_terms",
            semantic_role="payment_terms_code",
            target=_target("payment_terms_code"),
            validated_by="customer-analyst-1",
        ),
        CustomerOverride(
            element_id="el_notes",
            semantic_role="internal_note",
            target=_target("internal_note"),
            validated_by="customer-analyst-1",
        ),
    )


def materialize_nvcust() -> DecoderMaskBody:
    baseline = load_mask("mask_nvvendor.v1").body
    return EffectiveMaskMaterializer().materialize(
        baseline,
        mask_id="mask_nvcust",
        version=1,
        tenant_id=TENANT,
        overrides=nordvik_overrides(),
    )


def test_golden_materialized_mask_equals_fixture_mask_nvcust_body() -> None:
    assert materialize_nvcust() == load_mask("mask_nvcust.v1").body


def test_golden_materialized_mask_matches_fixture_wire_form() -> None:
    # by_alias=True: TargetBinding.target_schema must serialize as "schema"
    # (E01 wire-form note); exclude_none drops the optional keys the fixture omits.
    wire = materialize_nvcust().model_dump(by_alias=True, exclude_none=True)
    assert wire == load_artifact_json("mask_nvcust.v1")["body"]


def test_golden_materialized_mask_is_validator_clean() -> None:
    artifact = DecoderMaskArtifact(
        artifact_id="mask_nvcust",
        version=1,
        tenant_id=TENANT,
        created_at="2026-07-01T00:00:00Z",  # type: ignore[arg-type]
        body=materialize_nvcust(),
    )

    report = default_validator().validate(ArtifactBundle(template=load_template("tmpl_nvinv.v1"), mask=artifact))

    assert report.ok, f"materialized mask must be validator-clean, got: {report.violations}"


def test_full_baseline_coverage_with_exactly_the_overrides_flagged() -> None:
    baseline = load_mask("mask_nvvendor.v1").body

    materialized = materialize_nvcust()

    assert {entry.element_id for entry in materialized.entries} == {entry.element_id for entry in baseline.entries}
    overridden = {entry.element_id for entry in materialized.entries if entry.attribution.overridden}
    assert overridden == {"el_currency", "el_payment_terms", "el_notes"}
    for entry in materialized.entries:
        assert entry.attribution.inherited_from == MaskRef(mask_id="mask_nvvendor", version=1)
        assert entry.attribution.origin == ("customer" if entry.attribution.overridden else "vendor")


def test_override_for_element_missing_from_baseline_is_rejected() -> None:
    baseline = load_mask("mask_nvvendor.v1").body
    stray = CustomerOverride(
        element_id="el_ghost",
        semantic_role="ghost",
        target=_target("internal_note"),
        validated_by="customer-analyst-1",
    )

    with pytest.raises(LifecycleError):
        EffectiveMaskMaterializer().materialize(
            baseline, mask_id="mask_nvcust", version=1, tenant_id=TENANT, overrides=(stray,)
        )


def test_duplicate_overrides_for_one_element_are_rejected() -> None:
    baseline = load_mask("mask_nvvendor.v1").body
    override = nordvik_overrides()[0]

    with pytest.raises(LifecycleError):
        EffectiveMaskMaterializer().materialize(
            baseline, mask_id="mask_nvcust", version=1, tenant_id=TENANT, overrides=(override, override)
        )


def test_customer_scope_materialization_requires_a_vendor_baseline() -> None:
    customer_mask = load_mask("mask_nvcust.v1").body

    with pytest.raises(LifecycleError):
        EffectiveMaskMaterializer().materialize(
            customer_mask, mask_id="mask_x", version=1, tenant_id=TENANT, overrides=()
        )


def test_baseline_adoption_rematerializes_as_an_explicit_reviewable_event() -> None:
    current = load_mask("mask_nvcust.v1").body
    new_baseline = load_mask("mask_nvvendor.v1").body.model_copy(update={"version": 2})

    adoption = EffectiveMaskMaterializer().adopt_baseline(
        new_baseline, current, actor="customer-analyst-1", reason="adopt vendor baseline v2"
    )

    assert adoption.event.trigger == "baseline_adoption"
    assert adoption.event.actor == "customer-analyst-1"
    assert adoption.event.baseline_ref == MaskRef(mask_id="mask_nvvendor", version=2)
    body = adoption.mask_body
    assert body.version == current.version + 1  # appended version, never a mutation
    assert {entry.element_id for entry in body.entries if entry.attribution.overridden} == {
        "el_currency",
        "el_payment_terms",
        "el_notes",
    }
    for entry in body.entries:
        assert entry.attribution.inherited_from == MaskRef(mask_id="mask_nvvendor", version=2)
