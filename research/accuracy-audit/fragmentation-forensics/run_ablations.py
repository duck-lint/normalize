"""Run bounded geometry and page-edge raster ablations in memory."""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from statistics import median

import numpy as np
from PIL import Image
from pytesseract import Output

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src"))
import investigate as study  # noqa: E402
import normalize.geometry as geometry  # noqa: E402
import pytesseract  # noqa: E402

CLEAN_CONTROLS = {
    ("relativity_pdf17_pp40-41", "left", "line-0026"),
    ("relativity_pdf17_pp40-41", "left", "line-0029"),
    ("relativity_pdf17_pp40-41", "left", "line-0036"),
}
RESIDUALS = {
    ("relativity_pdf10_pp26-27", "left"): [
        ("token-0213", "system", None), ("token-0216", "that", "line-0047"),
        ("token-0217", "the", "line-0047"), ("token-0226", "with", "line-0049"),
        ("token-0227", "respect", "line-0049"),
    ],
    ("relativity_pdf10_pp26-27", "right"): [("token-0246", "impossible", "one_visible_row")],
    ("relativity_pdf17_pp40-41", "right"): [("token-0023", "A", "line-0003")],
}


def box_tokens(tokens):
    return {f"token-{t.source_row:04d}": t for t in tokens}


def edge_raster(image: Image.Image) -> tuple[Image.Image, dict, list[tuple[int, int]]]:
    """Detect frame-connected dark margins or a thin page-edge streak by pixels.

    A dark surround is cropped to the bright paper field. If the paper field
    continues beyond a narrow dark streak, only a detected streak in the outer
    20% is whitened. No fixture/page coordinates enter the rule.
    """
    arr = np.asarray(image.convert("L"))
    h, w = arr.shape
    bright = (arr >= 180).mean(axis=0)
    dark = (arr < 150).mean(axis=0)
    x0, x1 = 0, w
    detections = []
    edge_width = max(1, round(w * .03))
    if dark[:edge_width].mean() > .55:
        x0 = next((x for x in range(w) if bright[x] >= .65), 0)
        detections.append({"kind": "frame_connected_dark_left", "x0": 0, "x1": x0})
    if dark[w-edge_width:].mean() > .55:
        x1 = next((x for x in range(w - 1, -1, -1) if bright[x] >= .65), w - 1) + 1
        detections.append({"kind": "frame_connected_dark_right", "x0": x1, "x1": w})
    # A narrow paper-edge stripe has dark coverage across many rows while
    # ordinary glyph columns remain mostly light. This stronger criterion is
    # what distinguishes the right-edge streak from the recurring body-text
    # left margin.
    dark_mid = (arr < 200).mean(axis=0)
    mask_spans: list[tuple[int, int]] = []
    allowed = set(range(0, round(w * .20))) | set(range(round(w * .80), w))
    core = {x for x in allowed if dark_mid[x] > .65 and bright[x] < .80}
    runs = []
    for x in sorted(core):
        if not runs or x > runs[-1][-1] + 1:
            runs.append([x])
        else:
            runs[-1].append(x)
    for run in runs:
        if len(run) < 4:
            continue
        a, b = run[0], run[-1] + 1
        while a > 1 and a - 1 in allowed and dark_mid[a - 1] > .25 and bright[a - 1] < .90 and b - (a - 1) <= 60:
            a -= 1
        while b < w - 1 and b in allowed and dark_mid[b] > .25 and bright[b] < .90 and (b + 1 - a) <= 60:
            b += 1
        if (b - a <= 60 and bright[a - 1] >= .75 and bright[b] >= .75
                and not (b <= x0 + 1 or a >= x1 - 1)):
            mask_spans.append((a, b))
    for a, b in mask_spans:
        detections.append({"kind": "thin_interior_edge_streak", "x0": a, "x1": b})
    cropped = image.crop((x0, 0, x1, h))
    if mask_spans:
        from PIL import ImageDraw
        draw = ImageDraw.Draw(cropped)
        for a, b in mask_spans:
            # Mask a five-pixel guard around the detected line to cover its
            # antialiased edge. The range is data-derived, not page-specific.
            a -= x0
            b -= x0
            if b < 0 or a >= cropped.width:
                continue
            draw.rectangle((max(0, a - 2), 0, min(cropped.width - 1, b + 1), h - 1), fill="white")
    return cropped, {"crop_rect_px": [x0, 0, x1, h], "mask_spans_px": [list(span) for span in mask_spans],
                     "detected_features": detections, "input_dimensions_px": [w, h],
                     "output_dimensions_px": [cropped.width, cropped.height]}, mask_spans


