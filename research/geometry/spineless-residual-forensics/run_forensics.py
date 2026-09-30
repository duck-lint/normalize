"""Reproduce frozen spineless captures and trace four residual rows.

This harness reuses the prior study's measured crop and deskew values. It
captures raw TSV before calling the unchanged production parser and grouping
functions, then records the intermediate vertical-band and horizontal-region
decisions for the target tokens. No production module is patched.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any

from PIL import Image
import pytesseract
from pytesseract import Output

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from normalize import geometry as production  # noqa: E402

PRIOR = ROOT / "research/geometry/spineless-acquisition-ablation/results.json"
SOURCE_DIR = ROOT / "fixtures/einstein/spineless"
OUT_DIR = Path(__file__).resolve().parent
PAGES = (26, 27, 40, 41, 52, 53)
CROP = (0, 0, 1500, 2340)
SCALE = 144 / 300
TARGET_ROWS = {
    26: {"failure_1_changes_embankment_yet": list(range(69, 77))},
    27: {"failure_2_if_k_every_other": list(range(32, 41))},
    53: {"failure_4_greater_velocities_square_root": list(range(108, 116))},
}
TARGET_RECTS = {
    "26/failure_1_changes_embankment_yet": [75, 590, 730, 630],
    "27/failure_2_if_k_every_other": [145, 155, 655, 185],
    # This rectangle is the printed row, not the larger Tesseract box that
    # incorrectly spans it and its neighbors.
    "27/failure_3_affords_missing": [110, 660, 650, 700],
    "53/failure_4_greater_velocities_square_root": [85, 485, 620, 520],
}
CONTROL_ROWS = {
    "26/failure_1_changes_embankment_yet": {
        "preceding_row": [62, 63, 64, 65, 66, 67],
        "following_row": [79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89],
        "same_center_ocr_mark": [77],
    },
    "27/failure_2_if_k_every_other": {
        "preceding_row": [26, 27, 28, 29, 30],
        "following_row": [42, 43, 44, 45, 46, 47, 48],
    },
    "27/failure_3_affords_missing": {
        "preceding_row": [179, 180, 181, 182, 183, 184, 185, 186, 187],
        "following_row": [193, 194, 195, 196, 197, 198, 199, 200, 201],
    },
    "53/failure_4_greater_velocities_square_root": {
        "preceding_prose_row": [103, 104, 105, 106],
        "following_row": [117, 118, 119, 120, 121, 122, 123, 124, 125, 126],
        "next_following_row": [128, 129, 130, 131, 132, 133, 134, 135, 136, 137],
    },
}
FIRST_DIVERGENCE = {
    "failure_1_changes_embankment_yet": "vertical_band_construction",
    "failure_2_if_k_every_other": "vertical_band_construction",
    "failure_3_affords_missing": "raw_tesseract_observation",
    "failure_4_greater_velocities_square_root": "vertical_band_construction",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def half_up(value: float) -> int:
    return math.floor(value + 0.5)


def prepare_page(source_path: Path, angle: float) -> tuple[Image.Image, Image.Image]:
    """Apply the exact prior crop, Pillow deskew, and 144-DPI reduction."""
    with Image.open(source_path) as opened:
        cropped = opened.convert("RGB").crop(CROP)
    rotated = cropped if angle == 0 else cropped.rotate(
        angle,
        resample=Image.Resampling.BICUBIC,
        expand=True,
        fillcolor=(255, 255, 255),
    )
    final_size = (half_up(rotated.width * SCALE), half_up(rotated.height * SCALE))
    return rotated.resize(final_size, Image.Resampling.LANCZOS), rotated


def raw_rows(tsv: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(tsv), delimiter="\t")
    rows: list[dict[str, Any]] = []
    for source_row, row in enumerate(reader, start=1):
        if not row:
            continue
        rows.append({"source_row": source_row, **row})
    return rows


def admission_record(raw: dict[str, Any], admitted: set[int], errors: dict[int, dict[str, Any]], image_size: tuple[int, int]) -> dict[str, Any]:
    """Explain the production parser outcome for one captured TSV row."""
    row_id = raw["source_row"]
    if row_id in admitted:
        x, y, width, height = (int(raw[k]) for k in ("left", "top", "width", "height"))
        confidence = float(raw["conf"])
        return {
            "decision": "admitted",
            "predicate": "valid 12-column row; integer hierarchy/box; 1<=level<=5; nonnegative IDs; confidence in [0,100]; positive box inside raster; nonblank text; unique payload",
            "measured": {
                "level": int(raw["level"]),
                "confidence": confidence,
                "confidence_range_check": "0 <= confidence <= 100",
                "box_xyxy": [x, y, x + width, y + height],
                "raster_dimensions": list(image_size),
                "positive_box": width > 0 and height > 0,
                "inside_raster": x >= 0 and y >= 0 and x + width <= image_size[0] and y + height <= image_size[1],
                "text_nonblank": bool(raw["text"].strip()),
                "payload_unique": True,
            },
        }
    if row_id in errors:
        return {"decision": "rejected", "predicate": "parse_tsv_rows row error", "error": errors[row_id]}
    level = int(raw["level"])
    confidence = float(raw["conf"])
    text = raw["text"]
    if confidence == -1 or not text.strip():
        return {"decision": "skipped", "predicate": "confidence == -1 or text.strip() is empty"}
    if level != 5:
        return {"decision": "not_admitted", "predicate": "raw hierarchy row is not a word-level record"}
    return {"decision": "not_admitted", "predicate": "duplicate token payload"}


def token_dict(token: Any) -> dict[str, Any]:
    return {
        "source_row": token.source_row,
        "text": token.text,
        "confidence": token.confidence,
        "tesseract_ids": [token.page_num, token.block_num, token.par_num, token.line_num, token.word_num],
        "box_xyxy": [token.x, token.y, token.x1, token.y1],
        "center_x": (token.x + token.x1) / 2,
        "center_y": token.center_y,
        "width": token.width,
        "height": token.height,
        "baseline_bottom_y": token.y1,
    }


def vertical_trace(tokens: list[Any], tolerance: int, slope: float) -> tuple[list[list[Any]], dict[int, dict[str, Any]]]:
    """Mirror _line_bands' vertical phase and retain the exact predicate data."""
    ordered = sorted(tokens, key=lambda t: (production._adjusted_center_y(t, slope), t.x, t.source_row))
    bands: list[list[Any]] = []
    decisions: dict[int, dict[str, Any]] = {}
    gap_limit = production._horizontal_gap_limit(tokens)
    for token in ordered:
        adjusted = production._adjusted_center_y(token, slope)
        detail: dict[str, Any] = {
            "adjusted_center_y": adjusted,
            "tolerance": tolerance,
            "current_band_before": None,
            "band_median_before": None,
            "median_difference": None,
            "median_support": False,
            "neighbor_support_tokens": [],
            "decision": "new_vertical_band",
        }
        if bands:
            detail["current_band_before"] = len(bands) - 1
            current_median = median(production._adjusted_center_y(item, slope) for item in bands[-1])
            detail["band_median_before"] = current_median
            detail["median_difference"] = abs(adjusted - current_median)
            detail["median_support"] = detail["median_difference"] <= tolerance
            detail["neighbor_support_tokens"] = [
                item.source_row
                for item in bands[-1]
                if abs(adjusted - production._adjusted_center_y(item, slope)) <= tolerance
                and production._horizontally_adjacent(item, token, gap_limit)
            ]
            if detail["median_support"] or detail["neighbor_support_tokens"]:
                bands[-1].append(token)
                detail["decision"] = "join_current_vertical_band"
            else:
                bands.append([token])
                detail["decision"] = "start_new_vertical_band"
        else:
            bands.append([token])
        detail["vertical_band_after"] = len(bands) - 1
        decisions[token.source_row] = detail
    return bands, decisions


