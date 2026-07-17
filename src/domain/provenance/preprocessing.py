"""Preprocessing records: what happened to a page between the immutable
source PDF and the working artifact used for extraction — render DPI, deskew
angle, crop, structural rotation, pipeline version — and the affine transform
they compose into.

`to_transform()` produces the source-space -> working-space transform; a
provenance's `transform_to_source` is that transform's `.inverse()`.

Pure Python: no I/O, no framework imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from domain.provenance.geometry import RotationDegrees
from domain.provenance.transform import (
    AffineTransform,
    rotation_transform,
    scale_transform,
    translation_transform,
)

_SOURCE_DPI = 72.0  # PDF points are defined at 72 units per inch.

CropBox = tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class PreprocessingRecord:
    render_dpi: float
    deskew_angle_deg: float
    crop: CropBox | None
    rotation_deg: RotationDegrees
    pipeline_version: str

    def __post_init__(self) -> None:
        if self.render_dpi <= 0 or not isfinite(self.render_dpi):
            raise ValueError("render_dpi must be a finite positive number")
        if not isfinite(self.deskew_angle_deg):
            raise ValueError("deskew_angle_deg must be finite")
        if not self.pipeline_version:
            raise ValueError("pipeline_version must be non-empty")
        if self.crop is not None:
            self._validate_crop(self.crop)

    @staticmethod
    def _validate_crop(crop: CropBox) -> None:
        x0, y0, x1, y1 = crop
        if not all(isfinite(value) for value in crop):
            raise ValueError("crop bounds must be finite")
        if x1 <= x0 or y1 <= y0:
            raise ValueError("crop bounds must satisfy x1 > x0 and y1 > y0")

    def to_transform(self) -> AffineTransform:
        """Source space -> working space, composed in pipeline order: the
        page's structural rotation, then fine-grained deskew correction, then
        DPI scaling, then crop translation — each stage applied to the output
        of the previous one. The rotation *matrix* the epic calls for is
        exactly this method's rotation stage, derived from the stored degree
        values rather than duplicated as a separate raw field.
        """
        structural = rotation_transform(float(self.rotation_deg))
        deskewed = rotation_transform(self.deskew_angle_deg).compose(structural)
        scaled = scale_transform(self.render_dpi / _SOURCE_DPI).compose(deskewed)
        if self.crop is None:
            return scaled
        crop_x0, crop_y0, _, _ = self.crop
        return translation_transform(-crop_x0, -crop_y0).compose(scaled)