def tsv_tokens(image: Image.Image):
    tsv = pytesseract.image_to_data(image.convert("RGB"), lang="eng", config="--psm 6", output_type=Output.STRING)
    tokens, errors = geometry.parse_tsv_rows(tsv, image.width, image.height)
    return tokens, errors


def lexical_counts(tokens):
    return Counter(" ".join(token.text.casefold().split()) for token in tokens)


def crop_experiment(page, kind: str):
    with Image.open(page["image_path"]) as opened:
        source = opened.convert("RGB")
    w, h = source.size
    if kind == "uniform_2pct_crop":
        dx, dy = round(w * .02), round(h * .02)
        raster = source.crop((dx, dy, w - dx, h - dy))
        info = {"crop_rect_px": [dx, dy, w - dx, h - dy], "mask_spans_px": [],
                "input_dimensions_px": [w, h], "output_dimensions_px": list(raster.size)}
        feature_spans = []
    else:
        raster, info, feature_spans = edge_raster(source)
    variant_tokens, errors = tsv_tokens(raster)
    baseline_tokens = page["tokens"]
    baseline_counts, variant_counts = lexical_counts(baseline_tokens), lexical_counts(variant_tokens)
    removed = list((baseline_counts - variant_counts).elements())
    added = list((variant_counts - baseline_counts).elements())
    baseline_ids = []
    x0, y0, x1, y1 = info["crop_rect_px"]
    for token in baseline_tokens:
        cx = token.x + token.width / 2
        cy = token.y + token.height / 2
        if kind == "uniform_2pct_crop":
            affected = not (x0 <= cx < x1 and y0 <= cy < y1)
        else:
            affected = not (x0 <= cx < x1 and y0 <= cy < y1) or any(a - 2 <= cx <= b + 2 for a, b in feature_spans)
        if affected:
            baseline_ids.append({"token_id": f"token-{token.source_row:04d}", "text": token.text,
                                 "bbox": [token.x, token.y, token.x1, token.y1], "overlaps_treatment": True})
    matched_source_ids = set()
    matched_variant_ids = set()
    for source_token in baseline_tokens:
        source_id = f"token-{source_token.source_row:04d}"
        matched = map_original_token(page, source_id, variant_tokens, info, matched_variant_ids)
        if matched is not None:
            matched_source_ids.add(source_id)
            matched_variant_ids.add(matched.source_row)
    affected_ids = {item["token_id"] for item in baseline_ids}
    body_not_reemitted = [
        {"token_id": f"token-{token.source_row:04d}", "text": token.text,
         "bbox": [token.x, token.y, token.x1, token.y1]}
        for token in baseline_tokens
        if f"token-{token.source_row:04d}" not in affected_ids
        and f"token-{token.source_row:04d}" not in matched_source_ids
    ]
    grouping = study.run_grouping(variant_tokens)
    missing_row_tokens = []
    if page["fixture_id"] == "stella_maris_pdf06_dense-dialogue" and page["side"] == "left":
        y_shift = info["crop_rect_px"][1]
        missing_row_tokens = [{"text": token.text, "bbox": [token.x, token.y, token.x1, token.y1],
                               "source_y_center": token.center_y + y_shift}
                              for token in variant_tokens if 835 <= token.center_y + y_shift <= 885]
    return {
        "raster": info, "tesseract_admitted_token_count": len(variant_tokens), "tsv_errors": errors,
        "baseline_admitted_token_count": len(baseline_tokens), "lexical_tokens_removed": removed,
        "lexical_tokens_added": added, "baseline_boxes_affected_by_treatment": baseline_ids,
        "body_tokens_not_reemitted_at_matching_location": body_not_reemitted,
        "unmatched_new_token_count": len(variant_tokens) - len(matched_variant_ids),
        "geometry": page_stats(variant_tokens, grouping),
        "stella_reported_missing_row_tokens": missing_row_tokens, "tokens": variant_tokens,
    }


def page_stats(tokens, grouping):
    unresolved = grouping["unresolved"]
    resolved = len(tokens) - len(unresolved)
    return {"admitted_tokens": len(tokens), "resolved_tokens": resolved, "residual_tokens": len(unresolved),
            "physical_lines": len(grouping["lines"]), "selected_slope": grouping["measurements"]["baseline_slope_px_per_px"],
            "tolerance_px": grouping["measurements"]["tolerance_px"],
            "horizontal_gap_limit_px": grouping["measurements"]["horizontal_gap_limit_px"]}


