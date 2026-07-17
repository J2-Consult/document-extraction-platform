"""Affine transform utilities: bbox mapping between working and source space.

Convention: a transform is the 6 floats `[a, b, c, d, e, f]` used by
`Provenance.transform_to_source` (matching the fixtures, and the PDF/SVG/HTML5
canvas convention):

    x' = a*x + c*y + e
    y' = b*x + d*y + f

`compose`/`inverse` are computed with exact matrix algebra (plain float
arithmetic — no numpy). Any floating-point slop from repeated multiplication
is a test concern (tolerance lives in the tests that round-trip a bbox), never
baked into these functions.

Pure Python: no I/O, no framework imports.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import cos, isfinite, radians, sin

TransformTuple = tuple[float, float, float, float, float, float]


@dataclass(frozen=True, slots=True)
class AffineTransform:
    """One affine transform. Construct directly, via `identity()`, or via
    `from_sequence()` for a `Provenance.transform_to_source`-shaped 6-tuple.
    """

    a: float
    b: float
    c: float
    d: float
    e: float
    f: float

    def __post_init__(self) -> None:
        if not all(isfinite(value) for value in (self.a, self.b, self.c, self.d, self.e, self.f)):
            raise ValueError("affine transform components must all be finite")

    @classmethod
    def identity(cls) -> AffineTransform:
        return cls(1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

    @classmethod
    def from_sequence(cls, values: Sequence[float]) -> AffineTransform:
        """Build from a `transform_to_source`-shaped sequence; raises
        `ValueError` (never a bare unpack error) when it isn't exactly 6
        values, so callers get one consistent failure mode."""
        if len(values) != 6:
            raise ValueError(f"affine transform requires exactly 6 components, got {len(values)}")
        a, b, c, d, e, f = values
        return cls(a, b, c, d, e, f)

    def as_tuple(self) -> TransformTuple:
        return (self.a, self.b, self.c, self.d, self.e, self.f)

    @property
    def determinant(self) -> float:
        return self.a * self.d - self.c * self.b

    def apply_to_point(self, x: float, y: float) -> tuple[float, float]:
        return (self.a * x + self.c * y + self.e, self.b * x + self.d * y + self.f)

    def apply_to_bbox(self, bbox: Sequence[float]) -> tuple[float, float, float, float]:
        """Map an axis-aligned bbox `[x0, y0, x1, y1]` through this transform.

        All 4 corners are mapped and the result is the enclosing axis-aligned
        box of the (possibly rotated) mapped shape — the only representation
        that stays a valid bbox once a transform has a rotation component.
        This is lossy under rotation by construction (the mapped shape's true
        outline is a rotated rectangle, not a box); round-trip tests account
        for that growth explicitly rather than papering over it here.
        """
        x0, y0, x1, y1 = bbox
        corners = [self.apply_to_point(x, y) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
        xs = [point[0] for point in corners]
        ys = [point[1] for point in corners]
        return (min(xs), min(ys), max(xs), max(ys))

    def compose(self, inner: AffineTransform) -> AffineTransform:
        """`outer.compose(inner)` applies `inner` first, then `outer`:

        outer.compose(inner).apply_to_point(x, y) == outer.apply_to_point(*inner.apply_to_point(x, y))
        """
        a1, b1, c1, d1, e1, f1 = inner.as_tuple()
        a2, b2, c2, d2, e2, f2 = self.as_tuple()
        return AffineTransform(
            a=a2 * a1 + c2 * b1,
            b=b2 * a1 + d2 * b1,
            c=a2 * c1 + c2 * d1,
            d=b2 * c1 + d2 * d1,
            e=a2 * e1 + c2 * f1 + e2,
            f=b2 * e1 + d2 * f1 + f2,
        )

    def inverse(self) -> AffineTransform:
        det = self.determinant
        if det == 0.0:
            raise ValueError("affine transform is not invertible (determinant is zero)")
        a, b, c, d, e, f = self.as_tuple()
        inv_det = 1.0 / det
        return AffineTransform(
            a=d * inv_det,
            b=-b * inv_det,
            c=-c * inv_det,
            d=a * inv_det,
            e=(c * f - d * e) * inv_det,
            f=(b * e - a * f) * inv_det,
        )


def rotation_transform(angle_deg: float) -> AffineTransform:
    """Pure rotation about the origin, counter-clockwise, by `angle_deg`."""
    theta = radians(angle_deg)
    cos_t, sin_t = cos(theta), sin(theta)
    return AffineTransform(cos_t, sin_t, -sin_t, cos_t, 0.0, 0.0)


def scale_transform(sx: float, sy: float | None = None) -> AffineTransform:
    """Uniform (`sy=None`) or independent x/y scale about the origin."""
    sy = sx if sy is None else sy
    if sx == 0 or sy == 0:
        raise ValueError("scale factors must be non-zero")
    return AffineTransform(sx, 0.0, 0.0, sy, 0.0, 0.0)


def translation_transform(tx: float, ty: float) -> AffineTransform:
    return AffineTransform(1.0, 0.0, 0.0, 1.0, tx, ty)


def is_well_formed_transform(values: Sequence[float]) -> bool:
    """True iff `values` is exactly 6 finite floats — the shape required of a
    `transform_to_source` 6-tuple. Never raises; used by the validator's
    transform-well-formed check to defend against artifacts assembled
    in-process (e.g. via `model_copy(update=...)`) that bypass Pydantic field
    validation.
    """
    if len(values) != 6:
        return False
    return all(isfinite(value) for value in values)
