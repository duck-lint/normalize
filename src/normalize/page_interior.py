"""Pixel-only proposals for loose-page interior bounds and rigid orientation.

This module measures acquisition geometry. It deliberately has no dependency on
OCR, canonical text, or downstream layout outcomes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
from PIL import Image


PAGE_INTERIOR_METHOD = "lab-paper-chroma-largest-component-v1"


@dataclass(frozen=True)
class PageInteriorObservation:
    """A reviewable page-surface measurement from one source raster."""

    status: str
    physical_boundary_polygon_px: tuple[tuple[float, float], ...] | None
    content_bounds: tuple[int, int, int, int] | None
    deskew_degrees_clockwise: float | None
    edges: dict[str, dict[str, Any]]
    failures: tuple[str, ...]
    uncertainty: dict[str, Any]
    method: str = PAGE_INTERIOR_METHOD

    def record(self, page_id: str) -> dict[str, Any]:
        """Serialize evidence without projecting it into a BookProfile."""
        return {
            "page_id": page_id,
            "status": self.status,
            "physical_boundary_polygon_px": (
                [list(point) for point in self.physical_boundary_polygon_px]
                if self.physical_boundary_polygon_px is not None else None
            ),
            "content_bounds": list(self.content_bounds) if self.content_bounds else None,
            "deskew_degrees_clockwise": self.deskew_degrees_clockwise,
            "edges": self.edges,
            "failures": list(self.failures),
            "uncertainty": self.uncertainty,
            "method": self.method,
        }


def _largest_component(mask: np.ndarray) -> tuple[np.ndarray | None, int, int]:
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    if count <= 1:
        return None, 0, 0
    areas = stats[1:, cv2.CC_STAT_AREA]
    first = 1 + int(np.argmax(areas))
    largest_area = int(stats[first, cv2.CC_STAT_AREA])
    second_area = int(np.max(np.delete(areas, first - 1))) if len(areas) > 1 else 0
    return (labels == first).astype(np.uint8), largest_area, second_area


def _mask_for_paper(lab: np.ndarray, background_b: float, threshold_delta: float) -> np.ndarray:
    """Use paper chroma relative to the observed scanner-bed border."""
    b_channel = lab[:, :, 2].astype(np.float32)
    mask = (b_channel > background_b + threshold_delta).astype(np.uint8)
    # Closing bridges small print/highlight holes while preserving the measured
    # outside contour. The kernel is in analysis pixels, not source pixels.
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))


def _corners(mask: np.ndarray) -> tuple[np.ndarray, tuple[float, float, float, float]]:
    points_y, points_x = np.where(mask != 0)
    if len(points_x) < 20:
        raise ValueError("paper component has too few boundary pixels")
    rectangle = cv2.minAreaRect(np.column_stack((points_x, points_y)).astype(np.float32))
    points = cv2.boxPoints(rectangle).astype(np.float32)
    center = points.mean(axis=0)
    angles = np.arctan2(points[:, 1] - center[1], points[:, 0] - center[0])
    ordered = points[np.argsort(angles)]
    return ordered, rectangle


def _side_measurements(
    polygon: np.ndarray,
    component: np.ndarray,
    b_channel: np.ndarray,
    l_channel: np.ndarray,
    *,
    scale_x: float,
    scale_y: float,
) -> tuple[dict[str, dict[str, Any]], list[float], list[float]]:
    height, width = component.shape
    center = polygon.mean(axis=0)
    side_rows: list[dict[str, Any]] = []
    fit_angles: list[float] = []
    fit_residuals: list[float] = []
    contour_result = cv2.findContours(component.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    contours = contour_result[-2]
    if not contours:
        return {}, [], []
    contour = max(contours, key=cv2.contourArea).reshape(-1, 2).astype(np.float32)

    for index in range(4):
        first, second = polygon[index], polygon[(index + 1) % 4]
        vector = second - first
        length = float(np.linalg.norm(vector))
        if length < 10:
            continue
        midpoint = (first + second) / 2
        inward = center - midpoint
        inward /= max(float(np.linalg.norm(inward)), 1e-6)
        # Name edges by their source-raster position, preserving the four-side
        # distinction even when one side is clipped by the raster.
        if abs(vector[0]) >= abs(vector[1]):
            name = "top" if midpoint[1] < center[1] else "bottom"
        else:
            name = "left" if midpoint[0] < center[0] else "right"

        parameters = np.linspace(0.08, 0.92, 40)
        samples = first[None, :] + parameters[:, None] * vector[None, :]
        # Sample beyond the transition band on both sides. Chroma contrast is
        # more stable here than a binary mask whose exact threshold defines its
        # own contour.
        inside_points = samples + inward[None, :] * 6.0
        outside_points = samples - inward[None, :] * 6.0
        valid = (
            (outside_points[:, 0] >= 0) & (outside_points[:, 0] < width)
            & (outside_points[:, 1] >= 0) & (outside_points[:, 1] < height)
            & (inside_points[:, 0] >= 0) & (inside_points[:, 0] < width)
            & (inside_points[:, 1] >= 0) & (inside_points[:, 1] < height)
        )
        valid_fraction = float(valid.mean())
        if valid_fraction < 0.55:
            side_rows.append({"edge": name, "status": "unobserved_raster_clip", "support": valid_fraction})
            continue

        inside_indices = np.rint(inside_points[valid]).astype(int)
        outside_indices = np.rint(outside_points[valid]).astype(int)
        inside_chroma = b_channel[inside_indices[:, 1], inside_indices[:, 0]]
        outside_chroma = b_channel[outside_indices[:, 1], outside_indices[:, 0]]
        inside_lightness = l_channel[inside_indices[:, 1], inside_indices[:, 0]]
        outside_lightness = l_channel[outside_indices[:, 1], outside_indices[:, 0]]
        # Paper can be darker than a white bed or much lighter than a black
        # bed. Support therefore comes from a measurable two-sided Lab change,
        # not from assuming one background polarity.
        contrast = np.sqrt(
            (inside_lightness - outside_lightness) ** 2
            + (inside_chroma - outside_chroma) ** 2
        )
        support = float(np.mean(contrast >= 2.0))

        # Fit observed contour points close to this side. This gives independent
        # edge-angle evidence rather than reusing the rectangle angle itself.
        relative = contour - first
        along = relative @ vector / (length * length)
        distance = np.abs(relative[:, 0] * vector[1] - relative[:, 1] * vector[0]) / length
        selected = contour[(along >= 0.04) & (along <= 0.96) & (distance <= 3.0)]
        angle = None
        residual = None
        if len(selected) >= 20:
            line = cv2.fitLine(selected.reshape(-1, 1, 2), cv2.DIST_L1, 0, 0.01, 0.01).reshape(-1)
            vx, vy = float(line[0]), float(line[1])
            if abs(vx) >= abs(vy):
                if vx < 0:
                    vx, vy = -vx, -vy
                page_angle = math.degrees(math.atan2(vy, vx))
            else:
                if vy < 0:
                    vx, vy = -vx, -vy
                page_angle = -math.degrees(math.atan2(vx, vy))
            angle = -page_angle  # BookProfile stores clockwise correction.
            distances = np.abs((selected[:, 0] - line[2]) * vy - (selected[:, 1] - line[3]) * vx)
            residual = float(np.median(distances) * (scale_x + scale_y) / 2)
            fit_angles.append(angle)
            fit_residuals.append(residual)

        edge_status = "supported" if support >= 0.65 else "weak_boundary_contrast"
        side_rows.append({
            "edge": name,
            "status": edge_status,
            "support": round(support, 3),
            "orientation_correction_clockwise_degrees": round(angle, 3) if angle is not None else None,
            "median_fit_residual_px": round(residual, 2) if residual is not None else None,
            "valid_outside_samples_fraction": round(valid_fraction, 3),
        })

    # There can be duplicate side names only if the candidate is badly shaped;
    # retain the strongest observed estimate for each physical side.
    edges: dict[str, dict[str, Any]] = {}
    for row in side_rows:
        name = row["edge"]
        previous = edges.get(name)
        if previous is None or row.get("support", 0) > previous.get("support", 0):
            edges[name] = {key: value for key, value in row.items() if key != "edge"}
    return edges, fit_angles, fit_residuals


def _interior_bounds_from_polygon(
    polygon: np.ndarray,
    image_width: int,
    image_height: int,
    scale_x: float,
    scale_y: float,
    edges: dict[str, dict[str, Any]],
) -> tuple[int, int, int, int] | None:
    """Build a conservative axis-aligned rectangle contained by the fitted page.

    The inset comes from the fitted page rotation and one analysis pixel of
    boundary localization uncertainty. Raster-clipped sides keep coordinate 0
    (or the image maximum), since no scanner-bed pixels exist past that edge.
    """
    x_min, y_min = polygon.min(axis=0)
    x_max, y_max = polygon.max(axis=0)
    width_px = (x_max - x_min) * scale_x
    height_px = (y_max - y_min) * scale_y
    horizontal_angles = [
        abs(float(row["orientation_correction_clockwise_degrees"]))
        for row in edges.values() if row.get("orientation_correction_clockwise_degrees") is not None
    ]
    angle = math.radians(max(horizontal_angles, default=0.0))
    # Inscribing an axis-aligned box in a rotated rectangle requires these
    # geometry-derived corner clearances; the extra source pixel reflects the
    # resolution of the measured edge mask.
    inset_x = abs(math.tan(angle)) * height_px / 2 + scale_x
    inset_y = abs(math.tan(angle)) * width_px / 2 + scale_y
    left = max(0, math.ceil(x_min * scale_x + inset_x))
    right = min(image_width, math.floor(x_max * scale_x - inset_x))
    top = max(0, math.ceil(y_min * scale_y + inset_y))
    bottom = min(image_height, math.floor(y_max * scale_y - inset_y))

    # Do not move an unobserved raster-clipped edge inward: the raster itself
    # already excludes any scanner-bed context on that side.
    if edges.get("left", {}).get("status") == "unobserved_raster_clip":
        left = 0
    if edges.get("top", {}).get("status") == "unobserved_raster_clip":
        top = 0
    if edges.get("right", {}).get("status") == "unobserved_raster_clip":
        right = image_width
    if edges.get("bottom", {}).get("status") == "unobserved_raster_clip":
        bottom = image_height
    if left < 0 or top < 0 or right > image_width or bottom > image_height or right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def _deskew_from_rectangle(polygon: np.ndarray) -> float:
    """Return clockwise correction from the fitted physical page frame."""
    horizontal_angles: list[float] = []
    for index in range(4):
        first = polygon[index]
        second = polygon[(index + 1) % 4]
        dx, dy = float(second[0] - first[0]), float(second[1] - first[1])
        if abs(dx) >= abs(dy):
            if dx < 0:
                dx, dy = -dx, -dy
            horizontal_angles.append(math.degrees(math.atan2(dy, dx)))
    if not horizontal_angles:
        return 0.0
    page_angle = float(np.median(horizontal_angles))
    return -page_angle


def measure_page_interior(image: Image.Image, *, page_id: str = "page") -> PageInteriorObservation:
    """Propose page-interior bounds and rigid deskew from source pixels alone.

    The detector compares the raster-border Lab ``b`` chroma with page
    chroma, forms the largest contiguous paper-like component, and fits its
    rectangular outline. The more conservative of two noise-derived paper
    masks supplies the page-interior proposal. If paper and bed are not
    distinguishable or the geometry is not page-like, bounds remain unresolved.
    """
    if not isinstance(image, Image.Image):
        raise TypeError("image must be a Pillow Image")
    source = image.convert("RGB")
    image_width, image_height = source.size
    if image_width < 100 or image_height < 100:
        return PageInteriorObservation(
            "unresolved", None, None, None, {}, ("background_indistinguishable",),
            {"reason": "source raster is too small for page-boundary measurement"},
        )

    # Analyze at a bounded resolution: the 3-pixel mask operation corresponds
    # to a few source pixels even for large scans and limits full-book runtime.
    target_long_side = 1400
    scale = min(1.0, target_long_side / max(image_width, image_height))
    analysis_width = max(1, round(image_width * scale))
    analysis_height = max(1, round(image_height * scale))
    scale_x, scale_y = image_width / analysis_width, image_height / analysis_height
    raster = cv2.cvtColor(np.asarray(source), cv2.COLOR_RGB2BGR)
    small = cv2.resize(raster, (analysis_width, analysis_height), interpolation=cv2.INTER_AREA)
    lab = cv2.cvtColor(small, cv2.COLOR_BGR2LAB)
    b_channel = lab[:, :, 2].astype(np.float32)
    rim_width = max(3, round(min(analysis_width, analysis_height) * 0.015))
    rim = np.concatenate((
        b_channel[:rim_width, :].ravel(), b_channel[-rim_width:, :].ravel(),
        b_channel[:, :rim_width].ravel(), b_channel[:, -rim_width:].ravel(),
    ))
    background_b = float(np.median(rim))
    background_mad = float(np.median(np.abs(rim - background_b)))
    threshold_delta = max(1.0, 3.0 * 1.4826 * background_mad)

    outer_mask, outer_area, second_area = _largest_component(_mask_for_paper(lab, background_b, threshold_delta))
    if outer_mask is None:
        return PageInteriorObservation(
            "unresolved", None, None, None, {}, ("background_indistinguishable",),
            {"background_b_median": background_b, "background_b_mad": background_mad,
             "threshold_delta": threshold_delta, "reason": "no contiguous paper-like component"},
        )
    inner_mask, inner_area, _ = _largest_component(_mask_for_paper(lab, background_b, threshold_delta + 0.5))
    image_area = analysis_width * analysis_height
    outer_fraction = outer_area / image_area
    if inner_mask is None or inner_area < outer_area * 0.55:
        return PageInteriorObservation(
            "unresolved", None, None, None, {}, ("multiple_edge_candidates",),
            {"background_b_median": background_b, "background_b_mad": background_mad,
             "threshold_delta": threshold_delta, "outer_component_fraction": outer_fraction,
             "inner_component_fraction": inner_area / image_area if inner_mask is not None else 0,
             "reason": "paper component is unstable across the measured chroma transition"},
        )

    physical_polygon, _ = _corners(outer_mask)
    interior_polygon, rectangle = _corners(inner_mask)
    corners_source = physical_polygon * np.array([scale_x, scale_y], dtype=np.float32)
    rect_width, rect_height = rectangle[1]
    short_side, long_side = sorted((float(rect_width), float(rect_height)))
    aspect = short_side / max(long_side, 1e-6)
    rect_fraction = (rect_width * rect_height) / image_area
    if outer_fraction < 0.12 or outer_fraction > 0.88 or aspect < 0.35 or rect_fraction < 0.15:
        failure = "page_edge_not_visible" if outer_fraction > 0.88 else "multiple_edge_candidates"
        return PageInteriorObservation(
            "unresolved", tuple(map(tuple, corners_source.tolist())), None, None, {},
            (failure,),
            {"background_b_median": background_b, "background_b_mad": background_mad,
             "threshold_delta": threshold_delta, "outer_component_fraction": outer_fraction,
             "rectangular_aspect_ratio": aspect, "reason": "dominant component is not a defensible single-page shape"},
        )

    edges, edge_angles, edge_residuals = _side_measurements(
        physical_polygon, outer_mask, b_channel, lab[:, :, 0].astype(np.float32),
        scale_x=scale_x, scale_y=scale_y,
    )
    bounds = _interior_bounds_from_polygon(
        interior_polygon, image_width, image_height, scale_x, scale_y, edges,
    )
    failures: list[str] = []
    for name in ("top", "bottom", "left", "right"):
        row = edges.get(name)
        if row is None or row["status"] == "unobserved_raster_clip":
            failures.append("page_edge_not_visible")
        elif row["status"] != "supported":
            failures.append("background_indistinguishable")
    # The rectangle fit pools the visible page contour, while separate line
    # fits provide an independent consistency check where enough edge points
    # are available.
    angle_spread = max(edge_angles) - min(edge_angles) if len(edge_angles) >= 2 else None
    supported_edges = sum(row.get("status") == "supported" for row in edges.values())
    if supported_edges < 2 or (angle_spread is not None and angle_spread > 0.60):
        deskew = None
        failures.append("orientation_unresolved")
    else:
        deskew = _deskew_from_rectangle(physical_polygon)
        if len(edge_angles) >= 2 and angle_spread is not None:
            edge_fit_correction = float(np.median(edge_angles))
            if abs(edge_fit_correction - deskew) > 0.60:
                deskew = None
                failures.append("orientation_unresolved")
        if deskew is not None and abs(deskew) < 0.08:
            deskew = 0.0
    if bounds is None:
        failures.append("multiple_edge_candidates")
    if len(failures) == 0:
        status = "measured"
    elif bounds is not None:
        status = "partial"
    else:
        status = "unresolved"

    page_b = b_channel[inner_mask != 0]
    uncertainty = {
        "background_b_median": round(background_b, 3),
        "background_b_mad": round(background_mad, 3),
        "paper_background_b_difference": round(float(np.median(page_b) - background_b), 3) if len(page_b) else None,
        "threshold_delta": round(threshold_delta, 3),
        "component_area_fraction": round(outer_fraction, 4),
        "rectangular_aspect_ratio": round(aspect, 4),
        "edge_orientation_estimates_clockwise_degrees": [round(value, 3) for value in edge_angles],
        "edge_orientation_spread_degrees": round(angle_spread, 3) if angle_spread is not None else None,
        "median_boundary_fit_residual_px": round(float(np.median(edge_residuals)), 2) if edge_residuals else None,
        "analysis_scale_px_per_source_px": round(1 / max(scale_x, scale_y), 4),
    }
    return PageInteriorObservation(
        status=status,
        physical_boundary_polygon_px=tuple((round(float(x), 2), round(float(y), 2)) for x, y in corners_source),
        content_bounds=bounds,
        deskew_degrees_clockwise=round(deskew, 3) if deskew is not None else None,
        edges=edges,
        failures=tuple(sorted(set(failures))),
        uncertainty=uncertainty,
    )