def map_original_token(page, token_id, variant_tokens, crop_info=None, used=None):
    artifact_tokens = {record["token_id"]: record for record in page["record"]["tokens"]}
    source = artifact_tokens[token_id]
    dx, dy = crop_info["crop_rect_px"][:2] if crop_info else (0, 0)
    source_text = source["text"].casefold()
    cx = (source["x_px"] + source["right_px"]) / 2 - dx
    cy = (source["y_px"] + source["bottom_px"]) / 2 - dy
    choices = []
    for token in variant_tokens:
        if used and token.source_row in used:
            continue
        distance = abs(token.x + token.width / 2 - cx) + abs(token.center_y - cy)
        similarity = SequenceMatcher(None, source_text, token.text.casefold()).ratio()
        if distance <= 30 and (source_text == token.text.casefold() or similarity >= .72):
            choices.append((distance - similarity * 4, token))
    return min(choices, key=lambda item: item[0])[1] if choices else None


def map_original_tokens(page, original_token_ids, variant_tokens, crop_info=None):
    used = set()
    mapped = []
    for token_id in original_token_ids:
        token = map_original_token(page, token_id, variant_tokens, crop_info, used)
        if token is None:
            return None
        used.add(token.source_row)
        mapped.append(f"token-{token.source_row:04d}")
    return mapped


def known_repairs(page, grouping, variant_tokens, crop_info=None):
    result = {}
    for (fid, page_side, label), ids in study.KNOWN_VISIBLE_LINES.items():
        if (fid, page_side) != (page["fixture_id"], page["side"]):
            continue
        mapped = map_original_tokens(page, ids, variant_tokens, crop_info)
        if mapped is None:
            result[label] = "not_comparable_after_ocr_retokenization"
        else:
            assigned = [grouping["token_candidates"].get(token_id, []) for token_id in mapped]
            result[label] = bool(assigned) and all(len(candidates) == 1 for candidates in assigned) and len({candidates[0] for candidates in assigned}) == 1
    return result


def clean_control_damage(fixture_id, side, grouping, variant_tokens, crop_info=None):
    if (fixture_id, side) != ("relativity_pdf17_pp40-41", "left"):
        return []
    artifact = json.loads((study.REVIEW / "geometry/relativity_pdf17_pp40-41.geometry.json").read_text())
    page = next(page for page in artifact["pages"] if page["side"] == side)
    original = {token["token_id"]: token for token in page["tokens"]}
    candidates = grouping["token_candidates"]
    by_text = defaultdict(list)
    for token in variant_tokens:
        by_text[token.text.casefold()].append(token)
    dx, dy = (crop_info["crop_rect_px"][:2] if crop_info else (0, 0))
    damaged = []
    for fid, page_side, line_id in CLEAN_CONTROLS:
        if (fid, page_side) != (fixture_id, side):
            continue
        source_line = next(item for item in page["physical_lines"] if item["line_id"] == line_id)
        mapped = []
        for token_id in source_line["token_ids"]:
            record = original[token_id]
            center_x = (record["x_px"] + record["right_px"]) / 2 - dx
            center_y = (record["y_px"] + record["bottom_px"]) / 2 - dy
            choices = sorted(by_text.get(record["text"].casefold(), []),
                             key=lambda item: abs(item.x + item.width / 2 - center_x) + abs(item.center_y - center_y))
            if not choices or abs(choices[0].x + choices[0].width / 2 - center_x) + abs(choices[0].center_y - center_y) > 25:
                mapped = []
                break
            mapped.append(f"token-{choices[0].source_row:04d}")
        line_ids = {tuple(candidates.get(token_id, [])) for token_id in mapped}
        if not mapped or len(line_ids) != 1 or any(len(ids) != 1 for ids in line_ids):
            damaged.append(line_id)
            continue
        candidate_line_id = next(iter(line_ids))[0]
        produced = next(line for line in grouping["lines"] if line["line_id"] == candidate_line_id)
        if set(produced["token_ids"]) != set(mapped):
            damaged.append(line_id)
    return damaged


