"""decoded_view: typed artifact bodies -> chunker input (`DecodedElement`).

The semantic builder mirrors the E07 decoded view's join semantics (values
joined through ONE mask's entries); the structural builder reads the content
observations directly and takes section paths from the template's heading
hierarchy. Only `state == "present"` observations carry text to embed.
"""

from __future__ import annotations

from domain.artifacts.content import Confidence, ContentBody, CoordinateSpace, Observation, SourceDescriptor
from domain.artifacts.mask import DecoderMaskBody, EntryAttribution, MaskEntry, TargetBinding
from domain.artifacts.provenance import Provenance, SourceRef, WorkingRef
from domain.artifacts.template import Anchor, PageGeometry, TemplateBody, TemplateElement

_SHA = "c" * 64


def _provenance(page: int, bbox: list[float]) -> Provenance:
    return Provenance(
        source=SourceRef(artifact_sha256=_SHA, page=page),
        working=WorkingRef(artifact_sha256=_SHA, coordinate_space=f"page-{page}"),
        bbox=bbox,
        method="pdf_text",
        component_version="fixture-1.0.0",
        transform_to_source=[1, 0, 0, 1, 0, 0],
    )


def _observation(element_id: str, value: str | None, state: str, page: int = 1) -> Observation:
    return Observation(
        element_id=element_id,
        value=value,
        state=state,  # type: ignore[arg-type]
        confidence=Confidence(raw=0.95, calibrated=0.93),
        provenance=_provenance(page, [56.0, 496.0, 540.0, 528.0]),
    )


def _content(observations: list[Observation]) -> ContentBody:
    return ContentBody(
        content_id="content_mbr001",
        document_id="doc_mbr001",
        version=1,
        template_ref=None,
        source=SourceDescriptor(sha256=_SHA, media_type="application/pdf", page_count=2),
        coordinate_spaces=[CoordinateSpace(id="page-1", page=1, width=595.0, height=842.0, unit="pt")],
        observations=observations,
    )


def _mask_entry(element_id: str, semantic_role: str, section_path: str | None) -> MaskEntry:
    return MaskEntry(
        element_id=element_id,
        semantic_role=semantic_role,
        target=TargetBinding.model_validate(
            {"schema": "maintenance_record_v1", "field": semantic_role, "datatype": "string"}
        ),
        section_path=section_path,
        attribution=EntryAttribution(origin="vendor", inherited_from=None, overridden=False, validated_by="vc-1"),
    )


def _mask(entries: list[MaskEntry]) -> DecoderMaskBody:
    from domain.artifacts.template import TemplateRef

    return DecoderMaskBody(
        mask_id="mask_mbrvendor",
        version=1,
        scope="vendor",
        tenant_id=None,
        template_ref=TemplateRef(template_id="tmpl_mbr", version=1),
        system_context="cmms",
        entries=entries,
    )


def _template() -> TemplateBody:
    return TemplateBody(
        template_id="tmpl_mbr",
        version=1,
        doc_class="maintenance_report",
        fingerprint="fpv1:sha256:" + "d" * 64,
        page_count=2,
        pages=[PageGeometry(page=1, width=595.0, height=842.0, unit="pt", rotation=0)],
        elements=[
            TemplateElement(
                element_id="el_sec_13_4",
                kind="value_region",
                page=1,
                bbox=[56.0, 496.0, 540.0, 528.0],
                anchor=Anchor(label_text="13.4 Bearing Inspection", label_bbox=[56.0, 538.0, 300.0, 554.0]),
            ),
        ],
    )


class TestSemanticElements:
    def test_joins_present_observations_to_mask_entries(self) -> None:
        from services.embedding.decoded_view import semantic_elements

        content = _content([_observation("el_sec_13_4", "Bearing inspected.", "present")])
        mask = _mask([_mask_entry("el_sec_13_4", "bearing_inspection_notes", "13.4")])

        elements = semantic_elements(content, mask)

        assert len(elements) == 1
        element = elements[0]
        assert element.document_id == "doc_mbr001"
        assert element.element_id == "el_sec_13_4"
        assert element.text == "Bearing inspected."
        assert element.semantic_role == "bearing_inspection_notes"
        assert element.system_context == "cmms"
        assert element.section_path == "13.4"
        assert element.page == 1
        assert element.bbox == (56.0, 496.0, 540.0, 528.0)
        assert element.provenance["method"] == "pdf_text"

    def test_non_present_observations_and_unmasked_elements_are_excluded(self) -> None:
        from services.embedding.decoded_view import semantic_elements

        content = _content(
            [
                _observation("el_sec_13_4", "Bearing inspected.", "present"),
                _observation("el_sec_9_7", None, "unreadable"),
                _observation("el_sec_no_mask", "Orphan text.", "present"),
            ]
        )
        mask = _mask(
            [
                _mask_entry("el_sec_13_4", "bearing_inspection_notes", "13.4"),
                _mask_entry("el_sec_9_7", "torque_verification_notes", "9.7"),
            ]
        )

        elements = semantic_elements(content, mask)

        assert [element.element_id for element in elements] == ["el_sec_13_4"]


class TestStructuralElements:
    def test_present_observations_become_elements_with_heading_section_paths(self) -> None:
        from services.embedding.decoded_view import structural_elements

        content = _content(
            [
                _observation("el_sec_13_4", "Bearing inspected.", "present"),
                _observation("el_sec_9_7", None, "unreadable"),
            ]
        )

        elements = structural_elements(content, _template())

        assert [element.element_id for element in elements] == ["el_sec_13_4"]
        assert elements[0].section_path == "13.4"
        assert elements[0].semantic_role is None  # structural tier: no mask meaning

    def test_without_a_template_section_paths_stay_none(self) -> None:
        from services.embedding.decoded_view import structural_elements

        content = _content([_observation("el_sec_13_4", "Bearing inspected.", "present")])

        elements = structural_elements(content, None)

        assert elements[0].section_path is None