def horizontal_trace(bands: list[list[Any]], gap_limit: float) -> tuple[list[list[Any]], list[dict[str, Any]]]:
    regions: list[list[Any]] = []
    events: list[dict[str, Any]] = []
    for band_index, band in enumerate(bands):
        ordered = sorted(band, key=lambda t: (t.x, t.source_row))
        current: list[Any] = []
        covered_right: int | None = None
        for token in ordered:
            gap = None if not current or covered_right is None else token.x - covered_right
            split = gap is not None and gap > gap_limit
            events.append({
                "vertical_band": band_index,
                "token_source_row": token.source_row,
                "x0": token.x,
                "x1": token.x1,
                "covered_right_before": covered_right,
                "actual_gap": gap,
                "gap_limit": gap_limit,
                "split_before_token": split,
            })
            if split:
                regions.append(current)
                current = []
            current.append(token)
            covered_right = token.x1 if covered_right is None else max(covered_right, token.x1)
        if current:
            regions.append(current)
    return regions, events


def candidate_trace(tokens: list[Any], regions: list[list[Any]], tolerance: int, slope: float, gap_limit: float) -> dict[int, list[dict[str, Any]]]:
    ordered_regions = sorted(
        enumerate(regions),
        key=lambda pair: (median(production._adjusted_center_y(t, slope) for t in pair[1]), min(t.x for t in pair[1]), pair[0]),
    )
    records: dict[int, list[dict[str, Any]]] = {}
    for token in tokens:
        candidates = []
        adjusted = production._adjusted_center_y(token, slope)
        for region_index, region in ordered_regions:
            region_median = median(production._adjusted_center_y(item, slope) for item in region)
            support = abs(adjusted - region_median) <= tolerance
            adjacent = [item.source_row for item in region if item is not token and abs(adjusted - production._adjusted_center_y(item, slope)) <= tolerance and production._horizontally_adjacent(item, token, gap_limit)]
            contained = min(item.x for item in region) <= token.x <= max(item.x1 for item in region)
            direct_member = token in region and (support or bool(adjacent))
            interval_candidate = support and contained
            if direct_member or interval_candidate:
                candidates.append({
                    "candidate_line_id": f"line-{ordered_regions.index((region_index, region)) + 1:04d}",
                    "region_index": region_index,
                    "bounds_x": [min(item.x for item in region), max(item.x1 for item in region)],
                    "median_adjusted_center_y": region_median,
                    "token_adjusted_center_y": adjusted,
                    "vertical_difference": abs(adjusted - region_median),
                    "tolerance": tolerance,
                    "x_contained": contained,
                    "direct_member": direct_member,
                    "adjacent_support_source_rows": adjacent,
                })
        records[token.source_row] = candidates
    return records