def residual_states(page, tokens, grouping, crop_info=None):
    fixture_id, side = page["fixture_id"], page["side"]
    requested = RESIDUALS.get((fixture_id, side), [])
    if not requested:
        return []
    variant_candidates = grouping["token_candidates"]
    original_page = page["record"]
    original_by_id = {token["token_id"]: token for token in original_page["tokens"]}
    original_lines = {line["line_id"]: line["token_ids"] for line in original_page["physical_lines"]}
    x0, y0 = crop_info["crop_rect_px"][:2] if crop_info else (0, 0)
    by_text = defaultdict(list)
    for token in tokens:
        by_text[token.text.casefold()].append(token)
    output = []
    for token_id, text, target in requested:
        original = original_by_id[token_id]
        expected_x = (original["x_px"] + original["right_px"]) / 2 - x0
        expected_y = (original["y_px"] + original["bottom_px"]) / 2 - y0
        choices = sorted(by_text.get(text.casefold(), []), key=lambda token: abs(token.x + token.width / 2 - expected_x) + abs(token.center_y - expected_y))
        match = choices[0] if choices else None
        if match is None:
            output.append({"token_id": token_id, "text": text, "status": "removed_or_not_reemitted_by_crop"})
            continue
        variant_id = f"token-{match.source_row:04d}"
        candidate_ids = variant_candidates.get(variant_id, [])
        state = "unassigned" if not candidate_ids else "ambiguous" if len(candidate_ids) > 1 else "uniquely_assigned"
        if target == "one_visible_row":
            target_members = next(ids for (fid, pside, _), ids in study.KNOWN_VISIBLE_LINES.items()
                                  if fid == fixture_id and pside == side and token_id in ids)
            target_members = [item for item in target_members if item != token_id]
        elif target:
            target_members = original_lines.get(target, [])
        else:
            target_members = []
        mapped_members = map_original_tokens(page, target_members, tokens, crop_info) if target_members else []
        target_repaired = None
        if target_members and mapped_members is not None and len(candidate_ids) == 1:
            target_repaired = all(variant_candidates.get(member, []) == candidate_ids for member in mapped_members)
        output.append({"token_id": token_id, "text": text, "status": state,
                       "variant_token_id": variant_id, "candidate_line_ids": candidate_ids,
                       "human_target": target, "target_group_member_count": len(target_members),
                       "target_line_repaired": target_repaired})
    return output


def line_merge_audit(baseline, candidate, tokens, page=None, crop_info=None):
    source_line = study.partitions(baseline)
    if crop_info is not None and page is not None:
        mapped_source_line = {}
        for source_id, baseline_line_id in source_line.items():
            mapped = map_original_token(page, source_id, tokens, crop_info)
            if mapped is not None:
                mapped_source_line[f"token-{mapped.source_row:04d}"] = baseline_line_id
        source_line = mapped_source_line
    by_id = {f"token-{token.source_row:04d}": token for token in tokens}
    import normalize.geometry as production_geometry
    gap_limit = production_geometry._horizontal_gap_limit(tokens)
    mixed, suspicious = [], []
    for line in candidate["lines"]:
        source_ids = sorted({source_line[token_id] for token_id in line["token_ids"] if token_id in source_line})
        if len(source_ids) < 2:
            continue
        ordered = sorted((by_id[token_id] for token_id in line["token_ids"] if token_id in by_id), key=lambda token: token.x)
        max_gap = max((right.x - left.x1 for left, right in zip(ordered, ordered[1:])), default=0)
        y_spread = max((token.center_y for token in ordered), default=0) - min((token.center_y for token in ordered), default=0)
        audit = {"candidate_line_id": line["line_id"], "baseline_line_ids": source_ids,
                 "token_ids": line["token_ids"], "max_adjacent_box_gap_px": max_gap,
                 "gap_limit_px": gap_limit, "center_y_spread_px": y_spread,
                 "suspicious_cross_region": max_gap > gap_limit or y_spread > 1.5 * median(token.height for token in tokens)}
        mixed.append(audit)
        if audit["suspicious_cross_region"]:
            suspicious.append(audit)
    return {"new_line_merge_count": len(mixed), "suspicious_merge_count": len(suspicious),
            "new_line_merges": mixed, "suspicious_merges": suspicious}


