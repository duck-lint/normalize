"""Research-only pixel slope evidence and isolated estimator experiments."""

from __future__ import annotations

import json
import math
import random
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

import normalize.geometry as production_geometry
from normalize.geometry import _Token, group_physical_lines


# OCR hierarchy coordinates only locate candidate rows for visual review. They
# do not decide whether a row is physically continuous; that is adjudicated
# against the scan and the pixel fit below.
ROW_LOCATORS: dict[tuple[str, str], list[list[int]]] = {
    ("relativity_pdf10_pp26-27", "left"): [[21,22,23,24,25,26,27,28,29,30],[91,92,93,94,95,96,97,98,99,100,101],[176,177,178,179,180,181,182,183,184,185,186]],
    ("relativity_pdf10_pp26-27", "right"): [[32,33,34,35,36,37,38,39,40],[161,162,163,164,165,166,167],[258,259,260,261,262,263,264,265,266,267,268]],
    ("relativity_pdf17_pp40-41", "left"): [[16,17,18,19,20,21,22,23,24],[46,47,48,49,50,51,52,53,54,55],[148,149,150,151,152,153,154,155,156,157,158,159]],
    ("relativity_pdf17_pp40-41", "right"): [[15,16,17,18,19,20,21,22,23,24],[191,192,193,194,195,196,197,198,199,200,201,202],[316,317,318,319,320,321,322,323,324,325]],
    ("relativity_pdf23_pp52-53", "left"): [[21,22,23,24,25,26,27,28,29,30,31,32],[100,101,102,103,104,105,106,107,108,109,110,111,112,113],[176,177,178,179,180,181]],
    ("relativity_pdf23_pp52-53", "right"): [[19,20,21,22,23,24,25,26,27,28],[149,150,151,152,153,154,155,156,157,158,159],[274,275,276,277,278,279,280,281,282,283,284,285,286]],
    ("stella_maris_pdf03_session-I", "right"): [[11,12,13,14,15,16,17,18],[70,71,72,73,74,75],[152,153,154,155,156,157,158,159,160,161,162,163]],
    ("stella_maris_pdf06_dense-dialogue", "left"): [[63,64,65,66,67,68,69,70,71,72],[198,199,200,201,202,203,204,205,206,207,208],[297,298,299,300,301,302,303,304,305,306,307]],
    ("stella_maris_pdf06_dense-dialogue", "right"): [[41,42,43,44,45,46,47,48,49,50,51,52,53,54,55],[162,163,164,165,166,167,168,169,170,171,172,173,174,175,176,177,178],[308,309,310,311,312,313,314,315,316,317,318,319,320,321]],
    ("stella_maris_pdf18_session-II_p35", "left"): [[26,27,28,29,30],[55,56,57,58,59,60,61],[81,82,83,84,85,86,87,88,89,90,91]],
    ("stella_maris_pdf18_session-II_p35", "right"): [[33,34,35,36,37,38,39,40,41],[85,86,87,88,89,90,91,92,93,94,95],[148,149,150,151,152,153,154,155,156]],
}

# A few separately adjudicated display headings test whether page furniture's
# physical orientation agrees with sampled prose. These are evidence rows, not
# extra estimator inputs for the real-page candidate comparison.
AUXILIARY_ROW_LOCATORS: dict[tuple[str, str], list[list[int]]] = {
    ("relativity_pdf10_pp26-27", "left"): [[14, 15, 16, 17]],
    ("relativity_pdf17_pp40-41", "left"): [[9, 10, 11, 12]],
    ("relativity_pdf23_pp52-53", "left"): [[9, 10, 11, 12]],
}


def _projection_score(ys: np.ndarray, xs: np.ndarray, slope: float) -> int:
    corrected = np.rint(ys - slope * xs).astype(np.int32)
    corrected -= corrected.min()
    profile = np.bincount(corrected)
    return int(profile @ profile)


