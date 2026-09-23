"""Produce bounded, source-independent diagnostics for Slice 2 geometry.

This module imports the existing implementation only to observe it.  It does
not patch thresholds or replace any production predicate.  The generated JSON
keeps bounding-box evidence, synthetic pixel evidence, current assignments,
and physical interpretations in separate fields.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from statistics import median
from typing import Any

from PIL import Image, ImageDraw

RESEARCH_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = RESEARCH_ROOT.parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))

import normalize.geometry as geometry
from normalize.geometry import TSV_HEADER, group_physical_lines, parse_tsv_rows
from tests.geometry_oracle import canonical_geometry_state


RESIDUAL_ROOT = REPOSITORY_ROOT / "research" / "geometry" / "residual-forensics"


def _row(
    text: str,
    *,
    x: int,
    y: int,
    width: int,
    height: int = 10,
    word: int,
    line: int = 1,
) -> str:
    return "\t".join(
        map(str, (5, 1, 1, 1, line, word, x, y, width, height, 95, text))
    )


def _parse(rows: list[str], *, width: int = 500, height: int = 200):
    tsv = "\t".join(TSV_HEADER) + "\n" + "\n".join(rows) + "\n"
    tokens, errors = parse_tsv_rows(tsv, width, height)
    if errors:
        raise AssertionError(errors)
    return tokens


def _jsonable(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


def _state_digest(state: tuple[Any, ...]) -> str:
    encoded = json.dumps(_jsonable(state), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _assignment_rows(state: tuple[Any, ...]) -> list[dict[str, Any]]:
    return [
        {
            "identity": list(item[0]),
            "text": item[1],
            "assignment": item[2],
            "candidate_lines": list(item[3]),
            "uncertainty": item[4],
        }
        for item in state[0]
    ]


def _run_case(case: dict[str, Any]) -> dict[str, Any]:
    tokens = _parse(case["rows"])
    result = group_physical_lines(tokens)
    state = canonical_geometry_state(case["case_id"], "synthetic", tokens, *result)
    permuted = canonical_geometry_state(
        case["case_id"],
        "synthetic",
        list(reversed(tokens)),
        *group_physical_lines(list(reversed(tokens))),
    )
    if state != permuted:
        raise AssertionError(f"identity-complete oracle detected permutation drift in {case['case_id']}")
    return {
        **case,
        "bbox_parameters": {
            "token_count": len(tokens),
            "token_boxes": [
                {
                    "identity": [case["case_id"], "synthetic", token.source_row],
                    "text": token.text,
                    "x": token.x,
                    "y": token.y,
                    "width": token.width,
                    "height": token.height,
                }
                for token in tokens
            ],
            "horizontal_gap_limit_px": result[2]["horizontal_gap_limit_px"],
            "oversized_width_threshold_px": result[2]["horizontal_gap_limit_px"] * 1.5,
        },
        "current_output": {
            "physical_lines": result[0],
            "unresolved": result[1],
            "measurements": result[2],
            "identity_complete_assignments": _assignment_rows(state),
        },
        "oracle": {
            "state_sha256": _state_digest(state),
            "permuted_input_same": state == permuted,
        },
    }


def _horizontal_cases() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "one_ordinary_token_each_side",
            "rows": [
                _row("left", x=10, y=20, width=10, word=1),
                _row("ocr-wide", x=20, y=20, width=130, word=2),
                _row("right", x=150, y=20, width=10, word=3),
            ],
            "pixel_evidence": "synthetic central print may be continuous, but only one ordinary box is observed on each side",
            "physical_interpretation": "Bounding boxes alone do not license a bridge; the wide box is insufficiently supported.",
            "expected_failure_mode": "false split if pixels show one continuous printed line; justified abstention if the gap is visibly blank",
        },
        {
            "case_id": "one_sided_left_support",
            "rows": [
                _row("left-a", x=10, y=20, width=10, word=1),
                _row("left-b", x=25, y=20, width=10, word=2),
                _row("ocr-wide", x=30, y=20, width=115, word=3),
            ],
            "pixel_evidence": "one ordinary component precedes the wide rectangle; no ordinary component follows it",
            "physical_interpretation": "The wide box can remain adjacent to the left region but cannot establish a two-sided bridge.",
            "expected_failure_mode": "no bridge claim is licensed; continuation beyond the wide box is unknown",
        },
        {
            "case_id": "one_sided_right_support",
            "rows": [
                _row("ocr-wide", x=20, y=20, width=115, word=1),
                _row("right-a", x=135, y=20, width=10, word=2),
                _row("right-b", x=150, y=20, width=10, word=3),
            ],
            "pixel_evidence": "no ordinary component precedes the wide rectangle; one ordinary component follows it",
            "physical_interpretation": "A one-sided box cannot establish continuity through the rectangle.",
            "expected_failure_mode": "current left-to-right region construction can split the wide box from the right token",
        },
        {
            "case_id": "two_ordinary_tokens_each_side",
            "rows": [
                _row("left-a", x=10, y=20, width=10, word=1),
                _row("left-b", x=25, y=20, width=10, word=2),
                _row("ocr-wide", x=30, y=20, width=115, word=3),
                _row("right-a", x=145, y=20, width=10, word=4),
                _row("right-b", x=160, y=20, width=10, word=5),
            ],
            "pixel_evidence": "two ordinary boxes are present on both sides; their pixels may still be continuous or disconnected",
            "physical_interpretation": "The current predicate treats two-sided ordinary support as sufficient geometric bridge evidence.",
            "expected_failure_mode": "false merge when the wide OCR box spans a genuinely blank or disconnected region",
        },
        {
            "case_id": "genuine_long_printed_word",
            "rows": [
                _row("left", x=10, y=20, width=10, word=1),
                _row("longword", x=20, y=20, width=100, word=2),
                _row("right", x=120, y=20, width=10, word=3),
            ],
            "pixel_evidence": "the wide rectangle corresponds to one genuinely long printed word, not an OCR span over a gap",
            "physical_interpretation": "A long word should remain part of one physical line when neighboring word boxes are collinear.",
            "expected_failure_mode": "false split because a wide word is not admitted as a supported bridge with only one ordinary token per side",
        },
        {
            "case_id": "ocr_rectangle_over_disconnected_regions",
            "rows": [
                _row("left-a", x=10, y=20, width=10, word=1),
                _row("left-b", x=25, y=20, width=10, word=2),
                _row("ocr-wide", x=30, y=20, width=115, word=3),
                _row("right-a", x=145, y=20, width=10, word=4),
                _row("right-b", x=160, y=20, width=10, word=5),
            ],
            "pixel_evidence": "ordinary printed regions are disconnected; the wide OCR rectangle is the only evidence across the blank interval",
            "physical_interpretation": "Pixel evidence contradicts the box-only bridge inference; this is a false-merge counterexample.",
            "expected_failure_mode": "current output is one line despite absent pixel continuity",
        },
        {
            "case_id": "sparse_visibly_continuous_line",
            "rows": [
                _row("left", x=10, y=20, width=10, word=1),
                _row("ocr-wide", x=20, y=20, width=130, word=2),
                _row("right", x=150, y=20, width=10, word=3),
            ],
            "pixel_evidence": "a thin visible printed stroke crosses the central interval, but OCR emits one wide rectangle and only one ordinary token on each side",
            "physical_interpretation": "Pixels support continuity, while the current box predicate abstains; this is a false-split counterexample.",
            "expected_failure_mode": "current output remains split; do not loosen the bridge rule solely from this case",
        },
    ]


def _draw_pixels(case: dict[str, Any], output: Path) -> None:
    image = Image.new("RGB", (220, 70), "white")
    draw = ImageDraw.Draw(image)
    boxes = case["rows"]
    # The synthetic images are intentionally schematic: black marks are pixel
    # evidence, while blue outlines show the independent OCR boxes.
    for row in boxes:
        fields = row.split("\t")
        x, y, width, height = map(int, fields[6:10])
        text = fields[-1]
        if text == "ocr-wide":
            continue
        draw.rectangle((x, y + 3, x + width, y + height - 2), fill=(25, 25, 25))
    if case["case_id"] == "sparse_visibly_continuous_line":
        draw.line((20, 25, 150, 25), fill=(25, 25, 25), width=3)
    if case["case_id"] == "genuine_long_printed_word":
        draw.rectangle((20, 23, 120, 27), fill=(25, 25, 25))
    for row in boxes:
        fields = row.split("\t")
        x, y, width, height = map(int, fields[6:10])
        draw.rectangle((x, y, x + width, y + height), outline=(35, 100, 210), width=1)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)


def _token_from_record(record: dict[str, Any]) -> geometry._Token:
    evidence = record["evidence_only"]
    return geometry._Token(
        record["source_row"],
        record["text"],
        record["confidence"],
        5,
        1,
        evidence["tesseract_block_num"],
        evidence["tesseract_par_num"],
        evidence["tesseract_line_num"],
        evidence["tesseract_word_num"],
        record["x_px"],
        record["y_px"],
        record["width_px"],
        record["height_px"],
    )


def _raw_vertical_bands(
    tokens: list[geometry._Token], tolerance: int, slope: float
) -> list[list[geometry._Token]]:
    """Reproduce only the pre-horizontal-split greedy band pass for evidence."""

    ordered = sorted(
        tokens,
        key=lambda token: (
            geometry._adjusted_center_y(token, slope),
            token.x,
            token.source_row,
        ),
    )
    bands: list[list[geometry._Token]] = []
    gap_limit = geometry._horizontal_gap_limit(tokens)
    for token in ordered:
        if bands:
            current_median = median(
                geometry._adjusted_center_y(item, slope) for item in bands[-1]
            )
            median_support = (
                abs(geometry._adjusted_center_y(token, slope) - current_median)
                <= tolerance
            )
            neighbor_support = any(
                abs(
                    geometry._adjusted_center_y(token, slope)
                    - geometry._adjusted_center_y(item, slope)
                )
                <= tolerance
                and geometry._horizontally_adjacent(item, token, gap_limit)
                for item in bands[-1]
            )
            if median_support or neighbor_support:
                bands[-1].append(token)
                continue
        bands.append([token])
    return bands


def _vertical_trace(page: dict[str, Any], fixture_id: str) -> dict[str, Any]:
    tokens = [_token_from_record(record) for record in page["tokens"]]
    residual_rows = {record["source_row"] for record in page["tokens"] if record["physical_line_id"] is None}
    tolerance = max(1, int(median(token.height for token in tokens) / 4 + 0.5))
    slope = geometry._estimate_baseline_slope(tokens, tolerance)
    raw_bands = _raw_vertical_bands(tokens, tolerance, slope)
    bands = geometry._line_bands(tokens, tolerance, slope)
    gap_limit = geometry._horizontal_gap_limit(tokens)
    ordered = sorted(
        enumerate(bands),
        key=lambda pair: (
            median(geometry._adjusted_center_y(item, slope) for item in pair[1]),
            min(item.x for item in pair[1]),
            pair[0],
        ),
    )
    line_ids = {
        band_index: f"line-{ordinal:04d}"
        for ordinal, (band_index, _band) in enumerate(ordered, start=1)
    }
    lines, unresolved, measurements = group_physical_lines(tokens)
    unresolved_by_row = {item["token_source_row"]: item for item in unresolved}
    traces = []
    for token in tokens:
        if token.source_row not in residual_rows:
            continue
        adjusted = geometry._adjusted_center_y(token, slope)
        raw_band_index = next(index for index, band in enumerate(raw_bands) if token in band)
        raw_band = raw_bands[raw_band_index]
        raw_band_median = median(
            geometry._adjusted_center_y(item, slope) for item in raw_band
        )
        band_summaries = []
        provisional_band = None
        for band_index, band in ordered:
            line_id = line_ids[band_index]
            band_median = median(geometry._adjusted_center_y(item, slope) for item in band)
            delta = abs(adjusted - band_median)
            in_band = token in band
            median_support = delta <= tolerance
            neighbor_support = any(
                abs(adjusted - geometry._adjusted_center_y(item, slope)) <= tolerance
                and geometry._horizontally_adjacent(item, token, gap_limit)
                for item in band
                if item is not token
            )
            interval_support = min(item.x for item in band) <= token.x <= max(item.x1 for item in band)
            horizontal_support = geometry._horizontal_candidate_supported(band, token, gap_limit)
            provisional = in_band
            if provisional:
                provisional_band = line_id
            first_clause = in_band and (median_support or neighbor_support)
            second_clause = median_support and interval_support and horizontal_support
            accepted = first_clause or second_clause
            if accepted:
                exclusion = None
            elif not median_support:
                exclusion = "adjusted_center_outside_tolerance"
            elif not interval_support:
                exclusion = "x_outside_band_extent"
            elif not horizontal_support:
                exclusion = "horizontal_candidate_guard_rejected"
            else:
                exclusion = "not_in_provisional_band"
            band_summaries.append(
                {
                    "line_id": line_id,
                    "source_rows": [item.source_row for item in band],
                    "band_adjusted_center_median": band_median,
                    "token_adjusted_center": adjusted,
                    "absolute_delta": delta,
                    "in_provisional_band": in_band,
                    "median_support": median_support,
                    "neighbor_support": neighbor_support,
                    "x_interval_support": interval_support,
                    "horizontal_candidate_support": horizontal_support,
                    "accepted_by_first_clause": first_clause,
                    "accepted_by_second_clause": second_clause,
                    "accepted": accepted,
                    "exclusion": exclusion,
                }
            )
        traces.append(
            {
                "identity": [fixture_id, page["side"], token.source_row],
                "text": token.text,
                "box": {"x": token.x, "y": token.y, "width": token.width, "height": token.height},
                "adjusted_center_y": adjusted,
                "tolerance_px": tolerance,
                "baseline_slope_px_per_px": slope,
                "horizontal_gap_limit_px": gap_limit,
                "raw_greedy_band": {
                    "band_id": f"raw-band-{raw_band_index + 1:04d}",
                    "source_rows": [item.source_row for item in raw_band],
                    "band_adjusted_center_median": raw_band_median,
                    "absolute_delta_after_band_growth": abs(adjusted - raw_band_median),
                },
                "provisional_band": provisional_band,
                "bands_considered": band_summaries,
                "final_reconciliation": {
                    "candidate_line_ids": unresolved_by_row.get(token.source_row, {}).get("candidate_line_ids", []),
                    "uncertainty": unresolved_by_row.get(token.source_row, {}).get("code"),
                    "serialized_physical_line_id": next(
                        record["physical_line_id"]
                        for record in page["tokens"]
                        if record["source_row"] == token.source_row
                    ),
                },
            }
        )
    return {
        "fixture_id": fixture_id,
        "side": page["side"],
        "tolerance_px": tolerance,
        "baseline_slope_px_per_px": slope,
        "horizontal_gap_limit_px": gap_limit,
        "band_count": len(ordered),
        "raw_greedy_band_count": len(raw_bands),
        "raw_greedy_bands": [
            {
                "band_id": f"raw-band-{index + 1:04d}",
                "source_rows": [item.source_row for item in band],
                "band_adjusted_center_median": median(
                    geometry._adjusted_center_y(item, slope) for item in band
                ),
            }
            for index, band in enumerate(raw_bands)
        ],
        "page_measurements": measurements,
        "physical_line_records": lines,
        "traces": traces,
    }


def _vertical_synthetic_cases() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "continuous_row",
            "rows": [
                _row("a", x=10, y=45, width=10, word=1),
                _row("b", x=30, y=45, width=10, word=2),
                _row("c", x=50, y=45, width=10, word=3),
            ],
            "interpretation": "same adjusted baseline and horizontal continuity support one physical row",
        },
        {
            "case_id": "nearby_distinct_rows",
            "rows": [
                _row("upper-a", x=10, y=15, width=10, word=1),
                _row("upper-b", x=30, y=15, width=10, word=2),
                _row("lower-a", x=10, y=40, width=10, word=3),
                _row("lower-b", x=30, y=40, width=10, word=4),
            ],
            "interpretation": "large adjusted-center separation and separate horizontal rows should remain distinct",
        },
        {
            "case_id": "legitimately_ambiguous_vertical_geometry",
            "rows": [
                _row("upper", x=10, y=15, width=10, word=1),
                _row("middle-a", x=10, y=20, width=10, word=2),
                _row("middle-b", x=10, y=21, width=10, word=3),
                _row("lower", x=10, y=24, width=10, word=4),
            ],
            "interpretation": "same-column near bands provide insufficient horizontal evidence; ambiguity or abstention is expected",
        },
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=RESEARCH_ROOT / "diagnostics.json")
    args = parser.parse_args()
    pixel_root = RESEARCH_ROOT / "pixel-cases"
    horizontal = []
    for case in _horizontal_cases():
        output = _run_case(case)
        _draw_pixels(case, pixel_root / f"{case['case_id']}.png")
        horizontal.append(output)

    vertical_synthetic = []
    for case in _vertical_synthetic_cases():
        tokens = _parse(case["rows"])
        result = group_physical_lines(tokens)
        state = canonical_geometry_state(case["case_id"], "synthetic", tokens, *result)
        permuted_tokens = list(reversed(tokens))
        permuted_state = canonical_geometry_state(
            case["case_id"], "synthetic", permuted_tokens, *group_physical_lines(permuted_tokens)
        )
        if state != permuted_state:
            raise AssertionError(f"identity-complete oracle detected permutation drift in {case['case_id']}")
        vertical_synthetic.append(
            {
                **case,
                "current_output": {
                    "physical_lines": result[0],
                    "unresolved": result[1],
                    "measurements": result[2],
                    "identity_complete_assignments": _assignment_rows(state),
                },
                "oracle": {
                    "state_sha256": _state_digest(state),
                    "permuted_input_same": state == permuted_state,
                },
            }
        )

    vertical_fixtures = []
    for fixture_id in ("relativity_pdf10_pp26-27", "relativity_pdf17_pp40-41"):
        geometry_path = RESIDUAL_ROOT / fixture_id / "geometry.json"
        payload = json.loads(geometry_path.read_text(encoding="utf-8"))
        for page in payload["pages"]:
            if any(token["physical_line_id"] is None for token in page["tokens"]):
                vertical_fixtures.append(_vertical_trace(page, fixture_id))

    observed_rel17 = {
        "identity": ["relativity_pdf17_pp40-41", "right", 23],
        "text": "A",
        "description": "Observed residual crop contains the end of 'lightning' and the token A; this is evidence, not a special-case specification.",
        "geometry_artifact": "research/geometry/residual-forensics/relativity_pdf17_pp40-41/geometry.json",
        "crop_artifact": "research/geometry/residual-forensics/relativity_pdf17_pp40-41/crops/right-row-0023-a.png",
        "current_state": "ambiguous_line_assignment",
        "candidate_line_ids": ["line-0003", "line-0004"],
    }
    report = {
        "schema": "normalize-diagnostic-investigation-v1",
        "authority": "Synthetic pixel evidence is illustrative; preserved scan-derived geometry remains the observed source evidence.",
        "horizontal_connectivity": horizontal,
        "vertical_fragmentation": {
            "synthetic_cases": vertical_synthetic,
            "fixture_traces": vertical_fixtures,
            "observed_rel17_lightning_A": observed_rel17,
        },
        "source_evidence_references": [
            "research/geometry/residual-forensics/relativity_pdf10_pp26-27/geometry.json",
            "research/geometry/residual-forensics/relativity_pdf17_pp40-41/geometry.json",
            "research/geometry/residual-forensics/residual-annotations.json",
        ],
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "horizontal_cases": len(horizontal), "vertical_fixture_traces": len(vertical_fixtures)}, indent=2))


if __name__ == "__main__":
    main()
