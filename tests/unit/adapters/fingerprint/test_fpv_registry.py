"""Unit tests for the fpv version registry + bump/re-key machinery
(`adapters.fingerprint.fpv`), against fakes only — no PDF parsing here (see
test_born_digital_fpv1_parity.py for that).
"""

from __future__ import annotations

import pytest

from adapters.fingerprint import fpv
from domain.artifacts.canonical import JsonCanonicalSerializer


def test_current_version_is_registered() -> None:
    assert fpv.current_version() == 1
    assert fpv.get_algorithm(1).version == 1


def test_get_algorithm_raises_for_unknown_version() -> None:
    with pytest.raises(fpv.UnknownFpvVersionError):
        fpv.get_algorithm(999)


def test_register_algorithm_refuses_to_overwrite_an_existing_version() -> None:
    class _DuplicateFpv1:
        version = 1
        grid_bbox_pt = 8
        grid_dim_pt = 4

        def build_features(self, page_count: object, pages: object) -> object:  # pragma: no cover - never called
            raise NotImplementedError

        def features_from_bboxes(self, page_count: object, pages: object) -> object:  # pragma: no cover
            raise NotImplementedError

        def quantize_dims(self, width: float, height: float) -> tuple[int, int]:  # pragma: no cover
            raise NotImplementedError

    with pytest.raises(fpv.FpvAlgorithmAlreadyRegisteredError):
        fpv.register_algorithm(_DuplicateFpv1())  # type: ignore[arg-type]


def test_fingerprint_key_is_deterministic_and_content_free() -> None:
    serializer = JsonCanonicalSerializer()
    algorithm = fpv.get_algorithm(1)
    features_a = algorithm.features_from_bboxes(page_count=1, pages=[(595.0, 842.0, [(56.0, 780.0, 150.0, 792.0)])])
    features_b = algorithm.features_from_bboxes(page_count=1, pages=[(595.0, 842.0, [(56.0, 780.0, 150.0, 792.0)])])

    key_a = fpv.fingerprint_key(features_a, serializer)
    key_b = fpv.fingerprint_key(features_b, serializer)

    assert key_a == key_b
    assert key_a.startswith("fpv1:sha256:")
    assert len(key_a.split(":")[-1]) == 64


def test_rekey_template_fingerprint_matches_a_direct_features_from_bboxes_call() -> None:
    serializer = JsonCanonicalSerializer()
    pages = [(595.0, 842.0, [(56.0, 780.0, 196.0, 792.0), (206.0, 780.0, 346.0, 792.0)])]

    rekeyed = fpv.rekey_template_fingerprint(page_count=1, pages=pages, fpv_version=1, serializer=serializer)
    direct = fpv.fingerprint_key(fpv.get_algorithm(1).features_from_bboxes(1, pages), serializer)

    assert rekeyed == direct
    assert rekeyed.startswith("fpv1:sha256:")


def test_quantize_dims_buckets_to_the_4pt_grid() -> None:
    algorithm = fpv.get_algorithm(1)
    assert algorithm.quantize_dims(595.0, 842.0) == (596, 840)
    assert algorithm.quantize_dims(595.9, 841.6) == (596, 840)
