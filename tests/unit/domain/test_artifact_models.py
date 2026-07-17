"""Round-trip fidelity and strictness of the artifact contract models
(src/domain/artifacts/): ArtifactEnvelope/TemplateBody/ContentBody/
DecoderMaskBody and the value-state model (ValueState).

Fixture-shaped construction lives here; InvariantValidator's own mutation
coverage lives in tests/unit/services/validation/test_invariants.py.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from domain.artifacts.content import Confidence, ContentBody, CoordinateSpace, Observation, SourceDescriptor
from domain.artifacts.mask import DecoderMaskArtifact
from domain.artifacts.provenance import Provenance, SourceRef, WorkingRef
from domain.artifacts.template import TemplateArtifact, TemplateElement

# Relative, not `from tests.unit.domain._loaders import ...`: with tests/ having
# no __init__.py, an absolute `tests.*` import alongside pytest's own rootless
# module naming makes mypy see this file under two different module identities
# ("Source file found twice") — relative imports sidestep that entirely.
from ._loaders import ALL_FIXTURE_ARTIFACT_NAMES, parse_fixture_artifact


@pytest.mark.parametrize("fixture_name", ALL_FIXTURE_ARTIFACT_NAMES)
def test_fixture_artifact_round_trips_losslessly_through_model_and_json(
    fixture_name: str, load_fixture_artifact: object
) -> None:
    raw = load_fixture_artifact(fixture_name)  # type: ignore[operator]
    model = parse_fixture_artifact(raw)

    dumped = model.model_dump(mode="json")
    reparsed = parse_fixture_artifact(dumped)

    assert reparsed == model
    # `dumped` must itself be plain, JSON-safe data (no stray Python objects
    # a real json.dumps/json.loads hop would choke on).
    assert json.loads(json.dumps(dumped)) == dumped


def test_unknown_top_level_field_is_rejected_by_strict_parsing(load_fixture_artifact: object) -> None:
    raw = dict(load_fixture_artifact("tmpl_nvinv.v1"))  # type: ignore[operator]
    raw["unexpected_field"] = "not part of the contract"

    with pytest.raises(ValidationError):
        TemplateArtifact.model_validate(raw)


def test_unknown_nested_body_field_is_rejected_by_strict_parsing(load_fixture_artifact: object) -> None:
    raw = json.loads(json.dumps(load_fixture_artifact("tmpl_nvinv.v1")))  # type: ignore[operator]
    raw["body"]["unexpected_field"] = "not part of the contract"

    with pytest.raises(ValidationError):
        TemplateArtifact.model_validate(raw)


def test_wrong_type_for_a_field_is_rejected_by_strict_parsing(load_fixture_artifact: object) -> None:
    raw = json.loads(json.dumps(load_fixture_artifact("tmpl_nvinv.v1")))  # type: ignore[operator]
    raw["body"]["version"] = "1"  # str, not int — strict mode must not coerce

    with pytest.raises(ValidationError):
        TemplateArtifact.model_validate(raw)


def test_parsed_artifact_model_is_frozen(load_fixture_artifact: object) -> None:
    model = parse_fixture_artifact(load_fixture_artifact("mask_nvvendor.v1"))  # type: ignore[operator]

    with pytest.raises(ValidationError):
        model.artifact_id = "different-id"


def test_table_element_without_columns_is_rejected() -> None:
    with pytest.raises(ValidationError):
        TemplateElement(element_id="el_table", kind="table", page=1, bbox=[0, 0, 10, 10])


@pytest.mark.parametrize(
    ("state", "value"),
    [
        ("present", "some decoded text"),
        ("empty", None),
        ("not_applicable", None),
        ("unreadable", None),
        ("not_found", None),
    ],
)
def test_every_value_state_accepts_its_legal_value_shape(state: str, value: str | None) -> None:
    observation = Observation(
        element_id="el_x",
        value=value,
        state=state,  # type: ignore[arg-type]
        confidence=Confidence(raw=0.9, calibrated=0.9),
        provenance=_provenance(),
    )
    assert observation.state == state
    assert observation.value == value


def _provenance() -> Provenance:
    return Provenance(
        source=SourceRef(artifact_sha256="0" * 64, page=1),
        working=WorkingRef(artifact_sha256="0" * 64, coordinate_space="page-1"),
        bbox=[0, 0, 10, 10],
        method="pdf_text",
        component_version="fixture-1.0.0",
        transform_to_source=[1, 0, 0, 1, 0, 0],
    )


def test_content_body_defaults_to_empty_observations_and_unmapped_content() -> None:
    body = ContentBody(
        content_id="content_x",
        document_id="doc_x",
        version=1,
        template_ref=None,
        source=SourceDescriptor(sha256="0" * 64, media_type="application/pdf", page_count=1),
        coordinate_spaces=[CoordinateSpace(id="page-1", page=1, width=595, height=842, unit="pt")],
    )
    assert body.observations == []
    assert body.unmapped_content == []


def test_decoder_mask_artifact_type_is_pinned_to_decoder_mask_literal(load_fixture_artifact: object) -> None:
    model = parse_fixture_artifact(load_fixture_artifact("mask_nvcust.v1"))  # type: ignore[operator]
    assert isinstance(model, DecoderMaskArtifact)
    assert model.artifact_type == "decoder_mask"
