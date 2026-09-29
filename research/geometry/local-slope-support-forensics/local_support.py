"""Research-only local pixel support measurements for baseline-slope events.

Only token coordinates are accepted by this module. OCR strings, confidence,
line IDs, fixture names, and prior event labels cannot affect its measurements
or decisions. Token boxes locate scan regions; measured support comes from
pixels in the source raster.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any, Iterable

import numpy as np
from PIL import Image


PIXEL_THRESHOLD = 120
PIXEL_BIN_WIDTH = 20
PIXEL_MARGIN = 2


@dataclass(frozen=True)
class Box:
    """Geometric token locator with no lexical or OCR-line authority."""

    source_row: int
    x: int
    y: int
    width: int
    height: int

    @property
    def x1(self) -> int:
        return self.x + self.width

    @property
    def y1(self) -> int:
        return self.y + self.height

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2


def boxes_from_records(records: Iterable[dict[str, Any]]) -> list[Box]:
    """Discard all OCR fields except source identity and rectangle geometry."""

    result = []
    for record in records:
        if "box_px" in record:
            x, y, width, height = record["box_px"]
            source_row = record["source_row"]
        else:
            source_row = record["source_row"]
            x, y, width, height = (record[name] for name in ("x", "y", "width", "height"))
        result.append(Box(int(source_row), int(x), int(y), int(width), int(height)))
    return result


def _theil_sen(points: list[tuple[float, float]]) -> float | None:
    slopes = [
        (y2 - y1) / (x2 - x1)
        for index, (x1, y1) in enumerate(points)
        for x2, y2 in points[index + 1 :]
        if x2 != x1
    ]
    return float(median(slopes)) if slopes else None


def _line_residuals(points: list[tuple[float, float]], slope: float) -> list[float]:
    intercept = float(median(y - slope * x for x, y in points))
    return [y - (slope * x + intercept) for x, y in points]


def _pixel_points(
    gray: np.ndarray,
    boxes: list[Box],
    *,
    x_window: tuple[int, int] | None = None,
    bin_width: int = PIXEL_BIN_WIDTH,
) -> list[dict[str, float | int]]:
    """Summarize ink inside geometric token ROIs, preserving x subregions.

    Looking only within each token's box plus a two-pixel locator margin keeps
    neighboring rows, borders, and diagram strokes from supplying support.
    The lower envelope and ink median are deliberately separate measurements:
    neither is silently treated as a true glyph baseline.
    """

    if not boxes:
        return []
    min_x = min(box.x for box in boxes)
    max_x = max(box.x1 for box in boxes)
    if x_window is not None:
        min_x = max(min_x, x_window[0])
        max_x = min(max_x, x_window[1])
    if max_x <= min_x:
        return []
    points: list[dict[str, float | int]] = []
    for left in range(min_x, max_x, bin_width):
        ys: list[np.ndarray] = []
        for box in boxes:
            x0 = max(left, box.x, 0)
            x1 = min(left + bin_width, box.x1, gray.shape[1])
            y0 = max(0, box.y - PIXEL_MARGIN)
            y1 = min(gray.shape[0], box.y1 + PIXEL_MARGIN)
            if x1 <= x0 or y1 <= y0:
                continue
            local_y = np.where(gray[y0:y1, x0:x1] < PIXEL_THRESHOLD)[0]
            if len(local_y):
                ys.append(local_y + y0)
        if not ys:
            continue
        samples = np.concatenate(ys)
        if len(samples) < 4:
            continue
        points.append({
            "x": float(left + min(bin_width, max_x - left) / 2),
            "lower_y": float(np.percentile(samples, 90)),
            "median_y": float(np.median(samples)),
            "upper_y": float(np.percentile(samples, 10)),
            "vertical_ink_span_px": float(np.percentile(samples, 90) - np.percentile(samples, 10)),
            "pixel_count": int(len(samples)),
        })
    return points


def _token_lower_points(gray: np.ndarray, boxes: list[Box]) -> list[dict[str, float | int]]:
    """Extract one robust ink lower-edge landmark inside each located token."""

    points = []
    for box in boxes:
        x0, x1 = max(0, box.x), min(gray.shape[1], box.x1)
        y0, y1 = max(0, box.y - PIXEL_MARGIN), min(gray.shape[0], box.y1 + PIXEL_MARGIN)
        if x1 <= x0 or y1 <= y0:
            continue
        ys = np.where(gray[y0:y1, x0:x1] < PIXEL_THRESHOLD)[0] + y0
        if len(ys) < 4:
            continue
        points.append({
            "source_row": box.source_row,
            "x": box.center_x,
            "lower_y": float(np.percentile(ys, 90)),
            "pixel_count": int(len(ys)),
        })
    # Stable serialization matters because downstream permutation tests
    # compare support records as well as their order-invariant fitted value.
    return sorted(points, key=lambda point: (point["x"], point["source_row"]))


def _fit_channel(points: list[dict[str, float | int]], field: str) -> dict[str, Any]:
    xy = [(float(point["x"]), float(point[field])) for point in points]
    slope = _theil_sen(xy)
    if slope is None:
        return {"slope_px_per_px": None, "support_bins": len(points)}
    residuals = [abs(value) for value in _line_residuals(xy, slope)]
    if len(xy) >= 3:
        xs = np.asarray([point[0] for point in xy], dtype=np.float64)
        ys = np.asarray([point[1] for point in xy], dtype=np.float64)
        quadratic = np.polyfit(xs, ys, 2)
        quadratic_residuals = ys - np.polyval(quadratic, xs)
        center_x = float((xs.min() + xs.max()) / 2)
        edge_x = float((xs.max() - xs.min()) / 2)
        curvature_departure = float(abs(quadratic[0]) * edge_x**2)
    else:
        quadratic_residuals = np.asarray([], dtype=np.float64)
        curvature_departure = None
    return {
        "slope_px_per_px": slope,
        "support_bins": len(points),
        "median_absolute_residual_px": float(median(residuals)),
        "maximum_absolute_residual_px": float(max(residuals)),
        "quadratic_median_absolute_residual_px": float(np.median(np.abs(quadratic_residuals))) if len(quadratic_residuals) else None,
        "quadratic_departure_at_half_span_px": curvature_departure,
    }


def measure_scope(
    gray: np.ndarray,
    boxes: list[Box],
    *,
    page_width: int,
    candidate_slope: float | None = None,
) -> dict[str, Any]:
    """Measure pixel and box geometry in a specified local support scope."""

    if not boxes:
        return {"token_count": 0, "status": "no_geometric_support"}
    x0, x1 = min(box.x for box in boxes), max(box.x1 for box in boxes)
    span = x1 - x0
    points = _pixel_points(gray, boxes)
    token_points = _token_lower_points(gray, boxes)
    lower = _fit_channel(points, "lower_y")
    ink_median = _fit_channel(points, "median_y")
    token_lower = _fit_channel(token_points, "lower_y")
    centers = [(box.center_x, box.center_y) for box in boxes]
    box_slope = _theil_sen(centers)
    if span and box_slope is not None and lower.get("slope_px_per_px") is not None:
        proxy_delta = (box_slope - lower["slope_px_per_px"]) * span
    else:
        proxy_delta = None

    bounds = [x0 + span * part / 3 for part in range(4)]
    subfits = []
    for index in range(3):
        segment = [p for p in points if bounds[index] <= p["x"] < bounds[index + 1] or (index == 2 and p["x"] == bounds[index + 1])]
        subfits.append(_fit_channel(segment, "lower_y"))
    supported_subfits = [fit["slope_px_per_px"] for fit in subfits if fit["slope_px_per_px"] is not None]
    if len(supported_subfits) >= 2 and span:
        subregion_spread_px = (max(supported_subfits) - min(supported_subfits)) * span
    else:
        subregion_spread_px = None

    leave_one_box_out = []
    for box in boxes:
        remaining = [other for other in boxes if other.source_row != box.source_row]
        fit = _fit_channel(_pixel_points(gray, remaining), "lower_y")
        if fit.get("slope_px_per_px") is not None:
            leave_one_box_out.append(float(fit["slope_px_per_px"]))
    leave_one_subregion_out = []
    for index in range(3):
        kept = [p for p in points if not bounds[index] <= p["x"] < bounds[index + 1]]
        fit = _fit_channel(kept, "lower_y")
        if fit.get("slope_px_per_px") is not None:
            leave_one_subregion_out.append(float(fit["slope_px_per_px"]))
    leave_one_token_landmark_out = []
    for source_row in {box.source_row for box in boxes}:
        kept = [point for point in token_points if point["source_row"] != source_row]
        fit = _fit_channel(kept, "lower_y")
        if fit.get("slope_px_per_px") is not None:
            leave_one_token_landmark_out.append(float(fit["slope_px_per_px"]))

    heights = [box.height for box in boxes]
    widths = [box.width for box in boxes]
    height_mean = float(np.mean(heights))
    height_std = float(np.std(heights))
    valid_slopes = [lower.get("slope_px_per_px"), ink_median.get("slope_px_per_px")]
    proxy_spread_px = (
        (max(valid_slopes) - min(valid_slopes)) * span
        if span and all(value is not None for value in valid_slopes)
        else None
    )
    vertical_spans = [float(point["vertical_ink_span_px"]) for point in points]
    return {
        "token_count": len(boxes),
        "distinct_x_positions": len({box.x for box in boxes}),
        "x_span_px": span,
        "page_width_px": page_width,
        "page_width_fraction": span / page_width if page_width else None,
        "pixel_bin_coverage_fraction": (len(points) * PIXEL_BIN_WIDTH / span) if span else None,
        "median_token_width_px": float(median(widths)),
        "median_token_height_px": float(median(heights)),
        "token_height_min_max_px": [min(heights), max(heights)],
        "token_height_coefficient_of_variation": height_std / height_mean if height_mean else None,
        "local_box_center_slope_px_per_px": box_slope,
        "pixel_lower_envelope_fit": lower,
        "pixel_ink_median_fit": ink_median,
        "per_token_pixel_lower_envelope_fit": token_lower,
        "per_token_pixel_lower_envelope_points": token_points,
        "median_within_bin_vertical_ink_span_px": float(median(vertical_spans)) if vertical_spans else None,
        "lower_vs_median_proxy_disagreement_px_over_span": proxy_spread_px,
        "box_vs_pixel_lower_disagreement_px_over_span": proxy_delta,
        "horizontal_subregion_fits": subfits,
        "subregion_slope_spread_px_over_span": subregion_spread_px,
        "leave_one_token_out_slope_range_px_per_px": [min(leave_one_box_out), max(leave_one_box_out)] if leave_one_box_out else None,
        "leave_one_token_landmark_out_slope_range_px_per_px": [min(leave_one_token_landmark_out), max(leave_one_token_landmark_out)] if leave_one_token_landmark_out else None,
        "leave_one_subregion_out_slope_range_px_per_px": [min(leave_one_subregion_out), max(leave_one_subregion_out)] if leave_one_subregion_out else None,
        "candidate_slope_px_per_px": candidate_slope,
        "local_pixel_minus_candidate_trend_px": (
            (lower["slope_px_per_px"] - candidate_slope) * span
            if candidate_slope is not None and lower.get("slope_px_per_px") is not None else None
        ),
        "pixel_measurement_contract": {
            "threshold_gray_below": PIXEL_THRESHOLD,
            "bin_width_px": PIXEL_BIN_WIDTH,
            "token_box_margin_px": PIXEL_MARGIN,
            "lower_envelope_quantile": 0.90,
            "pixel_source": "current production-cropped raster",
            "ocr_role": "box rectangles locate pixels only; no string/confidence/line id is read",
        },
        "pixel_points": points,
    }


def local_support_decision(measurement: dict[str, Any]) -> dict[str, Any]:
    """Apply the v2 label-blind local support rule.

    Each located token contributes one measured lower-ink landmark. At least
    three independent token regions are needed to fit a line. A robust fit
    must remain within four predicted pixels across the support when any one
    landmark is removed, and median residual must remain at most two pixels.
    These limits reflect 144-DPI sampling, not event outcomes. A stable trend
    below two pixels across its support does not demonstrate a need for slope.
    No page/class identifiers, OCR text, or learned parameters are used.
    """

    if measurement.get("status") == "no_geometric_support":
        return {"decision": "abstain", "reason": "no_geometric_support", "slope_px_per_px": None}
    lower = measurement["per_token_pixel_lower_envelope_fit"]
    span = measurement["x_span_px"]
    if measurement["token_count"] < 3 or lower.get("support_bins", 0) < 3:
        return {"decision": "abstain", "reason": "fewer_than_three_token_support_regions", "slope_px_per_px": None}
    if lower.get("slope_px_per_px") is None:
        return {"decision": "abstain", "reason": "insufficient_token_pixel_landmarks", "slope_px_per_px": None}
    residual = lower["median_absolute_residual_px"]
    if residual > 2.0:
        return {"decision": "abstain", "reason": "local_baseline_residual_exceeds_two_pixels", "slope_px_per_px": lower["slope_px_per_px"]}
    loo = measurement.get("leave_one_token_landmark_out_slope_range_px_per_px")
    if loo is None or len(loo) != 2 or (loo[1] - loo[0]) * span > 4.0:
        return {"decision": "abstain", "reason": "slope_not_stable_to_one_token_landmark_deletion", "slope_px_per_px": lower["slope_px_per_px"]}
    trend = abs(lower["slope_px_per_px"] * span)
    if trend < 2.0:
        return {"decision": "reject_slope", "reason": "supported_trend_below_two_pixels_over_local_span", "slope_px_per_px": 0.0}
    return {"decision": "apply_slope", "reason": "three_token_landmarks_support_a_stable_nonzero_local_trend", "slope_px_per_px": lower["slope_px_per_px"]}


def region_consistency_decision_v1(measurement: dict[str, Any]) -> dict[str, Any]:
    """Retained v1 rule, falsified by short/variable-height synthetic controls."""

    if measurement.get("status") == "no_geometric_support":
        return {"decision": "abstain", "reason": "no_geometric_support", "slope_px_per_px": None}
    lower = measurement["pixel_lower_envelope_fit"]
    span = measurement["x_span_px"]
    if measurement["token_count"] < 3:
        return {"decision": "abstain", "reason": "fewer_than_three_token_support_regions", "slope_px_per_px": None}
    if any(fit.get("slope_px_per_px") is None for fit in measurement["horizontal_subregion_fits"]):
        return {"decision": "abstain", "reason": "one_or_more_horizontal_thirds_lack_independent_pixel_fit", "slope_px_per_px": None}
    if lower.get("slope_px_per_px") is None:
        return {"decision": "abstain", "reason": "insufficient_pixel_bins", "slope_px_per_px": None}
    spread = measurement["subregion_slope_spread_px_over_span"]
    proxy = measurement["lower_vs_median_proxy_disagreement_px_over_span"]
    if spread is None or spread > 4.0:
        return {"decision": "abstain", "reason": "horizontal_subregions_disagree_by_more_than_four_pixels", "slope_px_per_px": lower["slope_px_per_px"]}
    if proxy is None or proxy > 4.0:
        return {"decision": "abstain", "reason": "independent_pixel_proxies_disagree_by_more_than_four_pixels", "slope_px_per_px": lower["slope_px_per_px"]}
    if lower["median_absolute_residual_px"] > 2.0:
        return {"decision": "abstain", "reason": "local_baseline_residual_exceeds_two_pixels", "slope_px_per_px": lower["slope_px_per_px"]}
    if abs(lower["slope_px_per_px"] * span) < 2.0:
        return {"decision": "reject_slope", "reason": "supported_trend_below_two_pixels_over_local_span", "slope_px_per_px": 0.0}
    return {"decision": "apply_slope", "reason": "three_subregions_and_pixel_proxies_support_a_stable_nonzero_local_trend", "slope_px_per_px": lower["slope_px_per_px"]}


def scope_boxes(
    *,
    all_boxes: list[Box],
    event_boxes: list[Box],
    scope: str,
) -> list[Box]:
    """Return geometry-located support boxes for one declared spatial scope."""

    if scope in {"event_only", "candidate_band"}:
        return list(event_boxes)
    if not event_boxes:
        return []
    event_x0, event_x1 = min(b.x for b in event_boxes), max(b.x1 for b in event_boxes)
    event_y0, event_y1 = min(b.y for b in event_boxes), max(b.y1 for b in event_boxes)
    unit = float(median([b.height for b in event_boxes]))
    if scope == "local_x_neighborhood":
        x0, x1 = event_x0 - unit, event_x1 + unit
        y0, y1 = event_y0 - unit / 2, event_y1 + unit / 2
    elif scope == "neighbor_rows":
        x0, x1 = event_x0 - unit, event_x1 + unit
        y0, y1 = event_y0 - 2 * unit, event_y1 + 2 * unit
    else:
        raise ValueError(f"unknown local scope: {scope}")
    return [
        box for box in all_boxes
        if box.x < x1 and box.x1 > x0 and box.center_y >= y0 and box.center_y <= y1
    ]
