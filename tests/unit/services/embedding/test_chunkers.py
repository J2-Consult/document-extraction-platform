"""Unit tests for the E11 chunkers: overlap boundaries exact, heading-path
assignment, provenance on EVERY chunk (criterion 9 extension)."""

from __future__ import annotations

from typing import Any

import pytest

from domain.artifacts.template import Anchor, TemplateElement

_PROVENANCE = {
    "source": {"artifact_sha256": "a" * 64, "page": 1},
    "working": {"artifact_sha256": "a" * 64, "coordinate_space": "page-1"},
    "bbox": [56.0, 496.0, 540.0, 528.0],
    "method": "pdf_text",
    "component_version": "fixture-1.0.0",
    "transform_to_source": [1, 0, 0, 1, 0, 0],
}


def _decoded_element(**overrides: object) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "document_id": "doc_mbr001",
        "element_id": "el_sec_13_4",
        "text": "Main rotor bearing inspected per AMM 32-41-00.",
        "page": 1,
        "bbox": (56.0, 496.0, 540.0, 528.0),
        "provenance": _PROVENANCE,
    }
    defaults.update(overrides)
    return defaults


class TestSemanticChunker:
    def test_one_chunk_per_decoded_row_with_no_windowing(self) -> None:
        from services.embedding.chunkers import DecodedElement, SemanticChunker

        elements = [
            DecodedElement(
                **_decoded_element(
                    semantic_role="bearing_inspection_notes",
                    system_context="cmms",
                    section_path="13.4",
                )
            ),
        ]
        chunks = SemanticChunker().chunk(elements)

        assert len(chunks) == 1
        chunk = chunks[0]
        assert chunk.text == elements[0].text
        assert chunk.semantic_role == "bearing_inspection_notes"
        assert chunk.system_context == "cmms"
        assert chunk.section_path == "13.4"
        assert chunk.page == 1
        assert chunk.bbox == (56.0, 496.0, 540.0, 528.0)

    def test_missing_semantic_role_is_rejected(self) -> None:
        from services.embedding.chunkers import DecodedElement, MissingSemanticRoleError, SemanticChunker

        elements = [DecodedElement(**_decoded_element())]  # no semantic_role: not mask-resolved
        with pytest.raises(MissingSemanticRoleError):
            SemanticChunker().chunk(elements)

    def test_every_chunk_carries_provenance(self) -> None:
        from services.embedding.chunkers import DecodedElement, SemanticChunker

        elements = [
            DecodedElement(**_decoded_element(element_id="el_sec_13_4", semantic_role="bearing_inspection_notes")),
            DecodedElement(**_decoded_element(element_id="el_sec_16_3", semantic_role="corrective_actions_notes")),
        ]
        chunks = SemanticChunker().chunk(elements)

        assert len(chunks) == 2
        for chunk in chunks:
            assert chunk.provenance == _PROVENANCE
            assert chunk.provenance["source"]["page"] >= 1
            assert len(chunk.provenance["bbox"]) == 4


class TestStructuralChunkerConstruction:
    def test_rejects_non_positive_window(self) -> None:
        from services.embedding.chunkers import InvalidWindowError, StructuralChunker

        with pytest.raises(InvalidWindowError):
            StructuralChunker(window_tokens=0, overlap_tokens=0)

    def test_rejects_overlap_greater_or_equal_to_window(self) -> None:
        from services.embedding.chunkers import InvalidWindowError, StructuralChunker

        with pytest.raises(InvalidWindowError):
            StructuralChunker(window_tokens=4, overlap_tokens=4)
        with pytest.raises(InvalidWindowError):
            StructuralChunker(window_tokens=4, overlap_tokens=5)


