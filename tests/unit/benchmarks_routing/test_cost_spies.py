"""Unit tests for the tiny local provider spies + cascade stand-in used by
criterion 1's acceptance test and the benchmark harness's cost model.
"""

from __future__ import annotations

from benchmarks.routing.cost_spies import (
    FullLayoutProviderSpy,
    RegionalModelProviderSpy,
    WholeDocumentVlmProviderSpy,
    simulate_extraction_cascade,
)


def test_fast_path_calls_only_the_regional_provider() -> None:
    full_layout = FullLayoutProviderSpy()
    whole_document_vlm = WholeDocumentVlmProviderSpy()
    regional = RegionalModelProviderSpy()
    regions = ((0.0, 0.0, 10.0, 10.0), (20.0, 20.0, 30.0, 30.0))

    simulate_extraction_cascade(
        routed_to="fast_path",
        pdf_bytes=b"pdf",
        regions=regions,
        full_layout=full_layout,
        whole_document_vlm=whole_document_vlm,
        regional=regional,
    )

    assert full_layout.call_count == 0
    assert whole_document_vlm.call_count == 0
    assert regional.call_count == len(regions)


def test_full_analysis_calls_full_layout_and_whole_document_vlm_never_regional() -> None:
    full_layout = FullLayoutProviderSpy()
    whole_document_vlm = WholeDocumentVlmProviderSpy()
    regional = RegionalModelProviderSpy()

    simulate_extraction_cascade(
        routed_to="full_analysis",
        pdf_bytes=b"pdf",
        regions=((0.0, 0.0, 10.0, 10.0),),
        full_layout=full_layout,
        whole_document_vlm=whole_document_vlm,
        regional=regional,
    )

    assert full_layout.call_count == 1
    assert whole_document_vlm.call_count == 1
    assert regional.call_count == 0
