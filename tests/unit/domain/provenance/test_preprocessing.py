"""`domain.provenance.preprocessing`: PreprocessingRecord + its composed
transform, including the property-based round-trip that backs criterion 10
(specs/SKELETON-CRITERIA.md): a bbox mapped through a deskew+scale+crop chain
and back lands within tolerance.

The tolerance is not a fudge factor. `to_transform()` composes only
rotation + uniform scale + translation (a similarity transform, no shear) —
for such a transform, mapping an axis-aligned bbox to its enclosing AABB and
back through the exact inverse AABB-of-AABB grows the box by a closed-form
amount driven by the *total* rotation angle (structural + deskew degrees
combine by simple addition, since composing two pure rotations adds their
angles — see test_transform.py's
`test_compose_of_two_rotations_adds_the_angles`). `_expected_growth` computes
that exact bound per case; the assertions check equality against it (plus a
small float-rounding epsilon), not just "close enough".
"""

from __future__ import annotations

import math
import random

import pytest

from domain.provenance.preprocessing import PreprocessingRecord

_EPSILON = 1e-6


def test_render_dpi_must_be_positive() -> None:
    with pytest.raises(ValueError, match="render_dpi"):
        PreprocessingRecord(render_dpi=0.0, deskew_angle_deg=0.0, crop=None, rotation_deg=0, pipeline_version="v1")


def test_deskew_angle_must_be_finite() -> None:
    with pytest.raises(ValueError, match="deskew_angle_deg"):
        PreprocessingRecord(
            render_dpi=300.0,
            deskew_angle_deg=math.nan,
            crop=None,
            rotation_deg=0,
            pipeline_version="v1",
        )


def test_pipeline_version_must_be_non_empty() -> None:
    with pytest.raises(ValueError, match="pipeline_version"):
        PreprocessingRecord(render_dpi=300.0, deskew_angle_deg=0.0, crop=None, rotation_deg=0, pipeline_version="")


def test_crop_with_non_finite_bound_is_rejected() -> None:
    with pytest.raises(ValueError, match="crop bounds must be finite"):
        PreprocessingRecord(
            render_dpi=300.0,
            deskew_angle_deg=0.0,
            crop=(0.0, 0.0, math.inf, 100.0),
            rotation_deg=0,
            pipeline_version="v1",
        )


def test_crop_with_x1_not_greater_than_x0_is_rejected() -> None:
    with pytest.raises(ValueError, match="x1 > x0"):
        PreprocessingRecord(
            render_dpi=300.0,
            deskew_angle_deg=0.0,
            crop=(10.0, 0.0, 10.0, 100.0),
            rotation_deg=0,
            pipeline_version="v1",
        )


def test_crop_with_y1_not_greater_than_y0_is_rejected() -> None:
    with pytest.raises(ValueError, match="x1 > x0"):
        PreprocessingRecord(
            render_dpi=300.0,
            deskew_angle_deg=0.0,
            crop=(0.0, 10.0, 100.0, 10.0),
            rotation_deg=0,
            pipeline_version="v1",
        )


def test_valid_crop_is_accepted() -> None:
    PreprocessingRecord(
        render_dpi=300.0,
        deskew_angle_deg=0.0,
        crop=(0.0, 0.0, 100.0, 100.0),
        rotation_deg=0,
        pipeline_version="v1",
    )  # does not raise


def test_to_transform_without_crop_omits_translation() -> None:
    record = PreprocessingRecord(
        render_dpi=72.0, deskew_angle_deg=0.0, crop=None, rotation_deg=0, pipeline_version="v1"
    )
    assert record.to_transform().apply_to_point(10.0, 20.0) == pytest.approx((10.0, 20.0))


def test_to_transform_with_crop_translates_by_the_crop_origin() -> None:
    record = PreprocessingRecord(
        render_dpi=72.0,
        deskew_angle_deg=0.0,
        crop=(5.0, 8.0, 100.0, 100.0),
        rotation_deg=0,
        pipeline_version="v1",
    )
    assert record.to_transform().apply_to_point(5.0, 8.0) == pytest.approx((0.0, 0.0), abs=1e-9)