def capture_page(page: int, prior: dict[str, Any]) -> tuple[dict[str, Any], str, list[Any], list[Any]]:
    source_path = SOURCE_DIR / f"pg.{page}.jpg"
    with Image.open(source_path) as source_image:
        source_dimensions = list(source_image.size)
    if source_dimensions != prior["source_dimensions"]:
        raise RuntimeError(f"page {page}: source dimensions differ from the prior spineless capture")
    final, rotated = prepare_page(source_path, prior["angle_correction_degrees"])
    tsv = pytesseract.image_to_data(final, lang="eng", config="--psm 6", output_type=Output.STRING)
    tokens, row_errors = production.parse_tsv_rows(tsv, *final.size)
    lines, unresolved, measurements = production.group_physical_lines(tokens)
    expected = prior["geometry"]
    if (
        sha256(source_path.read_bytes()) != prior["source_sha256"]
        or sha256(final.tobytes()) != prior["transform"]["final_rgb_sha256"]
        or sha256(tsv.encode("utf-8")) != prior["tsv_sha256"]
        or (len(tokens), len(lines), sum(x["code"] == "ambiguous_line_assignment" for x in unresolved), sum(x["code"] == "unassigned_line_assignment" for x in unresolved))
        != (expected["token_count"], expected["line_count"], expected["ambiguous_count"], expected["unassigned_count"])
    ):
        raise RuntimeError(f"page {page}: reproduced observations differ from prior capture")
    summary = {
        "page": page,
        "source_file": source_path.relative_to(ROOT).as_posix(),
        "source_dimensions": source_dimensions,
        "source_sha256": sha256(source_path.read_bytes()),
        "crop_box": list(CROP),
        "correction_angle_degrees": prior["angle_correction_degrees"],
        "deskewed_dimensions": list(rotated.size),
        "final_dimensions": list(final.size),
        "final_rgb_sha256": sha256(final.tobytes()),
        "raw_tsv_sha256": sha256(tsv.encode("utf-8")),
        "admitted_tokens": len(tokens),
        "physical_lines": len(lines),
        "ambiguous": sum(x["code"] == "ambiguous_line_assignment" for x in unresolved),
        "unassigned": sum(x["code"] == "unassigned_line_assignment" for x in unresolved),
        "selected_slope": measurements["baseline_slope_px_per_px"],
        "vertical_tolerance": measurements["tolerance_px"],
        "horizontal_gap_limit": measurements["horizontal_gap_limit_px"],
        "reproduces_prior": True,
    }
    return summary, tsv, tokens, row_errors


