"""TargetedExtractor (fast path): label-text-first anchor matching tolerant
to small shifts, value-region read, E01-legal state assignment
(present/empty/unreadable/not_found), provenance on every observation.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any

import pytest

from adapters.passes.native_text import NATIVE_TEXT_COMPONENT_VERSION, PypdfNativeTextPass
from domain.artifacts.content import Observation
from domain.artifacts.template import TemplateArtifact, TemplateBody
from domain.extraction import IDENTITY_TRANSFORM, PageDims, PassOutput, TextSpan
from services.extraction.targeted import TargetedExtractor
from tests.unit.fakes.passes import ScriptedNativeTextPass
from tests.unit.fakes.pdfs import NV_20260043, render_invoice_pdf_bytes, render_invoice_pdf_shifted

LoadFixture = Callable[[str], dict[str, Any]]


def _template(load_fixture_artifact: LoadFixture) -> TemplateBody:
    return TemplateArtifact.model_validate(load_fixture_artifact("tmpl_nvinv.v1")).body


def _expected_from_content(load_fixture_artifact: LoadFixture) -> dict[str, tuple[str | None, str]]:
    body = load_fixture_artifact("content_nv20260043.v1")["body"]
    return {obs["element_id"]: (obs["value"], obs["state"]) for obs in body["observations"]}


def _by_element(observations: list[Observation]) -> dict[str, Observation]:
    return {observation.element_id: observation for observation in observations}


def _extractor() -> TargetedExtractor:
    return TargetedExtractor(PypdfNativeTextPass())


def _assert_full_recovery(observations: list[Observation], load_fixture_artifact: LoadFixture) -> None:
    expected = _expected_from_content(load_fixture_artifact)
    actual = _by_element(observations)
    assert set(actual) == set(expected), "one observation per template element"
    for element_id, (value, state) in expected.items():
        assert actual[element_id].state == state, f"{element_id}: expected state {state}"
        assert actual[element_id].value == value, f"{element_id}: expected value {value!r}"


def test_born_digital_invoice_0043_extracts_every_value_with_pdf_text_provenance(
    load_fixture_artifact: LoadFixture,
) -> None:
    pdf_bytes = render_invoice_pdf_bytes(NV_20260043)

    observations = _extractor().extract(pdf_bytes, _template(load_fixture_artifact))

    _assert_full_recovery(observations, load_fixture_artifact)
    for observation in observations:
        assert observation.provenance.method == "pdf_text", (
            f"{observation.element_id} must come from native text, got {observation.provenance.method}"
        )
        assert observation.provenance.component_version == NATIVE_TEXT_COMPONENT_VERSION


def test_five_px_shifted_rerender_of_invoice_0043_recovers_all_values_via_anchors(
    load_fixture_artifact: LoadFixture,
) -> None:
    shifted_pdf = render_invoice_pdf_shifted(NV_20260043, dy=-5.0)

    observations = _extractor().extract(shifted_pdf, _template(load_fixture_artifact))

    _assert_full_recovery(observations, load_fixture_artifact)
    states = {observation.state for observation in observations}
    assert "not_found" not in states and "unreadable" not in states


def test_anchorless_table_element_follows_the_median_anchor_shift(load_fixture_artifact: LoadFixture) -> None:
    shifted_pdf = render_invoice_pdf_shifted(NV_20260043, dy=-5.0)

    observations = _by_element(_extractor().extract(shifted_pdf, _template(load_fixture_artifact)))

    line_items = observations["el_line_items"]
    assert line_items.state == "present"
    assert line_items.value is not None and "Widget A 2 100.00 200.00" in line_items.value
    assert line_items.provenance.bbox[1] < 480.0, "recorded bbox must reflect the shifted read region"


def test_missing_label_yields_not_found_with_provenance(load_fixture_artifact: LoadFixture) -> None:
    template = _template(load_fixture_artifact)
    probe = template.elements[0].model_copy(
        update={
            "element_id": "el_po_number",
            "bbox": [206.0, 300.0, 346.0, 312.0],
            "anchor": template.elements[0].anchor.model_copy(  # type: ignore[union-attr]
                update={"label_text": "PO number:", "label_bbox": [56.0, 300.0, 196.0, 312.0]}
            ),
        }
    )
    template = template.model_copy(update={"elements": [*template.elements, probe]})

    observations = _by_element(_extractor().extract(render_invoice_pdf_bytes(NV_20260043), template))

    not_found = observations["el_po_number"]
    assert not_found.state == "not_found"
    assert not_found.value is None
    assert not_found.provenance.bbox == [206.0, 300.0, 346.0, 312.0], "provenance records where we looked"
    assert not_found.provenance.method == "pdf_text"


def test_illegible_spans_in_value_region_yield_unreadable_distinct_from_empty_and_not_found(
    load_fixture_artifact: LoadFixture,
) -> None:
    template = _template(load_fixture_artifact)
    pdf_bytes = render_invoice_pdf_bytes(NV_20260043)
    real_output = PypdfNativeTextPass().extract_text(pdf_bytes)

    def degrade(span: TextSpan) -> TextSpan:
        # Smudge exactly the payment-terms value region: [206, 636, 346, 648].
        if span.bbox[1] == pytest.approx(636.0) and span.bbox[0] == pytest.approx(206.0):
            return span.model_copy(update={"confidence": 0.2})
        return span

    degraded = real_output.model_copy(update={"spans": tuple(degrade(span) for span in real_output.spans)})

    observations = _by_element(TargetedExtractor(ScriptedNativeTextPass(degraded)).extract(pdf_bytes, template))

    assert observations["el_payment_terms"].state == "unreadable"
    assert observations["el_payment_terms"].value is None
    assert observations["el_notes"].state == "empty"
    assert observations["el_notes"].value is None
    states = {observations[element_id].state for element_id in ("el_payment_terms", "el_notes", "el_invoice_number")}
    assert states == {"unreadable", "empty", "present"}, "the three absence/presence cases must be distinguishable"


def test_every_observation_carries_complete_provenance(load_fixture_artifact: LoadFixture) -> None:
    pdf_bytes = render_invoice_pdf_bytes(NV_20260043)

    observations = _extractor().extract(pdf_bytes, _template(load_fixture_artifact))

    source_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    assert len(observations) > 0
    for observation in observations:
        provenance = observation.provenance
        assert provenance.source.artifact_sha256 == source_sha256
        assert provenance.source.page == 1
        assert len(provenance.bbox) == 4
        assert provenance.component_version
        assert provenance.working.coordinate_space == "page-1"
        assert list(provenance.transform_to_source) == list(IDENTITY_TRANSFORM)
        assert 0.0 <= observation.confidence.calibrated <= observation.confidence.raw <= 1.0


def test_confidently_blank_optional_field_is_empty_not_low_confidence(load_fixture_artifact: LoadFixture) -> None:
    observations = _by_element(
        _extractor().extract(render_invoice_pdf_bytes(NV_20260043), _template(load_fixture_artifact))
    )

    notes = observations["el_notes"]
    assert notes.state == "empty"
    assert notes.value is None
    assert notes.confidence.calibrated >= 0.9, "a blank region in a trustworthy text layer is CONFIDENTLY blank"


def test_scripted_source_without_page_dims_is_rejected() -> None:
    empty_output = PassOutput(
        method="pdf_text",
        component_version="x/1",
        transform_to_source=list(IDENTITY_TRANSFORM),
        pages=(),
    )
    extractor = TargetedExtractor(ScriptedNativeTextPass(empty_output))
    template = TemplateBody(
        template_id="t",
        version=1,
        doc_class="invoice",
        fingerprint="fpv1:sha256:" + "0" * 64,
        page_count=1,
        pages=[{"page": 1, "width": 595.0, "height": 842.0, "unit": "pt", "rotation": 0}],  # type: ignore[list-item]
        elements=[
            {
                "element_id": "el_x",
                "kind": "value_region",
                "page": 1,
                "bbox": [206.0, 780.0, 346.0, 792.0],
            }  # type: ignore[list-item]
        ],
    )

    with pytest.raises(ValueError, match="page"):
        extractor.extract(b"%PDF-1.4 fake", template)


def _page_dims() -> tuple[PageDims, ...]:
    return (PageDims(page=1, width=595.0, height=842.0),)