def main():
    forensic = json.loads((HERE / "results.json").read_text(encoding="utf-8"))
    pages = study.load_corpus()
    crop_data = {}
    for page in pages:
        key = f"{page['fixture_id']}/{page['side']}"
        crop_data[key] = {}
        for kind in ("uniform_2pct_crop", "automatic_page_edge_crop_mask"):
            crop_data[key][kind] = crop_experiment(page, kind)

    factorial = {name: [] for name in (
        "baseline", "vertical_only", "oversized_disabled_only", "crop_mask_only",
        "vertical_plus_oversized", "vertical_plus_crop", "oversized_plus_crop", "all_three"
    )}
    tolerance_sweep = []
    bridge_guard_comparison = []
    for page, evidence in zip(pages, forensic["pages"]):
        fid, side, tokens = page["fixture_id"], page["side"], page["tokens"]
        slope = evidence["slope_search"]["best_nonzero_unconstrained"]["slope"]
        crop_tokens = crop_data[f"{fid}/{side}"]["automatic_page_edge_crop_mask"]["tokens"]
        crop_results = crop_data[f"{fid}/{side}"]["automatic_page_edge_crop_mask"]
        scenarios = {
            "baseline": (tokens, None, "current"),
            "vertical_only": (tokens, slope, "current"),
            "oversized_disabled_only": (tokens, None, "disabled"),
            "crop_mask_only": (crop_tokens, None, "current"),
            "vertical_plus_oversized": (tokens, slope, "disabled"),
            "vertical_plus_crop": (crop_tokens, slope, "current"),
            "oversized_plus_crop": (crop_tokens, None, "disabled"),
            "all_three": (crop_tokens, slope, "disabled"),
        }
        baseline = study.run_grouping(tokens)
        for guard_mode in ("current", "four_median_widths", "disabled"):
            guard_grouping = study.run_grouping(tokens, oversized=guard_mode)
            merges = line_merge_audit(baseline, guard_grouping, tokens)
            bridge_guard_comparison.append({"fixture_id": fid, "side": side, "guard": guard_mode,
                                            **page_stats(tokens, guard_grouping),
                                            "known_false_splits_repaired": known_repairs(page, guard_grouping, tokens),
                                            "clean_control_lines_damaged": clean_control_damage(fid, side, guard_grouping, tokens),
                                            **merges})
        for name, (variant_tokens, forced_slope, oversized) in scenarios.items():
            grouping = study.run_grouping(variant_tokens, slope=forced_slope, oversized=oversized)
            stats = page_stats(variant_tokens, grouping)
            crop_info_for_variant = crop_results["raster"] if name in {"crop_mask_only", "vertical_plus_crop", "oversized_plus_crop", "all_three"} else None
            merge_audit = line_merge_audit(baseline, grouping, variant_tokens, page, crop_info_for_variant)
            stat = {"fixture_id": fid, "side": side, **stats,
                    "known_false_splits_repaired": known_repairs(page, grouping, variant_tokens, crop_results["raster"] if name in {"crop_mask_only", "vertical_plus_crop", "oversized_plus_crop", "all_three"} else None),
                    "clean_control_lines_damaged": clean_control_damage(fid, side, grouping, variant_tokens, crop_results["raster"] if name in {"crop_mask_only", "vertical_plus_crop", "oversized_plus_crop", "all_three"} else None),
                    "new_line_merge_count": merge_audit["new_line_merge_count"],
                    "suspicious_new_merges": merge_audit["suspicious_merges"],
                    "likely_edge_noise_tokens": sum(len(p["baseline_boxes_affected_by_treatment"]) for p in [crop_results]) if name in {"crop_mask_only", "vertical_plus_crop", "oversized_plus_crop", "all_three"} else 0,
                    "visible_whole_line_omissions_from_tesseract": (
                        ["stella_maris_pdf06_dense-dialogue/left:y~846"]
                        if fid == "stella_maris_pdf06_dense-dialogue" and side == "left"
                        and not (name in {"crop_mask_only", "vertical_plus_crop", "oversized_plus_crop", "all_three"}
                                 and crop_results["stella_reported_missing_row_tokens"])
                        else [])}
            factorial[name].append(stat)
        for tolerance in (2, 4, 6, 8, 10):
            grouping = study.run_grouping(tokens, tolerance=tolerance)
            tolerance_sweep.append({"fixture_id": fid, "side": side, "tolerance_px": tolerance,
                                    **page_stats(tokens, grouping),
                                    "known_false_splits_repaired": known_repairs(page, grouping, tokens),
                                    "clean_control_lines_damaged": clean_control_damage(fid, side, grouping, tokens),
                                    "suspicious_new_merges": line_merge_audit(baseline, grouping, tokens)["suspicious_merges"]})

    edge_reports = {}
    for page in pages:
        fid, side = page["fixture_id"], page["side"]
        if (fid, side) not in {("relativity_pdf10_pp26-27", "left"), ("relativity_pdf17_pp40-41", "right"),
                               ("relativity_pdf23_pp52-53", "left"), ("relativity_pdf23_pp52-53", "right")}:
            continue
        auto = crop_data[f"{fid}/{side}"]["automatic_page_edge_crop_mask"]
        edge_reports[f"{fid}/{side}"] = {
            "admitted_tokens": len(page["tokens"]),
            "detected_pixel_edge_features": auto["raster"]["detected_features"],
            "likely_edge_tokens_affected_by_pixel_treatment": auto["baseline_boxes_affected_by_treatment"],
            "source_page_stats": page_stats(page["tokens"], study.run_grouping(page["tokens"])),
            "with_treatment_stats": auto["geometry"],
            "physical_lines_consisting_only_of_affected_tokens": [],
        }
        affected = {item["token_id"] for item in auto["baseline_boxes_affected_by_treatment"]}
        baseline = study.run_grouping(page["tokens"])
        kept = [token for token in page["tokens"] if f"token-{token.source_row:04d}" not in affected]
        edge_reports[f"{fid}/{side}"]["excluding_affected_tokens_stats"] = page_stats(kept, study.run_grouping(kept))
        for line in baseline["lines"]:
            if line["token_ids"] and set(line["token_ids"]) <= affected:
                edge_reports[f"{fid}/{side}"]["physical_lines_consisting_only_of_affected_tokens"].append(line["line_id"])

    residual_tracking = {}
    for name, entries in factorial.items():
        residual_tracking[name] = []
        for page, entry in zip(pages, entries):
            if (page["fixture_id"], page["side"]) not in RESIDUALS:
                continue
            crop = crop_data[f"{page['fixture_id']}/{page['side']}"]["automatic_page_edge_crop_mask"] if name in {"crop_mask_only", "vertical_plus_crop", "oversized_plus_crop", "all_three"} else None
            variant_tokens = crop["tokens"] if crop else page["tokens"]
            forced_slope = next(p["slope_search"]["best_nonzero_unconstrained"]["slope"] for p in forensic["pages"] if p["fixture_id"]==page["fixture_id"] and p["side"]==page["side"]) if name in {"vertical_only", "vertical_plus_oversized", "vertical_plus_crop", "all_three"} else None
            oversized = "disabled" if "oversized" in name or name == "all_three" else "current"
            group = study.run_grouping(variant_tokens, slope=forced_slope, oversized=oversized)
            crop_info = crop["raster"] if crop else None
            residual_tracking[name].extend([{"fixture_id": page["fixture_id"], "side": page["side"], **row}
                                            for row in residual_states(page, variant_tokens, group, crop_info)])

    def aggregate(entries):
        return {"page_count": len(entries), "admitted_tokens": sum(x["admitted_tokens"] for x in entries),
                "resolved_tokens": sum(x["resolved_tokens"] for x in entries),
                "residual_count": sum(x["residual_tokens"] for x in entries),
                "physical_line_count": sum(x["physical_lines"] for x in entries),
                "known_false_splits_repaired": sum(sum(value is True for value in x["known_false_splits_repaired"].values()) for x in entries),
                "clean_control_lines_damaged": sum(len(x["clean_control_lines_damaged"]) for x in entries),
                "new_line_merge_count": sum(x.get("new_line_merge_count", 0) for x in entries),
                "suspicious_merge_count": sum(len(x["suspicious_new_merges"]) for x in entries),
                "likely_edge_noise_tokens": sum(x["likely_edge_noise_tokens"] for x in entries)}
    result = {
        "crop_treatment_pages": {key: {kind: {k:v for k,v in value.items() if k != "tokens"} for kind,value in treatments.items()}
                                  for key,treatments in crop_data.items()},
        "edge_noise_pages": edge_reports,
        "factorial": {name: {"aggregate": aggregate(entries), "pages": entries} for name,entries in factorial.items()},
        "vertical_tolerance_sweep": tolerance_sweep,
        "bridge_guard_comparison": bridge_guard_comparison,
        "residual_tracking": residual_tracking,
    }
    forensic.update(result)
    # Avoid serializing the transient in-memory OCR token objects.
    (HERE / "results.json").write_text(json.dumps(forensic, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"factorial": {name: block["aggregate"] for name,block in result["factorial"].items()},
                      "edge_noise_pages": {k: {"treatment": v["detected_pixel_edge_features"], "affected_tokens": len(v["likely_edge_tokens_affected_by_pixel_treatment"]), "after": v["with_treatment_stats"]} for k,v in edge_reports.items()}}, indent=2))


if __name__ == "__main__":
    main()