def build_failure_trace(context: str, page: int, tsv: str, tokens: list[Any], errors: list[dict[str, Any]], prior: dict[str, Any]) -> dict[str, Any]:
    raw = raw_rows(tsv)
    admitted = {t.source_row for t in tokens}
    errors_by_row = {e["source_row"]: e for e in errors}
    prior_image_size = tuple(prior["transform"]["final_dimensions"])
    target = TARGET_ROWS.get(page, {}).get(context, [])
    target_rect = TARGET_RECTS[f"{page}/{context}"]
    x0, y0, x1, y1 = target_rect
    relevant_raw = []
    for row in raw:
        try:
            left, top, width, height = map(int, (row["left"], row["top"], row["width"], row["height"]))
            intersects = left < x1 and left + width > x0 and top < y1 and top + height > y0
        except (KeyError, ValueError):
            intersects = False
        if intersects:
            relevant_raw.append({
                "source_row": row["source_row"],
                "level": int(row["level"]),
                "page_block_par_line_word": [int(row[k]) for k in ("page_num", "block_num", "par_num", "line_num", "word_num")],
                "box_xyxy": [left, top, left + width, top + height],
                "confidence": float(row["conf"]),
                "text": row["text"],
                "admission": admission_record(row, admitted, errors_by_row, prior_image_size),
            })
    target_tokens = [t for t in tokens if t.source_row in target]
    if target_tokens:
        median_height = median(t.height for t in tokens if t.height > 0)
        tolerance = max(1, math.floor(median_height / 4 + 0.5))
        slope = production._estimate_baseline_slope(tokens, tolerance)
        v_bands, v_decisions = vertical_trace(tokens, tolerance, slope)
        gap_limit = production._horizontal_gap_limit(tokens)
        regions, h_events = horizontal_trace(v_bands, gap_limit)
        prod_lines, unresolved, measurements = production.group_physical_lines(tokens)
        token_json = {t.source_row: token_dict(t) for t in tokens}
        target_vertical = defaultdict(list)
        for band_index, band in enumerate(v_bands):
            for t in band:
                if t.source_row in target:
                    target_vertical[band_index].append(t.source_row)
        target_regions = defaultdict(list)
        for rid, region in enumerate(regions):
            for t in region:
                if t.source_row in target:
                    target_regions[rid].append(t.source_row)
        assignments = {token.source_row: [] for token in tokens}
        for line in prod_lines:
            for token_id in line["token_ids"]:
                row = int(token_id.removeprefix("token-"))
                assignments[row].append(line["line_id"])
        unresolved_rows = {item["token_source_row"]: item for item in unresolved}
        target_candidates = candidate_trace(tokens, regions, tolerance, slope, gap_limit)
        target_control_ids = set(target)
        for rows in CONTROL_ROWS.get(f"{page}/{context}", {}).values():
            target_control_ids.update(rows)
        inventories = {}
        for label, rows in {"target": target, **CONTROL_ROWS.get(f"{page}/{context}", {})}.items():
            chosen = sorted((t for t in tokens if t.source_row in rows), key=lambda t: (t.x, t.source_row))
            entries = []
            for i, token in enumerate(chosen):
                previous = chosen[i - 1] if i else None
                entries.append({
                    **token_json[token.source_row],
                    "x_gap_from_previous": None if previous is None else token.x - previous.x1,
                    "vertical_center_difference_from_previous": None if previous is None else token.center_y - previous.center_y,
                    "vertical_band": next((bi for bi, band in enumerate(v_bands) if token in band), None),
                    "vertical_decision": v_decisions[token.source_row],
                    "horizontal_regions": [rid for rid, region in enumerate(regions) if token in region],
                    "candidate_lines": target_candidates[token.source_row],
                    "final_assignment": assignments[token.source_row],
                    "unresolved": unresolved_rows.get(token.source_row),
                })
            inventories[label] = entries
        target_h_events = [event for event in h_events if event["token_source_row"] in target or any(event["token_source_row"] in ids for ids in inventories.values())]
        simulated_memberships = sorted(tuple(sorted(t.source_row for t in region)) for region in regions)
        production_memberships = sorted(tuple(sorted(int(i.removeprefix("token-")) for i in line["token_ids"])) for line in prod_lines)
        if simulated_memberships != production_memberships:
            raise AssertionError(f"{page}/{context}: traced bands differ from production physical-line token memberships")
        stage = {
            "admitted_token_inventory": inventories,
            "slope": slope,
            "tolerance": tolerance,
            "gap_limit": gap_limit,
            "vertical_target_memberships": dict(target_vertical),
            "horizontal_target_memberships": dict(target_regions),
            "horizontal_gap_events": target_h_events,
            "production_lines": [line for line in prod_lines if any(int(i.removeprefix("token-")) in target for i in line["token_ids"])],
            "target_unresolved": [item for item in unresolved if item["token_source_row"] in target],
            "instrumentation_matches_production_memberships": True,
        }
    else:
        median_height = median(t.height for t in tokens if t.height > 0)
        tolerance = max(1, math.floor(median_height / 4 + 0.5))
        slope = production._estimate_baseline_slope(tokens, tolerance)
        gap_limit = production._horizontal_gap_limit(tokens)
        v_bands, v_decisions = vertical_trace(tokens, tolerance, slope)
        regions, h_events = horizontal_trace(v_bands, gap_limit)
        lines, unresolved, measurements = production.group_physical_lines(tokens)
        candidate_records = candidate_trace(tokens, regions, tolerance, slope, gap_limit)
        line_by_row = {
            row: line["line_id"]
            for line in prior["geometry"]["physical_lines"]
            for row in (int(item.removeprefix("token-")) for item in line["token_ids"])
        }
        geometry_line_by_row: dict[int, str] = {}
        for line in lines:
            for item in line["token_ids"]:
                geometry_line_by_row[int(item.removeprefix("token-"))] = line["line_id"]
        # Include every admitted box that intersects the visible row and its
        # nearest row context; this exposes a merged word box without assigning
        # it a fabricated identity inside the printed sentence.
        context_rows = {
            row["source_row"]
            for row in raw
            if row["level"] == "5"
            and int(row["left"]) < x1 and int(row["left"]) + int(row["width"]) > x0
            and int(row["top"]) < y1 and int(row["top"]) + int(row["height"]) > y0
        }
        context_tokens = [
            token_dict(t)
            | {
                "production_line_id": geometry_line_by_row.get(t.source_row),
                "vertical_band": next((bi for bi, band in enumerate(v_bands) if t in band), None),
                "vertical_decision": v_decisions[t.source_row],
                "horizontal_regions": [ri for ri, region in enumerate(regions) if t in region],
                "candidate_lines": candidate_records[t.source_row],
            }
            for t in tokens if t.source_row in context_rows
        ]
        controls = CONTROL_ROWS[f"{page}/{context}"]
        control_inventory = {}
        for label, source_rows in controls.items():
            selected = sorted((t for t in tokens if t.source_row in source_rows), key=lambda t: (t.x, t.source_row))
            control_inventory[label] = []
            for index, token in enumerate(selected):
                previous = selected[index - 1] if index else None
                control_inventory[label].append({
                    **token_dict(token),
                    "x_gap_from_previous": None if previous is None else token.x - previous.x1,
                    "vertical_center_difference_from_previous": None if previous is None else token.center_y - previous.center_y,
                    "vertical_band": next((bi for bi, band in enumerate(v_bands) if token in band), None),
                    "vertical_decision": v_decisions[token.source_row],
                    "horizontal_regions": [ri for ri, region in enumerate(regions) if token in region],
                    "candidate_lines": candidate_records[token.source_row],
                    "final_assignment": geometry_line_by_row.get(token.source_row),
                })
        stage = {
            "admitted_spatially_intersecting_tokens": context_tokens,
            "matched_control_inventory": control_inventory,
            "parser_row_errors_in_context": [e for e in errors if e["source_row"] in context_rows],
            "selected_slope": measurements["baseline_slope_px_per_px"],
            "tolerance": measurements["tolerance_px"],
            "gap_limit": measurements["horizontal_gap_limit_px"],
            "vertical_and_horizontal_memberships_of_intersecting_tokens": {
                str(token.source_row): {
                    "vertical_band": next((bi for bi, band in enumerate(v_bands) if token in band), None),
                    "horizontal_regions": [ri for ri, region in enumerate(regions) if token in region],
                    "final_assignment": geometry_line_by_row.get(token.source_row),
                }
                for token in tokens if token.source_row in context_rows
            },
            "line_membership_for_context_tokens": {str(row): line_by_row.get(row) for row in sorted(context_rows)},
            "unresolved_context_tokens": [e for e in unresolved if e["token_source_row"] in context_rows],
        }
    prior_page = prior
    return {
        "context": context,
        "page": page,
        "first_divergence": FIRST_DIVERGENCE[context],
        "physical_pixel_rectangle_xyxy": target_rect,
        "raw_tsv_records_intersecting_context": relevant_raw,
        "raw_tsv_row_classification": "complete_usable_boxes" if target_tokens else "complete_but_geometrically_abnormal" if relevant_raw else "missing_observation",
        "target_source_rows": target,
        "stage_trace": stage,
        "prior_spineless_line_context": [line for line in prior_page["line_texts"] if any(row in target for row in line["source_rows"])],
    }