class TestStructuralChunkerOverlapBoundaries:
    def test_exact_token_windows_with_overlap(self) -> None:
        from services.embedding.chunkers import DecodedElement, StructuralChunker

        text = "a b c d e f g"  # 7 whitespace tokens
        elements = [DecodedElement(**_decoded_element(text=text))]
        chunker = StructuralChunker(window_tokens=4, overlap_tokens=1)

        chunks = chunker.chunk(elements)

        assert [chunk.text for chunk in chunks] == ["a b c d", "d e f g"]
        assert [chunk.chunk_index for chunk in chunks] == [0, 1]
        assert [chunk.chunk_id for chunk in chunks] == [
            "doc_mbr001:el_sec_13_4:0",
            "doc_mbr001:el_sec_13_4:1",
        ]

    def test_no_overlap_is_a_clean_partition(self) -> None:
        from services.embedding.chunkers import DecodedElement, StructuralChunker

        text = "a b c d e f g h"  # 8 tokens
        elements = [DecodedElement(**_decoded_element(text=text))]
        chunker = StructuralChunker(window_tokens=4, overlap_tokens=0)

        chunks = chunker.chunk(elements)

        assert [chunk.text for chunk in chunks] == ["a b c d", "e f g h"]

    def test_final_short_window_still_emitted_once(self) -> None:
        from services.embedding.chunkers import DecodedElement, StructuralChunker

        text = "a b c d e"  # 5 tokens, window 4 overlap 2 -> stride 2
        elements = [DecodedElement(**_decoded_element(text=text))]
        chunker = StructuralChunker(window_tokens=4, overlap_tokens=2)

        chunks = chunker.chunk(elements)

        # start=0 -> "a b c d"; start=2 -> "c d e" (final short window, not dropped)
        assert [chunk.text for chunk in chunks] == ["a b c d", "c d e"]

    def test_blank_text_yields_no_chunks(self) -> None:
        from services.embedding.chunkers import DecodedElement, StructuralChunker

        elements = [DecodedElement(**_decoded_element(text="   "))]
        chunks = StructuralChunker(window_tokens=4, overlap_tokens=1).chunk(elements)
        assert chunks == ()

    def test_every_chunk_carries_page_bbox_and_provenance(self) -> None:
        from services.embedding.chunkers import DecodedElement, StructuralChunker

        text = "a b c d e f g h i"
        elements = [DecodedElement(**_decoded_element(text=text, page=2, bbox=(1.0, 2.0, 3.0, 4.0)))]
        chunks = StructuralChunker(window_tokens=3, overlap_tokens=1).chunk(elements)

        assert len(chunks) > 1
        for chunk in chunks:
            assert chunk.page == 2
            assert chunk.bbox == (1.0, 2.0, 3.0, 4.0)
            assert chunk.provenance == _PROVENANCE


class TestHeadingHierarchyAssignment:
    def _template_elements(self) -> list[TemplateElement]:
        return [
            TemplateElement(element_id="el_head_13_4", kind="section_heading", page=1, bbox=[56, 538, 300, 554]),
            TemplateElement(
                element_id="el_sec_13_4",
                kind="value_region",
                page=1,
                bbox=[56, 496, 540, 528],
                anchor=Anchor(label_text="13.4 Bearing Inspection", label_bbox=[56, 538, 300, 554]),
            ),
            TemplateElement(element_id="el_head_16_3", kind="section_heading", page=2, bbox=[56, 698, 300, 714]),
            TemplateElement(
                element_id="el_sec_16_3",
                kind="value_region",
                page=2,
                bbox=[56, 640, 540, 688],
                anchor=Anchor(label_text="16.3 Corrective Actions", label_bbox=[56, 698, 300, 714]),
            ),
            TemplateElement(
                element_id="el_sec_no_number",
                kind="value_region",
                page=2,
                bbox=[0, 0, 10, 10],
                anchor=Anchor(label_text="Miscellaneous notes", label_bbox=[0, 0, 10, 10]),
            ),
        ]

    def test_section_path_assigned_from_anchor_leading_section_number(self) -> None:
        from services.embedding.chunkers import DecodedElement, assign_section_paths_from_heading_hierarchy

        elements = [
            DecodedElement(**_decoded_element(element_id="el_sec_13_4", section_path=None)),
            DecodedElement(**_decoded_element(element_id="el_sec_16_3", section_path=None)),
        ]
        resolved = assign_section_paths_from_heading_hierarchy(self._template_elements(), elements)

        assert {element.element_id: element.section_path for element in resolved} == {
            "el_sec_13_4": "13.4",
            "el_sec_16_3": "16.3",
        }

    def test_element_without_dotted_section_number_keeps_section_path_none(self) -> None:
        from services.embedding.chunkers import DecodedElement, assign_section_paths_from_heading_hierarchy

        elements = [DecodedElement(**_decoded_element(element_id="el_sec_no_number", section_path=None))]
        resolved = assign_section_paths_from_heading_hierarchy(self._template_elements(), elements)

        assert resolved[0].section_path is None

    def test_unmatched_element_id_is_left_untouched(self) -> None:
        from services.embedding.chunkers import DecodedElement, assign_section_paths_from_heading_hierarchy

        elements = [DecodedElement(**_decoded_element(element_id="el_ghost", section_path=None))]
        resolved = assign_section_paths_from_heading_hierarchy(self._template_elements(), elements)

        assert resolved[0].section_path is None
