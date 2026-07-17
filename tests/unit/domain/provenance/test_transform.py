"""`domain.provenance.transform`: affine transform algebra.

Every branch in `transform.py` is exercised at least once in each direction
(see the per-function comments below) — these are small, load-bearing
functions (E06 epic: "100% branch-covered") and there is no coverage tool in
this project's dependency set (adding `pytest-cov` would violate the "no new
dependencies" rule), so branch coverage is proven by exhaustive test cases
instead of a coverage run.
"""

from __future__ import annotations

import math

import pytest

from domain.provenance.transform import (
    AffineTransform,
    is_well_formed_transform,
    rotation_transform,
    scale_transform,
    translation_transform,
)

# --- AffineTransform.__post_init__: finite (pass) / non-finite (raise) ------


def test_transform_with_all_finite_components_constructs() -> None:
    transform = AffineTransform(1.0, 0.0, 0.0, 1.0, 5.0, -3.0)
    assert transform.as_tuple() == (1.0, 0.0, 0.0, 1.0, 5.0, -3.0)


@pytest.mark.parametrize("bad_value", [math.nan, math.inf, -math.inf])
@pytest.mark.parametrize("position", range(6))
def test_transform_with_a_non_finite_component_is_rejected(bad_value: float, position: int) -> None:
    components = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
    components[position] = bad_value
    with pytest.raises(ValueError, match="finite"):
        AffineTransform(*components)


# --- AffineTransform.from_sequence: length == 6 (pass) / != 6 (raise) ------


def test_from_sequence_with_exactly_six_values_constructs() -> None:
    transform = AffineTransform.from_sequence([1, 0, 0, 1, 0, 0])
    assert transform == AffineTransform.identity()


@pytest.mark.parametrize("values", [[], [1, 0, 0, 1, 0], [1, 0, 0, 1, 0, 0, 0]])
def test_from_sequence_with_wrong_length_is_rejected(values: list[float]) -> None:
    with pytest.raises(ValueError, match="exactly 6"):
        AffineTransform.from_sequence(values)


# --- identity / apply_to_point --------------------------------------------


def test_identity_leaves_points_unchanged() -> None:
    identity = AffineTransform.identity()
    assert identity.apply_to_point(12.5, -7.0) == (12.5, -7.0)


def test_translation_shifts_points() -> None:
    translate = translation_transform(10.0, -4.0)
    assert translate.apply_to_point(1.0, 1.0) == (11.0, -3.0)


def test_scale_scales_points() -> None:
    scale = scale_transform(2.0, 3.0)
    assert scale.apply_to_point(4.0, 5.0) == (8.0, 15.0)


def test_rotation_by_90_degrees_maps_x_axis_onto_y_axis() -> None:
    rotate = rotation_transform(90.0)
    x, y = rotate.apply_to_point(1.0, 0.0)
    assert x == pytest.approx(0.0, abs=1e-9)
    assert y == pytest.approx(1.0, abs=1e-9)


# --- apply_to_bbox: axis-aligned (no growth) vs rotated (AABB growth) ------


def test_apply_to_bbox_under_pure_translation_preserves_dimensions() -> None:
    translate = translation_transform(5.0, -2.0)
    bbox = translate.apply_to_bbox((0.0, 0.0, 10.0, 20.0))
    assert bbox == pytest.approx((5.0, -2.0, 15.0, 18.0))


def test_apply_to_bbox_under_45_degree_rotation_grows_to_the_known_aabb() -> None:
    # A unit square rotated 45 degrees has an AABB of side sqrt(2), centered
    # on the rotated center (rotation is about the origin, so the square
    # [0,0,1,1]'s center (0.5, 0.5) rotates too).
    rotate = rotation_transform(45.0)
    x0, y0, x1, y1 = rotate.apply_to_bbox((0.0, 0.0, 1.0, 1.0))
    assert (x1 - x0) == pytest.approx(math.sqrt(2), abs=1e-9)
    assert (y1 - y0) == pytest.approx(math.sqrt(2), abs=1e-9)


# --- compose: outer.compose(inner) applies inner first, then outer --------


def test_compose_matches_sequential_point_application() -> None:
    outer = rotation_transform(30.0)
    inner = translation_transform(3.0, -1.0)
    composed = outer.compose(inner)

    expected = outer.apply_to_point(*inner.apply_to_point(2.0, 7.0))
    actual = composed.apply_to_point(2.0, 7.0)

    assert actual == pytest.approx(expected, abs=1e-12)


def test_compose_of_two_rotations_adds_the_angles() -> None:
    composed = rotation_transform(20.0).compose(rotation_transform(25.0))
    expected = rotation_transform(45.0)
    assert composed.as_tuple() == pytest.approx(expected.as_tuple(), abs=1e-12)


# --- inverse: determinant != 0 (pass) / == 0 (raise) ------------------------


def test_inverse_undoes_a_composed_transform() -> None:
    transform = translation_transform(4.0, -9.0).compose(scale_transform(2.0).compose(rotation_transform(37.0)))
    inverse = transform.inverse()

    recovered = inverse.apply_to_point(*transform.apply_to_point(11.0, -6.0))

    assert recovered == pytest.approx((11.0, -6.0), abs=1e-9)


def test_inverse_of_identity_is_identity() -> None:
    assert AffineTransform.identity().inverse() == AffineTransform.identity()


def test_inverse_of_a_singular_transform_is_rejected() -> None:
    singular = AffineTransform(0.0, 0.0, 0.0, 0.0, 1.0, 1.0)
    assert singular.determinant == 0.0
    with pytest.raises(ValueError, match="not invertible"):
        singular.inverse()


# --- scale_transform: sy default (None) vs explicit; zero-factor branches --


def test_scale_transform_defaults_sy_to_sx_when_omitted() -> None:
    assert scale_transform(3.0) == AffineTransform(3.0, 0.0, 0.0, 3.0, 0.0, 0.0)


def test_scale_transform_accepts_independent_sy() -> None:
    assert scale_transform(3.0, 5.0) == AffineTransform(3.0, 0.0, 0.0, 5.0, 0.0, 0.0)


def test_scale_transform_rejects_zero_sx() -> None:
    with pytest.raises(ValueError, match="non-zero"):
        scale_transform(0.0, 1.0)


def test_scale_transform_rejects_zero_sy() -> None:
    with pytest.raises(ValueError, match="non-zero"):
        scale_transform(1.0, 0.0)


def test_scale_transform_accepts_both_non_zero() -> None:
    scale_transform(1.0, 1.0)  # does not raise


# --- is_well_formed_transform: length branch, finiteness branch -----------


def test_is_well_formed_transform_accepts_six_finite_floats() -> None:
    assert is_well_formed_transform([1.0, 0.0, 0.0, 1.0, 0.0, 0.0]) is True


def test_is_well_formed_transform_rejects_wrong_length() -> None:
    assert is_well_formed_transform([1.0, 0.0, 0.0, 1.0, 0.0]) is False


def test_is_well_formed_transform_rejects_a_non_finite_component() -> None:
    assert is_well_formed_transform([1.0, 0.0, 0.0, 1.0, 0.0, math.nan]) is False
    assert is_well_formed_transform([1.0, 0.0, 0.0, 1.0, 0.0, math.inf]) is False
