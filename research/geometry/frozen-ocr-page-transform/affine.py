"""Pillow-compatible page-coordinate transforms for frozen OCR boxes.

Pillow samples a destination raster by inverse mapping.  This module records
the equivalent source-to-destination transform so one frozen set of source
observations can be moved into that destination coordinate frame.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class PageAffine:
    source_width: int
    source_height: int
    angle_degrees: float
    source_center: tuple[float, float]
    rotation: tuple[tuple[float, float], tuple[float, float]]
    expansion_translation: tuple[float, float]
    destination_width: int
    destination_height: int
    matrix: tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]

    def apply(self, point: tuple[float, float]) -> tuple[float, float]:
        x, y = point
        a, b, c = self.matrix[0]
        d, e, f = self.matrix[1]
        return a * x + b * y + c, d * x + e * y + f

    def invert(self, point: tuple[float, float]) -> tuple[float, float]:
        x, y = point
        a, b, c = self.matrix[0]
        d, e, f = self.matrix[1]
        determinant = a * e - b * d
        x -= c
        y -= f
        return (e * x - b * y) / determinant, (-d * x + a * y) / determinant


def make_page_affine(width: int, height: int, angle_degrees: float) -> PageAffine:
    """Match ``PIL.Image.rotate(angle, expand=True)`` geometry and sign.

    Pillow rounds sine/cosine to 15 decimal places before building the inverse
    sampling matrix. Its positive angle is counterclockwise. In pixel
    coordinates (y downward), the equivalent forward matrix is
    ``[[cos, sin], [-sin, cos]]``. Expansion uses the ceiling/floor of the
    transformed source edge corners, then centers the rotated frame in that
    integer-sized canvas.
    """

    if width <= 0 or height <= 0:
        raise ValueError("source dimensions must be positive")
    radians = math.radians(angle_degrees)
    cosine = round(math.cos(radians), 15)
    sine = round(math.sin(radians), 15)
    rotation = ((cosine, sine), (-sine, cosine))
    corners = ((0.0, 0.0), (float(width), 0.0), (float(width), float(height)), (0.0, float(height)))
    center = (width / 2.0, height / 2.0)

    def centered_rotate(point: tuple[float, float]) -> tuple[float, float]:
        x, y = point[0] - center[0], point[1] - center[1]
        return cosine * x + sine * y + center[0], -sine * x + cosine * y + center[1]

    rotated_corners = [centered_rotate(point) for point in corners]
    min_x = math.floor(min(point[0] for point in rotated_corners))
    max_x = math.ceil(max(point[0] for point in rotated_corners))
    min_y = math.floor(min(point[1] for point in rotated_corners))
    max_y = math.ceil(max(point[1] for point in rotated_corners))
    destination_width = max_x - min_x
    destination_height = max_y - min_y

    # This is the forward equivalent of Pillow's inverse-matrix canvas
    # recentering. For right-angle-near-zero rotations it preserves the same
    # integer output dimensions used by Pillow's expand implementation.
    translation = ((destination_width - width) / 2.0, (destination_height - height) / 2.0)
    tx = center[0] - cosine * center[0] - sine * center[1] + translation[0]
    ty = center[1] + sine * center[0] - cosine * center[1] + translation[1]
    matrix = (
        (cosine, sine, tx),
        (-sine, cosine, ty),
        (0.0, 0.0, 1.0),
    )
    return PageAffine(
        width,
        height,
        float(angle_degrees),
        center,
        rotation,
        translation,
        destination_width,
        destination_height,
        matrix,
    )


def transform_box_envelope(
    affine: PageAffine, box: tuple[int, int, int, int]
) -> tuple[int, int, int, int]:
    """Rotate all four box corners, then floor minima / ceil maxima."""

    x, y, width, height = box
    corners = (
        (float(x), float(y)),
        (float(x + width), float(y)),
        (float(x + width), float(y + height)),
        (float(x), float(y + height)),
    )
    mapped = [affine.apply(point) for point in corners]
    x0 = math.floor(min(point[0] for point in mapped))
    y0 = math.floor(min(point[1] for point in mapped))
    x1 = math.ceil(max(point[0] for point in mapped))
    y1 = math.ceil(max(point[1] for point in mapped))
    return x0, y0, x1 - x0, y1 - y0


def transform_points(
    affine: PageAffine, points: Iterable[tuple[float, float]]
) -> list[tuple[float, float]]:
    return [affine.apply(point) for point in points]
