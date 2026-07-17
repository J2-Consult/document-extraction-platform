"""JsonCanonicalSerializer (src/domain/artifacts/canonical.py) must reproduce
fixtures/fpv1.py's `canonical_json` byte-for-byte for the same input.

`fpv1.py` is loaded via a path-based importlib loader here, in the test only
— src/ never imports from fixtures/ (fixtures/ is test data, not a runtime
dependency; see specs/epics/E01-artifact-contracts.md).
"""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from domain.artifacts.canonical import JsonCanonicalSerializer
from ports.canonical import CanonicalSerializer

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_fpv1_module() -> ModuleType:
    fpv1_path = REPO_ROOT / "fixtures" / "fpv1.py"
    if not fpv1_path.exists():
        pytest.skip(f"fixture not yet present: {fpv1_path.relative_to(REPO_ROOT)}")
    spec = importlib.util.spec_from_file_location("fpv1_reference", fpv1_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def fpv1() -> ModuleType:
    return _load_fpv1_module()


@pytest.fixture
def serializer() -> CanonicalSerializer:
    return JsonCanonicalSerializer()


@pytest.mark.parametrize(
    "obj",
    [
        {},
        {"b": 1, "a": 2},
        {"fpv": 1, "page_count": 1, "pages": [{"w_bucket": 592, "h_bucket": 840, "lines": [[56, 780, 200, 792]]}]},
        {"nested": {"z": [3, 2, 1], "a": None, "b": True, "c": 1.5}},
        {"unicode": "café ☃"},
    ],
)
def test_canonical_bytes_matches_fpv1_canonical_json_byte_for_byte(
    serializer: CanonicalSerializer, fpv1: ModuleType, obj: dict[str, object]
) -> None:
    assert serializer.canonical_bytes(obj) == fpv1.canonical_json(obj)


def test_canonical_bytes_matches_fpv1_fingerprint_over_real_template_features(fpv1: ModuleType) -> None:
    """End-to-end: hashing our canonical bytes reproduces fpv1's own fingerprint()."""
    features = fpv1.build_features(
        page_count=1,
        pages=[{"width": 595, "height": 842, "lines": [fpv1.line_bbox(56, 780, "Invoice number:", 10)]}],
    )
    serializer = JsonCanonicalSerializer()

    our_digest = hashlib.sha256(serializer.canonical_bytes(features)).hexdigest()
    reference_fingerprint = fpv1.fingerprint(features)

    assert reference_fingerprint == f"fpv1:sha256:{our_digest}"


def test_canonical_bytes_rejects_nan(serializer: CanonicalSerializer) -> None:
    with pytest.raises(ValueError):  # noqa: PT011 - json.dumps raises plain ValueError for NaN
        serializer.canonical_bytes({"x": float("nan")})


def test_canonical_serializer_implements_the_port_protocol(serializer: CanonicalSerializer) -> None:
    assert isinstance(serializer, CanonicalSerializer)