def run() -> tuple[dict[str, Any], dict[str, Any]]:
    prior_root = json.loads(PRIOR.read_text(encoding="utf-8"))
    prior_pages = prior_root["spineless"]
    summaries: dict[str, Any] = {}
    captures: dict[int, tuple[str, list[Any], list[dict[str, Any]]]] = {}
    for page in PAGES:
        summary, tsv, tokens, errors = capture_page(page, prior_pages[str(page)])
        summaries[str(page)] = summary
        captures[page] = (tsv, tokens, errors)
    traces = []
    for key, rows in TARGET_ROWS.items():
        context, = rows.keys()
        tsv, tokens, errors = captures[key]
        traces.append(build_failure_trace(context, key, tsv, tokens, errors, prior_pages[str(key)]))
    # Missing-observation case has no token inventory. Capture raw TSV and its
    # parser outcome directly instead of fabricating token identities.
    page = 27
    tsv, tokens, errors = captures[page]
    traces.append(build_failure_trace("failure_3_affords_missing", page, tsv, tokens, errors, prior_pages[str(page)]))
    reproduction = {
        "schema": "spineless-residual-forensics-reproduction-v1",
        "prior_source": "research/geometry/spineless-acquisition-ablation/results.json",
        "tesseract": {"version": str(pytesseract.get_tesseract_version()).strip(), "language": "eng", "config": "--psm 6"},
        "ocr_invocations": 6,
        "pages": summaries,
    }
    stage_data = {
        "schema": "spineless-residual-forensics-stage-traces-v1",
        "source_observation_hashes": {str(p): summaries[str(p)]["raw_tsv_sha256"] for p in PAGES},
        "traces": traces,
    }
    return reproduction, stage_data


if __name__ == "__main__":
    reproduction, traces = run()
    (OUT_DIR / "results.json").write_text(json.dumps(reproduction, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (OUT_DIR / "stage-traces.json").write_text(json.dumps(traces, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT_DIR / 'results.json'} and stage-traces.json")
