"""Research-only causal traces for Slice 2 geometry fragmentation.

The grouping calls delegate to the current production implementation. Research
variants inject only a slope/tolerance/oversized predicate into that process;
no production files or durable review artifacts are written.
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[3]
AUDIT = ROOT / "research/accuracy-audit"
REVIEW = AUDIT / "review"
OUTPUT = Path(__file__).resolve().parent / "results.json"
sys.path.insert(0, str(ROOT / "src"))
import normalize.geometry as geometry  # noqa: E402
import pytesseract  # noqa: E402
from pytesseract import Output  # noqa: E402

# These token groups come from the user's visual review and are positive
# controls, not geometry-derived labels.
KNOWN_VISIBLE_LINES = {
    ("relativity_pdf10_pp26-27", "left", "fragment-17-19"): [f"token-{i:04d}" for i in range(68, 74)],
    ("relativity_pdf10_pp26-27", "right", "fragment-53-55-plus-residual"): [
        *(f"token-{i:04d}" for i in range(238, 246)), "token-0246", "token-0247"
    ],
    ("relativity_pdf17_pp40-41", "right", "fragment-61-62"): [f"token-{i:04d}" for i in range(335, 345)],
}


def load_corpus() -> list[dict[str, Any]]:
    pages = []
    for path in sorted((REVIEW / "geometry").glob("*.geometry.json")):
        artifact = json.loads(path.read_text(encoding="utf-8"))
        fixture_id = artifact["fixture_id"]
        for page in artifact["pages"]:
            if page["blank"]:
                continue
            tokens = []
            for record in page["tokens"]:
                evidence = record["evidence_only"]
                tokens.append(geometry._Token(
                    source_row=int(record["token_id"].removeprefix("token-")),
                    text=record["text"], confidence=float(record["confidence"]), level=5,
                    page_num=1, block_num=evidence["tesseract_block_num"],
                    par_num=evidence["tesseract_par_num"], line_num=evidence["tesseract_line_num"],
                    word_num=evidence["tesseract_word_num"], x=record["x_px"], y=record["y_px"],
                    width=record["width_px"], height=record["height_px"],
                ))
            image_path = REVIEW / "preprocessed" / fixture_id / Path(page["image_path"]).name
            pages.append({
                "fixture_id": fixture_id, "side": page["side"], "record": page,
                "tokens": tokens, "image_path": image_path,
            })
    return pages


def cohesion(bands: list[list[Any]]) -> int:
    return sum(len(band) * (len(band) - 1) // 2 for band in bands)


def slope_candidates(tokens: list[Any], tolerance: int) -> dict[str, Any]:
    zero_bands = geometry._line_bands(tokens, tolerance, 0.0)
    zero_score = cohesion(zero_bands)
    rows = []
    best_any = (float("-inf"), 0.0)
    best_admissible = (float("-inf"), 0.0)
    for milli in range(-100, 101):
        slope = milli / 1000
        bands = geometry._line_bands(tokens, tolerance, slope)
        score = cohesion(bands)
        shape_ok = slope == 0 or (len(bands) >= 2 and all(len(band) >= 2 for band in bands))
        improves_zero = slope == 0 or score > zero_score
        accepted = shape_ok and improves_zero
        if (score, -abs(slope)) > (best_any[0], -abs(best_any[1])):
            best_any = (score, slope)
        if accepted and (score, -abs(slope)) > (best_admissible[0], -abs(best_admissible[1])):
            best_admissible = (score, slope)
        rows.append({
            "slope": slope, "cohesion": score, "band_count": len(bands),
            "multi_token_band_count": sum(len(band) >= 2 for band in bands),
            "singleton_band_count": sum(len(band) == 1 for band in bands),
            "admissible": accepted,
            "rejection": None if accepted else (
                "fewer_than_two_bands_or_singleton_band" if not shape_ok else "cohesion_not_above_zero_slope"
            ),
        })
    return {
        "zero_slope_cohesion": zero_score,
        "best_nonzero_unconstrained": {"slope": best_any[1], "cohesion": best_any[0]},
        "best_admissible": {"slope": best_admissible[1], "cohesion": best_admissible[0]},
        "selected_by_production": best_admissible[1],
        "candidates": rows,
    }


def clone_for_tolerance(tokens: list[Any], tolerance: int) -> list[Any]:
    """Change only the median-height-derived tolerance; preserve every center-Y."""
    result = []
    for token in tokens:
        center_y = token.center_y
        height = max(1, tolerance * 4)
        result.append(geometry._Token(
            token.source_row, token.text, token.confidence, token.level, token.page_num,
            token.block_num, token.par_num, token.line_num, token.word_num,
            token.x, center_y - height / 2, token.width, height,
        ))
    return result


def run_grouping(
    tokens: list[Any], *, tolerance: int | None = None, slope: float | None = None,
    oversized: str = "current",
) -> dict[str, Any]:
    original_estimator = geometry._estimate_baseline_slope
    original_oversized = geometry._is_oversized
    inputs = clone_for_tolerance(tokens, tolerance) if tolerance is not None else tokens
    try:
        if slope is not None:
            geometry._estimate_baseline_slope = lambda _tokens, _tolerance: slope
        if oversized == "disabled":
            geometry._is_oversized = lambda _token, _gap: False
        elif oversized == "four_median_widths":
            geometry._is_oversized = lambda token, gap: token.width > gap * 2
        lines, unresolved, measurements = geometry.group_physical_lines(inputs)
    finally:
        geometry._estimate_baseline_slope = original_estimator
        geometry._is_oversized = original_oversized
    token_candidates: dict[str, list[str]] = defaultdict(list)
    for line in lines:
        for token_id in line["token_ids"]:
            token_candidates[token_id].append(line["line_id"])
    for item in unresolved:
        token_candidates[f"token-{item['token_source_row']:04d}"] = item["candidate_line_ids"]
    return {
        "lines": lines, "unresolved": unresolved, "measurements": measurements,
        "token_candidates": dict(token_candidates),
    }


def partitions(grouping: dict[str, Any]) -> dict[str, str]:
    result = {}
    for line in grouping["lines"]:
        for token_id in line["token_ids"]:
            result[token_id] = line["line_id"]
    return result


def visible_line_repaired(grouping: dict[str, Any], token_ids: list[str]) -> bool:
    assigned = [grouping["token_candidates"].get(token_id, []) for token_id in token_ids]
    return bool(assigned) and all(len(ids) == 1 for ids in assigned) and len({ids[0] for ids in assigned}) == 1


def suspicious_merges(baseline: dict[str, Any], candidate: dict[str, Any], tokens: list[Any]) -> list[dict[str, Any]]:
    base_partition = partitions(baseline)
    by_id = {f"token-{token.source_row:04d}": token for token in tokens}
    merges = []
    for line in candidate["lines"]:
        base_lines = sorted({base_partition[token_id] for token_id in line["token_ids"] if token_id in base_partition})
        if len(base_lines) < 2:
            continue
        ys = [by_id[token_id].center_y for token_id in line["token_ids"] if token_id in by_id]
        if not ys:
            continue
        spread = max(ys) - min(ys)
        if spread > 2 * median(token.height for token in tokens):
            merges.append({"candidate_line_id": line["line_id"], "baseline_line_ids": base_lines,
                           "token_ids": line["token_ids"], "center_y_spread_px": spread})
    return merges


def instrument_page(page: dict[str, Any]) -> dict[str, Any]:
    tokens, artifact = page["tokens"], page["record"]
    tolerance = artifact["measurements"]["tolerance_px"]
    slope_trace = slope_candidates(tokens, tolerance)
    baseline = run_grouping(tokens, slope=slope_trace["selected_by_production"])
    # Ask the current production band/split functions to expose the exact
    # vertical input bands, then trace each horizontal decision from their
    # production outputs and the same guarded predicate calls.
    original_split = geometry._split_horizontal_regions
    split_trace: list[dict[str, Any]] = []
    def traced_split(bands, gap_limit):
        result = original_split(bands, gap_limit)
        bridge_ids = set()
        for band in bands:
            bridge_ids |= geometry._supported_bridge_ids(sorted(band, key=lambda item: (item.x, item.source_row)), gap_limit)
        for band_index, band in enumerate(bands):
            ordered = sorted(band, key=lambda item: (item.x, item.source_row))
            covered = None
            current = []
            row_splits = []
            for token in ordered:
                gap_before = None if not current or covered is None else token.x - covered
                if current and covered is not None and gap_before > gap_limit:
                    previous = current[-1]
                    previous_oversized = geometry._is_oversized(previous, gap_limit)
                    previous_supported = id(previous) in bridge_ids
                    actual_token_gap = token.x - previous.x1
                    row_splits.append({
                        "before_token": f"token-{token.source_row:04d}",
                        "after_token": f"token-{previous.source_row:04d}",
                        "covered_gap_px": gap_before, "actual_adjacent_token_gap_px": actual_token_gap,
                        "preceding_token_oversized": previous_oversized,
                        "preceding_token_supported_bridge": previous_supported,
                        "mechanism": "oversized_bridge_guard" if previous_oversized and not previous_supported else "horizontal_gap",
                        "predicate": "token.x - covered_right > gap_limit",
                    })
                    current = []
                current.append(token)
                is_over = geometry._is_oversized(token, gap_limit)
                supported = id(token) in bridge_ids
                if not is_over or supported:
                    covered = max(covered or token.x1, token.x1)
                elif covered is None:
                    covered = token.x
            split_trace.append({
                "vertical_band_index": band_index,
                "token_ids": [f"token-{item.source_row:04d}" for item in ordered],
                "median_center_y": float(median(item.center_y for item in band)),
                "median_support_and_neighbor_support": [
                    {
                        "token_id": f"token-{item.source_row:04d}",
                        "adjusted_center_y": geometry._adjusted_center_y(item, slope_trace["selected_by_production"]),
                        "distance_to_band_median": abs(geometry._adjusted_center_y(item, slope_trace["selected_by_production"]) - median(geometry._adjusted_center_y(other, slope_trace["selected_by_production"]) for other in band)),
                        "median_support": abs(geometry._adjusted_center_y(item, slope_trace["selected_by_production"]) - median(geometry._adjusted_center_y(other, slope_trace["selected_by_production"]) for other in band)) <= tolerance,
                        "neighbor_support": any(
                            other is not item
                            and abs(geometry._adjusted_center_y(item, slope_trace["selected_by_production"]) - geometry._adjusted_center_y(other, slope_trace["selected_by_production"])) <= tolerance
                            and geometry._horizontally_adjacent(other, item, gap_limit)
                            for other in band
                        ),
                    } for item in ordered
                ],
                "tokens": [{
                    "token_id": f"token-{item.source_row:04d}", "text": item.text,
                    "bbox": [item.x, item.y, item.x1, item.y1], "width": item.width,
                    "oversized": geometry._is_oversized(item, gap_limit),
                    "supported_bridge": id(item) in bridge_ids,
                    "extends_covered_right": not geometry._is_oversized(item, gap_limit) or id(item) in bridge_ids,
                } for item in ordered],
                "horizontal_splits": row_splits,
            })
        return result
    try:
        geometry._split_horizontal_regions = traced_split
        # Selection is fixed to the measured production slope so this invocation
        # exposes the production final grouping rather than searching again.
        original_estimator = geometry._estimate_baseline_slope
        geometry._estimate_baseline_slope = lambda _tokens, _tol: slope_trace["selected_by_production"]
        try:
            lines, unresolved, measurements = geometry.group_physical_lines(tokens)
        finally:
            geometry._estimate_baseline_slope = original_estimator
    finally:
        geometry._split_horizontal_regions = original_split
    final = {"lines": lines, "unresolved": unresolved, "measurements": measurements,
             "token_candidates": run_grouping(tokens, slope=slope_trace["selected_by_production"])["token_candidates"]}
    # Tesseract is rerun on unmodified source pixels with the recorded --psm 6
    # English TSV configuration. This is only to locate OCR-omitted visible lines.
    with Image.open(page["image_path"]) as opened:
        image = opened.convert("RGB")
        tsv = pytesseract.image_to_data(image, lang="eng", config="--psm 6", output_type=Output.STRING)
    raw_lines = []
    for row_number, line in enumerate(tsv.splitlines()[1:], start=1):
        cells = line.split("\t")
        if len(cells) != 12:
            continue
        try:
            y, height = int(cells[7]), int(cells[9])
        except ValueError:
            continue
        if page["fixture_id"] == "stella_maris_pdf06_dense-dialogue" and page["side"] == "left" and 820 <= y <= 930:
            raw_lines.append({"source_row": row_number, "text": cells[11], "left": int(cells[6]), "top": y,
                              "width": int(cells[8]), "height": height, "confidence": cells[10],
                              "level": cells[0], "block": cells[2], "par": cells[3], "line": cells[4], "word": cells[5]})
    oversized = []
    gap_limit = geometry._horizontal_gap_limit(tokens)
    for token in tokens:
        if geometry._is_oversized(token, gap_limit):
            oversized.append({"token_id": f"token-{token.source_row:04d}", "text": token.text,
                              "bbox": [token.x, token.y, token.x1, token.y1], "width_px": token.width,
                              "median_token_width_px": gap_limit / 2, "gap_limit_px": gap_limit,
                              "threshold_px": gap_limit * 1.5,
                              "kind": "ordinary_lexical_locator" if token.text.isalpha() or any(c.isalpha() for c in token.text) else "not_determinable_from_locator"})
    all_candidates = final["token_candidates"]
    for item in oversized:
        token_id = item["token_id"]
        item["candidate_line_ids"] = all_candidates.get(token_id, [])
    return {
        "fixture_id": page["fixture_id"], "side": page["side"],
        "image_path": str(page["image_path"].relative_to(ROOT)),
        "input_tokens": [{"token_id": f"token-{t.source_row:04d}", "text": t.text,
                          "bbox": [t.x, t.y, t.x1, t.y1], "confidence": t.confidence,
                          "initial_candidate_line_ids": artifact_token["candidate_line_ids"]}
                         for t, artifact_token in zip(tokens, artifact["tokens"])],
        "selected_slope_px_per_px": slope_trace["selected_by_production"],
        "slope_search": slope_trace,
        "tolerance_px": tolerance,
        "horizontal_gap_limit_px": gap_limit,
        "oversized_threshold_px": gap_limit * 1.5,
        "vertical_bands_and_horizontal_splits": split_trace,
        "final_lines": final["lines"], "final_unresolved": final["unresolved"],
        "final_token_candidates": final["token_candidates"],
        "oversized_tokens": oversized,
        "stella_missing_line_tsv_window": raw_lines,
    }


def diagnose_first_split_predicate(*, tesseract_emitted: bool, tsv_admitted: bool,
                                  selected_vertical_delta: float | None = None, tolerance: float | None = None,
                                  alternative_slope_delta: float | None = None,
                                  horizontal_gap: float | None = None, gap_limit: float | None = None,
                                  preceding_token_oversized: bool = False, bridge_supported: bool = False) -> str:
    """Name the earliest evidenced split stage for one visually shared row."""
    if not tesseract_emitted:
        return "ocr_observation_missing"
    if not tsv_admitted:
        return "tsv_admission_rejection"
    if selected_vertical_delta is not None and tolerance is not None and selected_vertical_delta > tolerance:
        if alternative_slope_delta is not None and alternative_slope_delta <= tolerance:
            return "baseline_slope_model"
        return "vertical_tolerance"
    if horizontal_gap is not None and gap_limit is not None and horizontal_gap > gap_limit:
        if preceding_token_oversized and not bridge_supported:
            return "oversized_bridge_guard"
        return "horizontal_gap"
    return "other"


def edge_removal_claim(*, pixel_boundary_supported: bool, token_removed: bool) -> dict[str, Any]:
    """Removal is an OCR observation change; pixel evidence is still needed for its label."""
    return {"removed": token_removed,
            "edge_noise_supported": bool(pixel_boundary_supported and token_removed),
            "geometry_correctness": "not_established"}


def observation_stage(*, tesseract_emitted: bool, tsv_admitted: bool, grouped: bool) -> str:
    """Keep absence at OCR, admission, and grouping as separate evidence states."""
    if not tesseract_emitted:
        return "ocr_observation_missing"
    if not tsv_admitted:
        return "tsv_admission_rejection"
    if not grouped:
        return "geometry_grouping_omission"
    return "grouped"


def main() -> None:
    pages = load_corpus()
    results = {"schema": "normalize-fragmentation-forensics-v1", "source_revision": "f55ab640db98a48767c612464579c66d5b1a1c1f",
               "tesseract_config": {"language": "eng", "config": "--psm 6", "output": "TSV"},
               "pages": [instrument_page(page) for page in pages]}
    OUTPUT.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"pages": len(results["pages"]), "admitted_tokens": sum(len(p["input_tokens"]) for p in results["pages"]),
                      "oversized_tokens": sum(len(p["oversized_tokens"]) for p in results["pages"]),
                      "output": str(OUTPUT)}, indent=2))


if __name__ == "__main__":
    main()