def test_to_transform_scales_by_dpi_over_source_dpi() -> None:
    record = PreprocessingRecord(
        render_dpi=144.0, deskew_angle_deg=0.0, crop=None, rotation_deg=0, pipeline_version="v1"
    )
    assert record.to_transform().apply_to_point(10.0, 10.0) == pytest.approx((20.0, 20.0))


def test_to_transform_applies_structural_rotation() -> None:
    record = PreprocessingRecord(
        render_dpi=72.0, deskew_angle_deg=0.0, crop=None, rotation_deg=90, pipeline_version="v1"
    )
    x, y = record.to_transform().apply_to_point(1.0, 0.0)
    assert x == pytest.approx(0.0, abs=1e-9)
    assert y == pytest.approx(1.0, abs=1e-9)


def _expected_growth(width: float, height: float, total_angle_deg: float) -> tuple[float, float]:
    """Exact AABB-growth bound for a similarity transform (rotation + uniform
    scale + translation) round-tripped through forward-then-inverse
    bbox-via-corners mapping. See module docstring."""
    factor = abs(math.sin(2 * math.radians(total_angle_deg)))
    return (height * factor / 2, width * factor / 2)


def test_bbox_round_trip_through_deskew_scale_crop_lands_within_the_exact_growth_bound() -> None:
    rng = random.Random(424242)
    case_count = 0

    for _ in range(400):
        x0 = rng.uniform(-200.0, 400.0)
        y0 = rng.uniform(-200.0, 400.0)
        width = rng.uniform(1.0, 300.0)
        height = rng.uniform(1.0, 300.0)
        source_bbox = (x0, y0, x0 + width, y0 + height)

        deskew_angle_deg = rng.uniform(-3.0, 3.0)
        rotation_deg = rng.choice([0, 90, 180, 270])
        render_dpi = rng.uniform(72.0, 600.0)
        has_crop = rng.random() < 0.5
        crop = (
            (rng.uniform(-100.0, 0.0), rng.uniform(-100.0, 0.0), rng.uniform(600.0, 900.0), rng.uniform(600.0, 900.0))
            if has_crop
            else None
        )

        record = PreprocessingRecord(
            render_dpi=render_dpi,
            deskew_angle_deg=deskew_angle_deg,
            crop=crop,
            rotation_deg=rotation_deg,  # type: ignore[arg-type]
            pipeline_version="fixture-1.0.0",
        )

        forward = record.to_transform()
        transform_to_source = forward.inverse()

        working_bbox = forward.apply_to_bbox(source_bbox)
        recovered_bbox = transform_to_source.apply_to_bbox(working_bbox)

        x_tolerance, y_tolerance = _expected_growth(width, height, rotation_deg + deskew_angle_deg)

        assert abs(recovered_bbox[0] - source_bbox[0]) <= x_tolerance + _EPSILON
        assert abs(recovered_bbox[2] - source_bbox[2]) <= x_tolerance + _EPSILON
        assert abs(recovered_bbox[1] - source_bbox[1]) <= y_tolerance + _EPSILON
        assert abs(recovered_bbox[3] - source_bbox[3]) <= y_tolerance + _EPSILON
        case_count += 1

    assert case_count == 400


def test_bbox_round_trip_with_zero_rotation_is_exact() -> None:
    """No rotation (structural or deskew) => pure scale+translate => the AABB
    round trip is exact, not just within a growth-derived tolerance."""
    record = PreprocessingRecord(
        render_dpi=150.0,
        deskew_angle_deg=0.0,
        crop=(3.0, 4.0, 500.0, 700.0),
        rotation_deg=0,
        pipeline_version="v1",
    )
    source_bbox = (10.0, 20.0, 110.0, 220.0)

    forward = record.to_transform()
    recovered = forward.inverse().apply_to_bbox(forward.apply_to_bbox(source_bbox))

    assert recovered == pytest.approx(source_bbox, abs=1e-9)
