"""E05 pass ports: six single-method Protocols (interface segregation), with
"VLM per region only" enforced structurally — RegionalVlmFallback accepts ONE
region and no protocol exposes a whole-page or whole-document model method.
"""

from __future__ import annotations

import inspect

from ports.extraction_passes import (
    LayoutDetector,
    NativeTextPass,
    OcrPass,
    PagePreprocessor,
    RegionalVlmFallback,
    SpecializedDetector,
)

_EXPECTED_SINGLE_METHODS = {
    NativeTextPass: "extract_text",
    PagePreprocessor: "preprocess",
    LayoutDetector: "detect_regions",
    OcrPass: "recognize_text",
    SpecializedDetector: "detect",
    RegionalVlmFallback: "read_region",
}


def _public_methods(protocol: type) -> list[str]:
    return [
        name
        for name, member in vars(protocol).items()
        if not name.startswith("_") and (inspect.isfunction(member) or inspect.ismethod(member))
    ]


def test_every_pass_protocol_declares_exactly_one_public_method() -> None:
    for protocol, expected in _EXPECTED_SINGLE_METHODS.items():
        assert _public_methods(protocol) == [expected], f"{protocol.__name__} must be single-method (got extra)"


def test_regional_vlm_fallback_reads_exactly_one_region_with_opaque_job_ref() -> None:
    signature = inspect.signature(RegionalVlmFallback.read_region)
    parameter_names = [name for name in signature.parameters if name != "self"]
    assert parameter_names == ["image", "region", "job_ref"]


def test_no_protocol_exposes_a_whole_document_model_method() -> None:
    """The only methods accepting raw whole-document bytes are the deterministic
    native-text pass and the per-page preprocessor; no probabilistic pass
    (layout, OCR, detector, VLM) can even receive a whole document."""
    for protocol, method_name in _EXPECTED_SINGLE_METHODS.items():
        signature = inspect.signature(getattr(protocol, method_name))
        takes_pdf_bytes = "pdf_bytes" in signature.parameters
        deterministic_whole_doc_ok = protocol in (NativeTextPass, PagePreprocessor)
        assert takes_pdf_bytes == deterministic_whole_doc_ok, (
            f"{protocol.__name__}.{method_name} must {'take' if deterministic_whole_doc_ok else 'never take'} "
            "raw pdf_bytes"
        )