def pixel_projection_slope(
    image_path: Path,
    *,
    threshold: int = 120,
    grid_step: float = 0.00025,
    slope_limit: float = 0.06,
) -> dict[str, Any]:
    """Estimate whole-page orientation from dark-pixel row concentration.

    The fixed proportional crop excludes page furniture/margins. No OCR text,
    boxes, or hierarchy IDs enter this measurement. Threshold/grid sensitivity
    is recorded by the caller rather than hidden in a confidence label.
    """

    image = np.asarray(Image.open(image_path).convert("L"))
    height, width = image.shape
    y0, y1 = int(0.10 * height), int(0.94 * height)
    x0, x1 = int(0.07 * width), int(0.94 * width)
    ys, xs = np.where(image[y0:y1, x0:x1] < threshold)
    ys = ys.astype(np.float64) + y0
    xs = xs.astype(np.float64) + x0
    if not len(xs):
        return {"slope": None, "support_pixels": 0, "reason": "no_dark_pixels"}
    count = round(2 * slope_limit / grid_step)
    slopes = np.linspace(-slope_limit, slope_limit, count + 1)
    scores = [_projection_score(ys, xs, float(slope)) for slope in slopes]
    index = int(np.argmax(scores))
    ordered = sorted(scores, reverse=True)
    return {
        "slope": float(slopes[index]),
        "threshold": threshold,
        "grid_step": grid_step,
        "support_pixels": len(xs),
        "score": scores[index],
        "zero_score": scores[len(scores) // 2],
        "score_gain_over_zero": scores[index] - scores[len(scores) // 2],
        "runner_up_score": ordered[1] if len(ordered) > 1 else scores[index],
        "dimensions_px": [width, height],
        "measurement": "maximum squared horizontal-shear-adjusted dark-pixel row profile",
    }


def corrected_ink_run_count(image_path: Path, slope: float, threshold: int = 120) -> int:
    """Count nonempty corrected-y runs as a crude independent row-support check."""

    image = np.asarray(Image.open(image_path).convert("L"))
    height, width = image.shape
    y0, y1 = int(0.10 * height), int(0.94 * height)
    x0, x1 = int(0.07 * width), int(0.94 * width)
    ys, xs = np.where(image[y0:y1, x0:x1] < threshold)
    if not len(xs):
        return 0
    corrected = np.rint((ys + y0) - slope * (xs + x0)).astype(np.int32)
    profile = np.zeros(corrected.max() - corrected.min() + 1, dtype=np.bool_)
    profile[corrected - corrected.min()] = True
    # One empty row can occur from raster quantization; bridge it because a
    # one-pixel gap is not evidence for two independently supported rows.
    for index in range(1, len(profile) - 1):
        if profile[index - 1] and profile[index + 1]:
            profile[index] = True
    padded = np.pad(profile.astype(np.int8), (1, 1))
    starts = np.flatnonzero(np.diff(padded) == 1)
    return len(starts)


def pixel_row_fit(
    image_path: Path,
    tokens: list[_Token],
    source_rows: list[int],
    page_slope: float,
    *,
    threshold: int = 120,
    bin_width: int = 25,
) -> dict[str, Any]:
    """Fit pixel lower-envelope trend across a visually adjudicated row ROI."""

    selected = [token for token in tokens if token.source_row in set(source_rows)]
    if not selected:
        raise ValueError(f"row locator source identities not found: {source_rows}")
    x0 = min(token.x for token in selected)
    x1 = max(token.x1 for token in selected)
    # Source rows define only a search window. The fitted y values below come
    # exclusively from dark pixels in the current production raster.
    adjusted_centers = [token.center_y - page_slope * token.x for token in selected]
    center = float(median(adjusted_centers))
    image = np.asarray(Image.open(image_path).convert("L"))
    ys, xs = np.where(image[:, x0:x1] < threshold)
    xs = xs + x0
    mask = np.abs(ys - page_slope * xs - center) < 7
    ys, xs = ys[mask].astype(np.float64), xs[mask].astype(np.float64)
    points: list[tuple[float, float]] = []
    for left in range(x0, x1, bin_width):
        in_bin = (xs >= left) & (xs < min(left + bin_width, x1))
        if int(in_bin.sum()) >= 3:
            # The 95th percentile follows the lower ink envelope while reducing
            # sensitivity to a single descender or paper speck.
            points.append((float(np.median(xs[in_bin])), float(np.percentile(ys[in_bin], 95))))
    if len(points) < 6:
        raise ValueError(f"insufficient pixel support for row {source_rows}: {len(points)} bins")
    px = np.asarray([point[0] for point in points])
    py = np.asarray([point[1] for point in points])
    slope, intercept = np.polyfit(px, py, 1)
    residuals = py - (slope * px + intercept)
    rmse = float(np.sqrt(np.mean(residuals**2)))
    standard_error = float(
        np.sqrt(np.sum(residuals**2) / (len(points) - 2) / np.sum((px - px.mean()) ** 2))
    )
    return {
        "source_rows_as_locator": sorted(source_rows),
        "x_span_px": [x0, x1],
        "pixel_threshold": threshold,
        "pixel_measurement": "95th percentile dark-pixel y per 25 px x-bin; ordinary least-squares line fit",
        "estimated_slope_px_per_px": float(slope),
        "fit_rmse_px": rmse,
        "slope_standard_error_px_per_px": standard_error,
        "x_bin_count": len(points),
        "human_adjudication": "visually confirmed one continuous printed text row; OCR boxes/IDs used only to locate it",
    }


def page_pixel_evidence(capture_record: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = []
    for side in capture_record["sides"]:
        key = (side["fixture_id"], side["side"])
        if side["blank_declared"]:
            evidence.append({"fixture_id": key[0], "side": key[1], "status": "declared_blank_excluded"})
            continue
        tokens = [_Token(**item) for item in side["tokens"]]
        path = Path(side["local_paths"]["image"])
        projections = [pixel_projection_slope(path, threshold=t) for t in (90, 120, 150, 180)]
        coarse = projections[1]["slope"]
        rows = [pixel_row_fit(path, tokens, ids, coarse) for ids in ROW_LOCATORS[key]]
        for ordinal, row in enumerate(rows, start=1):
            row["row_evidence_id"] = f"{key[0]}.{key[1]}.body-row-{ordinal:02d}"
        auxiliary_rows = [pixel_row_fit(path, tokens, ids, coarse) for ids in AUXILIARY_ROW_LOCATORS.get(key, [])]
        for ordinal, row in enumerate(auxiliary_rows, start=1):
            row["row_evidence_id"] = f"{key[0]}.{key[1]}.aux-row-{ordinal:02d}"
        row_slopes = [row["estimated_slope_px_per_px"] for row in rows]
        evidence.append({
            "fixture_id": key[0],
            "side": key[1],
            "global_pixel_projection_by_threshold": projections,
            "adjudicated_rows": rows,
            "auxiliary_adjudicated_rows": auxiliary_rows,
            "row_slope_median": float(median(row_slopes)),
            "row_slope_min": min(row_slopes),
            "row_slope_max": max(row_slopes),
            "row_slope_spread": max(row_slopes) - min(row_slopes),
            "row_slope_spread_as_full_page_vertical_displacement_px": (max(row_slopes) - min(row_slopes)) * side["dimensions_px"][0],
            "global_candidate_slope": float(median(row_slopes)),
        })
    return evidence


def _snapshot(lines: list[dict[str, Any]], unresolved: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unresolved_by_line: dict[str, list[int]] = defaultdict(list)
    for item in unresolved:
        for line_id in item["candidate_line_ids"]:
            unresolved_by_line[line_id].append(item["token_source_row"])
    result = []
    for line in lines:
        assigned = sorted(int(identity[6:]) for identity in line["token_ids"])
        ambiguous = sorted(unresolved_by_line.get(line["line_id"], []))
        members = sorted(set(assigned + ambiguous))
        result.append({
            "members": members,
            "assigned": assigned,
            "ambiguous": ambiguous,
            "bounds_px": {key: line[key] for key in ("left_px", "right_px", "top_px", "bottom_px")},
        })
    return result


def group_with_slope(tokens: list[_Token], slope: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Use the exact production downstream function with only slope selection replaced."""

    original = production_geometry._estimate_baseline_slope
    production_geometry._estimate_baseline_slope = lambda _tokens, _tolerance: slope
    try:
        return group_physical_lines(tokens)
    finally:
        production_geometry._estimate_baseline_slope = original


def changed_events(
    fixture_id: str,
    side: str,
    tokens: list[_Token],
    before_lines: list[dict[str, Any]],
    before_unresolved: list[dict[str, Any]],
    after_lines: list[dict[str, Any]],
    after_unresolved: list[dict[str, Any]],
    production_slope: float,
    candidate_slope: float,
    candidate_name: str,
) -> list[dict[str, Any]]:
    before = _snapshot(before_lines, before_unresolved)
    after = _snapshot(after_lines, after_unresolved)
    before_sets = {frozenset(row["members"]) for row in before}
    after_sets = {frozenset(row["members"]) for row in after}
    changed = [("production", row) for row in before if frozenset(row["members"]) not in after_sets]
    changed += [("candidate", row) for row in after if frozenset(row["members"]) not in before_sets]
    components: list[list[tuple[str, dict[str, Any]]]] = []
    while changed:
        component = [changed.pop()]
        member_set = set(component[0][1]["members"])
        while True:
            found = next((i for i, (_label, row) in enumerate(changed) if member_set.intersection(row["members"])), None)
            if found is None:
                break
            item = changed.pop(found)
            member_set.update(item[1]["members"])
            component.append(item)
        components.append(component)
    by_source = {token.source_row: token for token in tokens}
    events = []
    for ordinal, component in enumerate(components, start=1):
        identities = sorted({identity for _label, row in component for identity in row["members"]})
        events.append({
            "fixture_id": fixture_id,
            "side": side,
            "event_id": f"{fixture_id}.{side}.{candidate_name}-{ordinal:03d}",
            "production_slope": production_slope,
            "candidate_slope": candidate_slope,
            "source_rows": identities,
            "token_boxes": [
                {"source_row": identity, "text_locator": by_source[identity].text, "box_px": [by_source[identity].x, by_source[identity].y, by_source[identity].width, by_source[identity].height]}
                for identity in identities
            ],
            "production_grouping": [row for label, row in component if label == "production"],
            "candidate_grouping": [row for label, row in component if label == "candidate"],
            "classification": "pending_pixel_visual_adjudication",
        })
    return events


def candidate_experiments(capture_record: dict[str, Any], landscape: dict[str, Any], pixel_evidence: list[dict[str, Any]]) -> dict[str, Any]:
    pixel_lookup = {(item.get("fixture_id"), item.get("side")): item for item in pixel_evidence}
    landscape_lookup = {(item["fixture_id"], item["side"]): item for item in landscape["sides"]}
    results = []
    for captured in capture_record["sides"]:
        key = (captured["fixture_id"], captured["side"])
        tokens = [_Token(**item) for item in captured["tokens"]]
        if not tokens:
            results.append({"fixture_id": key[0], "side": key[1], "blank": True, "production_slope": 0.0, "candidate_slope": None, "events": []})
            continue
        baseline_lines, baseline_unresolved, _ = group_physical_lines(tokens)
        landscape_side = landscape_lookup[key]
        nonzero_candidates = [item for item in landscape_side["candidates"] if item["slope"] != 0]
        score_candidate = max(
            (item for item in nonzero_candidates if item["multi_token_region_count"] >= 2),
            key=lambda item: (item["cohesion_score"], -abs(item["slope"])),
        )
        pixel_side = pixel_lookup[key]
        pixel_slope = pixel_side.get("global_candidate_slope")
        # At less than a two-pixel baseline displacement across the raster,
        # abstain to zero: this is below the pixel method's useful resolution.
        width = captured["dimensions_px"][0]
        if pixel_slope is not None and abs(pixel_slope) * width < 2.0:
            pixel_slope = 0.0
        candidates = {"cohesion_without_singleton_veto": score_candidate["slope"], "pixel_row_median": pixel_slope}
        candidate_records = {}
        for name, slope in candidates.items():
            lines, unresolved, measurements = group_with_slope(tokens, slope)
            candidate_records[name] = {
                "slope": slope,
                "support": pixel_side.get("adjudicated_rows") if name == "pixel_row_median" else {"cohesion_score": score_candidate["cohesion_score"], "singleton_count": score_candidate["singleton_count"], "region_count": score_candidate["region_count"]},
                "lines": lines,
                "unresolved": unresolved,
                "measurements": measurements,
                "events": changed_events(key[0], key[1], tokens, baseline_lines, baseline_unresolved, lines, unresolved, 0.0, slope, name),
            }
        results.append({
            "fixture_id": key[0],
            "side": key[1],
            "blank": False,
            "production_slope": 0.0,
            "production_lines": baseline_lines,
            "production_unresolved": baseline_unresolved,
            "candidates": candidate_records,
        })
    return {"schema": "baseline-slope-candidate-comparison-v1", "sides": results}


def synthetic_token(source_row: int, x: int, y: int, *, width: int = 24, height: int = 10) -> _Token:
    return _Token(source_row, f"t{source_row}", 99.0, 5, 1, 1, 1, 1, source_row, x, y, width, height)


def synthetic_matrix() -> list[dict[str, Any]]:
    """Known physical interpretations; labels are oracle-only and never estimator input."""

    xs = (10, 80, 150, 220, 290, 360, 430)

    def rows(specs: list[tuple[int, float]], *, first: int = 1) -> tuple[list[_Token], list[list[int]]]:
        tokens: list[_Token] = []
        identities: list[list[int]] = []
        source = first
        for intercept, slope in specs:
            group = []
            for x in xs:
                y = round(intercept + slope * x)
                tokens.append(synthetic_token(source, x, y, width=40, height=12))
                group.append(source)
                source += 1
            identities.append(group)
        return tokens, identities

    horizontal, horizontal_ids = rows([(40, 0.0), (110, 0.0)])
    shared, shared_ids = rows([(40, .08), (110, .08)])
    skew_singleton, singleton_ids = rows([(40, .08), (110, .08)])
    skew_singleton.append(synthetic_token(15, 20, 285))
    header, header_ids = rows([(10, .03), (70, .03), (130, .03)])
    competing, competing_ids = rows([(35, .06), (61, -.015)])
    split_regions, split_ids = rows([(40, .05), (100, .05), (170, -.04), (230, -.04)])
    single, single_ids = rows([(40, .05)])
    outliers, outlier_ids = rows([(40, .035), (110, .035)])
    outliers.extend([synthetic_token(15, 15, 285), synthetic_token(16, 470, 315)])

    cases: list[tuple[str, list[_Token], dict[str, Any]]] = [
        ("A_horizontal_rows", horizontal, {"expected_slope": 0.0, "expected_rows": horizontal_ids, "must_preserve_rows": True}),
        ("B_shared_skew", shared, {"expected_slope": .08, "expected_rows": shared_ids, "must_preserve_rows": True}),
        ("C_skew_plus_singleton", skew_singleton, {"expected_slope": .08, "expected_rows": singleton_ids, "must_ignore_unrelated_singleton": True}),
        ("D_skew_plus_header", header, {"expected_slope": .03, "expected_rows": header_ids, "header_stays_separate": True}),
        ("E_competing_nearby_rows", competing, {"expected_slope": None, "expected_rows": competing_ids, "policy": "abstain_if_nearby_distinct_rows_are_at_merge_risk"}),
        ("F_different_slope_regions", split_regions, {"expected_slope": None, "expected_rows": split_ids, "policy": "abstain_on_materially_disagreeing_regions"}),
        ("G_single_sloped_row", single, {"expected_slope": None, "expected_rows": single_ids, "policy": "abstain_without_two_row_page_support"}),
        ("H_sloped_rows_plus_outliers", outliers, {"expected_slope": .035, "expected_rows": outlier_ids, "outliers_must_not_drag_estimate": True}),
    ]
    results = []
    for name, tokens, oracle in cases:
        tolerance = 3
        zero_bands = production_geometry._line_bands(tokens, tolerance, 0.0)
        score_zero = sum(len(b)*(len(b)-1)//2 for b in zero_bands)
        candidates = []
        for milli in range(-100,101):
            slope=milli/1000
            bands=production_geometry._line_bands(tokens,tolerance,slope)
            score=sum(len(b)*(len(b)-1)//2 for b in bands)
            if sum(len(b)>=2 for b in bands)>=2:
                candidates.append((score,abs(slope),slope,bands))
        best=max(candidates,key=lambda row:(row[0],-row[1])) if candidates else None
        # The candidate model permits unrelated singleton bands but still
        # requires two multi-token regions and improvement over zero.
        selected=best[2] if best and best[0]>score_zero else 0.0
        lines,unresolved,_=group_with_slope(tokens,selected)
        predicted={frozenset(int(identity[6:]) for identity in line["token_ids"]) for line in lines}
        expected={frozenset(group) for group in oracle["expected_rows"]}
        false_merges=[sorted(set.union(*(set(group) for group in expected if group & set(predicted_group)))) for predicted_group in predicted if len([group for group in expected if group & set(predicted_group)])>1]
        false_splits=[{"expected":sorted(group),"predicted_parts":[sorted(part) for part in predicted if part & set(group)]} for group in expected if len([part for part in predicted if part & set(group)])>1]
        results.append({
            "case_id":name,
            "oracle":oracle,
            "token_count":len(tokens),
            "production_slope":production_geometry._estimate_baseline_slope(tokens,tolerance),
            "zero_score":score_zero,
            "candidate_slope":selected,
            "candidate_score":best[0] if best else None,
            "candidate_singletons":sum(len(b)==1 for b in best[3]) if best else None,
            "candidate_line_memberships":[line["token_ids"] for line in lines],
            "candidate_unresolved":unresolved,
            "oracle_false_merges":false_merges,
            "oracle_false_splits":false_splits,
            "input_permutation_stability":None,
            "one_pixel_perturbation":None,
        })
    return results


def synthetic_pixel_matrix(output_dir: Path) -> list[dict[str, Any]]:
    """Exercise pixel orientation on source-independent synthetic page rasters."""

    output_dir.mkdir(parents=True, exist_ok=True)
    xs = (35, 115, 195, 275, 355, 435)

    def draw_case(name: str, rows: list[tuple[int, float]], outliers: list[tuple[int, int, int, int]] = ()) -> tuple[Path, list[_Token], list[list[int]]]:
        image = Image.new("L", (560, 440), 255)
        draw = ImageDraw.Draw(image)
        tokens: list[_Token] = []
        expected_rows: list[list[int]] = []
        source = 1
        for intercept, slope in rows:
            expected: list[int] = []
            for x in xs:
                y = round(intercept + slope * x)
                draw.rectangle((x, y, x + 39, y + 11), fill=0)
                tokens.append(synthetic_token(source, x, y, width=40, height=12))
                expected.append(source)
                source += 1
            expected_rows.append(expected)
        for x, y, width, height in outliers:
            draw.rectangle((x, y, x + width - 1, y + height - 1), fill=0)
            tokens.append(synthetic_token(source, x, y, width=width, height=height))
            source += 1
        path = output_dir / f"{name}.png"
        image.save(path)
        return path, tokens, expected_rows

    cases = [
        ("A_horizontal_rows", [(70, 0.0), (155, 0.0)], [], 0.0, "recover_zero"),
        ("B_shared_skew", [(70, .04), (155, .04)], [], .04, "recover_known_slope"),
        ("C_skew_plus_singleton", [(70, .04), (155, .04)], [(500, 350, 12, 12)], .04, "singleton_must_not_veto"),
        ("D_running_header", [(55, .03), (135, .03), (215, .03)], [], .03, "keep_header_and_body_rows_separate"),
        ("E_competing_nearby_rows", [(90, .04), (124, -.025)], [], None, "abstain_if_distinct_rows_merge"),
        ("F_different_slope_regions", [(70, .045), (125, .045), (275, -.045), (335, -.045)], [], None, "abstain_on_region_disagreement"),
        ("G_single_sloped_row", [(160, .04)], [], None, "abstain_without_two_row_support"),
        ("H_local_outliers", [(75, .035), (165, .035)], [(500, 340, 9, 9), (20, 360, 9, 9)], .035, "outliers_must_not_drag_estimate"),
    ]
    results = []
    for name, row_specs, outliers, expected_slope, policy in cases:
        path, tokens, expected_rows = draw_case(name, row_specs, outliers)
        projection_by_threshold = [pixel_projection_slope(path, threshold=value) for value in (90, 120, 150, 180)]
        slope = projection_by_threshold[1]["slope"]
        row_runs = corrected_ink_run_count(path, slope)
        # The candidate's minimum support policy is explicit: one corrected
        # ink run cannot establish a page-global slope. F's upper/lower local
        # projection estimates expose a region disagreement independently.
        if name == "F_different_slope_regions":
            image = Image.open(path)
            upper_path, lower_path = output_dir / "F_upper.png", output_dir / "F_lower.png"
            image.crop((0, 0, image.width, image.height // 2)).save(upper_path)
            image.crop((0, image.height // 2, image.width, image.height)).save(lower_path)
            upper = pixel_projection_slope(upper_path, threshold=120)["slope"]
            lower = pixel_projection_slope(lower_path, threshold=120)["slope"]
            disagrees = abs(upper - lower) > .01
        else:
            upper = lower = None
            disagrees = False
        selected = None if row_runs < 2 or disagrees else slope
        lines, unresolved, _ = group_with_slope(tokens, selected or 0.0)
        assigned = {frozenset(int(identity[6:]) for identity in line["token_ids"]) for line in lines}
        expected = {frozenset(group) for group in expected_rows}
        false_merges = [
            sorted(set.union(*(set(group) for group in expected if group & set(predicted))))
            for predicted in assigned
            if len([group for group in expected if group & set(predicted)]) > 1
        ]
        false_splits = [sorted(group) for group in expected if len([part for part in assigned if part & set(group)]) > 1]
        results.append({
            "case_id": name,
            "policy": policy,
            "expected_slope": expected_slope,
            "selected_slope": selected,
            "projection_by_threshold": projection_by_threshold,
            "corrected_ink_runs": row_runs,
            "upper_region_slope": upper,
            "lower_region_slope": lower,
            "region_disagreement": disagrees,
            "predicted_line_memberships": [line["token_ids"] for line in lines],
            "false_merges": false_merges,
            "false_splits": false_splits,
            "unresolved": unresolved,
            "pixel_path_local_only": str(path),
        })
    return results


def grouping_identity_state(tokens: list[_Token], slope: float) -> tuple[set[frozenset[int]], set[int], set[int]]:
    lines, unresolved, _ = group_with_slope(tokens, slope)
    groups = {
        frozenset(int(identity[6:]) for identity in line["token_ids"])
        for line in lines
    }
    ambiguous = {item["token_source_row"] for item in unresolved if item["code"] == "ambiguous_line_assignment"}
    unassigned = {item["token_source_row"] for item in unresolved if item["code"] == "unassigned_line_assignment"}
    return groups, ambiguous, unassigned


def _relaxed_score_slope(tokens: list[_Token], tolerance: int) -> float:
    zero = production_geometry._line_bands(tokens, tolerance, 0.0)
    zero_score = sum(len(band) * (len(band) - 1) // 2 for band in zero)
    candidates = []
    for milli in range(-100, 101):
        slope = milli / 1000
        bands = production_geometry._line_bands(tokens, tolerance, slope)
        score = sum(len(band) * (len(band) - 1) // 2 for band in bands)
        if sum(len(band) >= 2 for band in bands) >= 2:
            candidates.append((score, abs(slope), slope))
    winner = max(candidates, key=lambda item: (item[0], -item[1]))
    return winner[2] if winner[0] > zero_score else 0.0


def stability_experiments(capture_record: dict[str, Any], pixel_evidence: list[dict[str, Any]]) -> dict[str, Any]:
    pixel_lookup = {(item.get("fixture_id"), item.get("side")): item for item in pixel_evidence}
    rng = random.Random(20260928)
    side_results = []
    for captured in capture_record["sides"]:
        if captured["blank_declared"] or not captured["tokens"]:
            continue
        key = (captured["fixture_id"], captured["side"])
        tokens = [_Token(**record) for record in captured["tokens"]]
        tolerance = captured["tolerance_px"]
        baseline_slope = production_geometry._estimate_baseline_slope(tokens, tolerance)
        relaxed_slope = _relaxed_score_slope(tokens, tolerance)
        pixel_slope = pixel_lookup[key]["global_candidate_slope"]
        width = captured["dimensions_px"][0]
        if abs(pixel_slope) * width < 2.0:
            pixel_slope = 0.0
        baseline_groups, baseline_ambiguous, baseline_unassigned = grouping_identity_state(tokens, pixel_slope)
        image_path = Path(captured["local_paths"]["image"])
        baseline_row_fits = [pixel_row_fit(image_path, tokens, ids, pixel_slope) for ids in ROW_LOCATORS[key]]
        baseline_row_slopes = [fit["estimated_slope_px_per_px"] for fit in baseline_row_fits]
        baseline_pixel_row_median = float(median(baseline_row_slopes))

        permuted = list(tokens)
        rng.shuffle(permuted)
        permutation_production_slope = production_geometry._estimate_baseline_slope(permuted, tolerance)
        permutation_relaxed_slope = _relaxed_score_slope(permuted, tolerance)
        permutation_state = grouping_identity_state(permuted, pixel_slope)
        permuted_row_slopes = [
            pixel_row_fit(image_path, permuted, ids, pixel_slope)["estimated_slope_px_per_px"]
            for ids in ROW_LOCATORS[key]
        ]

        row_ids = ROW_LOCATORS[key][0]
        perturbed = list(tokens)
        target = next(token for token in perturbed if token.source_row == row_ids[0])
        target_index = perturbed.index(target)
        perturbed[target_index] = _Token(**{**target.__dict__, "y": target.y + 1})
        original_map = {token.source_row: token for token in tokens}
        original_fit = baseline_row_fits[0]
        perturbed_row_fits = [pixel_row_fit(image_path, perturbed, ids, pixel_slope) for ids in ROW_LOCATORS[key]]
        perturbed_row_slopes = [fit["estimated_slope_px_per_px"] for fit in perturbed_row_fits]
        perturbed_pixel_row_median = float(median(perturbed_row_slopes))
        perturbed_fit = perturbed_row_fits[0]
        perturbed_selected_pixel_slope = (
            0.0 if abs(perturbed_pixel_row_median) * width < 2.0 else perturbed_pixel_row_median
        )
        perturbed_production_slope = production_geometry._estimate_baseline_slope(perturbed, tolerance)
        perturbed_relaxed_slope = _relaxed_score_slope(perturbed, tolerance)
        perturbed_state = grouping_identity_state(perturbed, pixel_slope)
        side_results.append({
            "fixture_id": key[0],
            "side": key[1],
            "permutation": {
                "seed": 20260928,
                "production_slope_stable": baseline_slope == permutation_production_slope,
                "relaxed_score_slope_stable": relaxed_slope == permutation_relaxed_slope,
                "pixel_candidate_grouping_stable": baseline_groups == permutation_state[0] and baseline_ambiguous == permutation_state[1] and baseline_unassigned == permutation_state[2],
                "pixel_row_measurement_stable": baseline_row_slopes == permuted_row_slopes,
                "pixel_row_median_slope_stable": baseline_pixel_row_median == float(median(permuted_row_slopes)),
            },
            "one_pixel_coordinate_perturbation": {
                "identity": target.source_row,
                "coordinate": "y + 1 px",
                "input_changed": original_map[target.source_row].y != perturbed[target_index].y,
                "production_slope_changed": baseline_slope != perturbed_production_slope,
                "relaxed_score_slope_changed": relaxed_slope != perturbed_relaxed_slope,
                "pixel_candidate_slope_changed": pixel_slope != perturbed_selected_pixel_slope,
                "pixel_row_measurement_changed": baseline_row_slopes != perturbed_row_slopes,
                "pixel_row_median_measurement_changed": baseline_pixel_row_median != perturbed_pixel_row_median,
                "pixel_candidate_grouping_changed": baseline_groups != perturbed_state[0],
                "assignment_changed": baseline_groups != perturbed_state[0] or baseline_ambiguous != perturbed_state[1] or baseline_unassigned != perturbed_state[2],
                "production_slope_before": baseline_slope,
                "production_slope_after": perturbed_production_slope,
                "relaxed_slope_before": relaxed_slope,
                "relaxed_slope_after": perturbed_relaxed_slope,
                "pixel_row_fit_before": original_fit["estimated_slope_px_per_px"],
                "pixel_row_fit_after": perturbed_fit["estimated_slope_px_per_px"],
                "pixel_candidate_slope_before": baseline_pixel_row_median,
                "pixel_candidate_slope_after": perturbed_selected_pixel_slope,
                "pixel_row_median_measurement_before": baseline_pixel_row_median,
                "pixel_row_median_measurement_after": perturbed_pixel_row_median,
            },
        })
    return {"schema": "baseline-slope-stability-v1", "sides": side_results}


def scale_experiments(synthetic_pixel_dir: Path, output_dir: Path) -> dict[str, Any]:
    """Exploratory coordinate scaling check; no DPI guarantee is implied."""

    from PIL import Image as PILImage

    output_dir.mkdir(parents=True, exist_ok=True)
    source = synthetic_pixel_dir / "B_shared_skew.png"
    original = PILImage.open(source).convert("L")
    results = []
    for scale in (0.5, 1.0, 2.0, 3.0):
        if scale == 1.0:
            path = source
        else:
            width, height = round(original.width * scale), round(original.height * scale)
            resized = original.resize((width, height), resample=PILImage.Resampling.NEAREST)
            path = output_dir / f"scaled-{scale:g}.png"
            resized.save(path)
        fit = pixel_projection_slope(path, threshold=120)
        results.append({
            "scale_factor": scale,
            "dimensions_px": fit["dimensions_px"],
            "estimated_slope_px_per_px": fit["slope"],
            "difference_from_unscaled": None,
            "support_pixels": fit["support_pixels"],
        })
    base = results[1]["estimated_slope_px_per_px"]
    for record in results:
        record["difference_from_unscaled"] = record["estimated_slope_px_per_px"] - base
    return {"scope": "exploratory synthetic nearest-neighbor scale only", "results": results}


def resolution_boundary_experiments(output_dir: Path) -> dict[str, Any]:
    """Expose the two-pixel full-page abstention boundary and its output effect."""

    output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    width, height = 560, 440
    threshold_slope = 2.0 / width
    for intended in (threshold_slope - .0005, threshold_slope - .00025, threshold_slope, threshold_slope + .00025, threshold_slope + .0005):
        image = Image.new("L", (width, height), 255)
        draw = ImageDraw.Draw(image)
        tokens = []
        source = 1
        for base in (70, 155):
            for x in (40, 135, 230, 325, 420, 515):
                y = round(base + intended * x)
                draw.rectangle((x, y, x + 39, y + 11), fill=0)
                tokens.append(synthetic_token(source, x, y, width=40, height=12))
                source += 1
        path = output_dir / f"threshold-{intended:.7f}.png"
        image.save(path)
        measured = pixel_projection_slope(path, threshold=120)["slope"]
        selected = 0.0 if abs(measured) * width < 2.0 else measured
        zero_state = grouping_identity_state(tokens, 0.0)
        selected_state = grouping_identity_state(tokens, selected)
        results.append({
            "intended_slope": intended,
            "measured_slope": measured,
            "full_page_displacement_px": abs(measured) * width,
            "abstention_threshold_px": 2.0,
            "selected_slope": selected,
            "grouping_changed_from_zero": zero_state[0] != selected_state[0],
            "assignment_changed_from_zero": zero_state[1:] != selected_state[1:],
        })
    return {"policy": "select only when measured baseline displacement is at least 2 px across page width; otherwise explicit slope abstention", "results": results}
