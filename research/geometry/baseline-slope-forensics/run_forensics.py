"""Capture current fixture OCR once, then instrument the unchanged slope search.

Raster and TSV files belong under the caller's temporary work directory. The
checked-in output is deliberately summary JSON only; page pixels remain local.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict
from pathlib import Path
from statistics import median
from typing import Any

from PIL import Image
import pytesseract
from pytesseract import Output

from normalize.fixtures import FixtureCatalog
from normalize.geometry import (
    _Token,
    _adjusted_center_y,
    _estimate_baseline_slope,
    _horizontal_gap_limit,
    _horizontally_adjacent,
    _line_bands,
    _split_horizontal_regions,
    group_physical_lines,
    parse_tsv_rows,
)
from normalize.rendering import SUCCESS, preprocess_fixture


ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "fixtures" / "preprocessing.json"
FIXTURE_IDS = (
    "relativity_pdf10_pp26-27",
    "relativity_pdf17_pp40-41",
    "relativity_pdf23_pp52-53",
    "stella_maris_pdf03_session-I",
    "stella_maris_pdf06_dense-dialogue",
    "stella_maris_pdf18_session-II_p35",
)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_digest(value: Any) -> str:
    return sha256_bytes(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    )


def capture(work_dir: Path) -> dict[str, Any]:
    """Run production preprocessing and exactly one Tesseract TSV call per side."""

    catalog = FixtureCatalog.load(ROOT)
    sides: list[dict[str, Any]] = []
    for fixture_id in FIXTURE_IDS:
        fixture_dir = work_dir / fixture_id
        fixture_dir.mkdir(parents=True, exist_ok=True)
        metadata = preprocess_fixture(catalog.get(fixture_id), CONFIG, fixture_dir)
        if metadata.get("status") != SUCCESS:
            raise RuntimeError(f"preprocessing failed for {fixture_id}: {metadata}")
        source_pdf = catalog.get(fixture_id).source_pdf
        for page_record in metadata["pages"]:
            side = page_record["side"]
            image_path = fixture_dir / metadata["output_files"][side]
            with Image.open(image_path) as image:
                image.load()
                width, height = image.size
                # This is the only OCR call made for this production side.
                tsv = pytesseract.image_to_data(image, output_type=Output.STRING)
            tsv_bytes = tsv.encode("utf-8")
            tokens, parse_errors = parse_tsv_rows(tsv, width, height)
            token_records = [asdict(token) for token in tokens]
            record = {
                "fixture_id": fixture_id,
                "side": side,
                "blank_declared": bool(page_record.get("blank", False)),
                "dimensions_px": [width, height],
                "source_pdf_sha256": sha256_file(source_pdf),
                "image_sha256": sha256_file(image_path),
                "tsv_sha256": sha256_bytes(tsv_bytes),
                "admitted_token_sha256": canonical_digest(token_records),
                "token_count": len(tokens),
                "tokens": token_records,
                "parse_errors": parse_errors,
                "tolerance_px": max(1, math.floor(median(t.height for t in tokens) / 4 + 0.5)) if tokens else None,
                "horizontal_gap_limit_px": _horizontal_gap_limit(tokens),
                "local_paths": {
                    "image": str(image_path),
                    "tsv": str(fixture_dir / f"{fixture_id}.{side}.tsv"),
                },
            }
            Path(record["local_paths"]["tsv"]).write_bytes(tsv_bytes)
            sides.append(record)
    result = {
        "schema": "baseline-slope-capture-v1",
        "fixtures": list(FIXTURE_IDS),
        "sides": sides,
    }
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "capture.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def instrumented_bands(
    tokens: list[_Token], tolerance: int, slope: float
) -> tuple[list[list[_Token]], list[list[_Token]]]:
    """Mirror production band formation and expose pre-horizontal-split bands."""

    ordered = sorted(
        tokens,
        key=lambda token: (_adjusted_center_y(token, slope), token.x, token.source_row),
    )
    raw_bands: list[list[_Token]] = []
    gap_limit = _horizontal_gap_limit(tokens)
    for token in ordered:
        if raw_bands:
            current_median = median(_adjusted_center_y(item, slope) for item in raw_bands[-1])
            median_support = abs(_adjusted_center_y(token, slope) - current_median) <= tolerance
            neighbor_support = any(
                abs(_adjusted_center_y(token, slope) - _adjusted_center_y(item, slope)) <= tolerance
                and _horizontally_adjacent(item, token, gap_limit)
                for item in raw_bands[-1]
            )
            if median_support or neighbor_support:
                raw_bands[-1].append(token)
                continue
        raw_bands.append([token])
    regions = _split_horizontal_regions(raw_bands, gap_limit)
    assert regions == _line_bands(tokens, tolerance, slope)
    return raw_bands, regions


def analyze(capture_record: dict[str, Any]) -> dict[str, Any]:
    """Run all 201 candidates over the fixed token capture and verify baseline."""

    output_sides: list[dict[str, Any]] = []
    for captured in capture_record["sides"]:
        tokens = [_Token(**item) for item in captured["tokens"]]
        tolerance = captured["tolerance_px"]
        if not tokens:
            output_sides.append({**{k: v for k, v in captured.items() if k != "tokens"}, "candidates": [], "selected_slope": 0.0})
            continue
        zero_bands = _line_bands(tokens, tolerance, 0.0)
        zero_score = sum(len(band) * (len(band) - 1) // 2 for band in zero_bands)
        candidate_records: list[dict[str, Any]] = []
        survivors: list[dict[str, Any]] = []
        for slope_milli in range(-100, 101):
            slope = slope_milli / 1000
            raw_bands, regions = instrumented_bands(tokens, tolerance, slope)
            score = sum(len(region) * (len(region) - 1) // 2 for region in regions)
            singletons = [region for region in regions if len(region) < 2]
            multi = [region for region in regions if len(region) >= 2]
            reasons: list[str] = []
            if slope != 0.0 and len(regions) < 2:
                reasons.append("fewer_than_two_regions")
            if slope != 0.0 and singletons:
                reasons.append("singleton_region_present")
            if slope != 0.0 and score <= zero_score:
                reasons.append("cohesion_not_strictly_above_zero")
            admissible = slope == 0.0 or not reasons
            record = {
                "slope": slope,
                "region_count": len(regions),
                "raw_band_count": len(raw_bands),
                "horizontal_split_count": len(raw_bands) - len(regions),
                "memberships": [[token.source_row for token in region] for region in regions],
                "raw_band_memberships": [[token.source_row for token in band] for band in raw_bands],
                "singleton_count": len(singletons),
                "singleton_source_rows": [token.source_row for region in singletons for token in region],
                "multi_token_region_count": len(multi),
                "cohesion_score": score,
                "zero_slope_score": zero_score,
                "rejected": bool(reasons),
                "rejection_reasons": reasons,
                "would_beat_zero_without_gates": bool(slope != 0 and score > zero_score),
                "admissible": admissible,
            }
            candidate_records.append(record)
            if admissible:
                survivors.append(record)
        ranked = sorted(survivors, key=lambda item: (-item["cohesion_score"], abs(item["slope"])))
        for rank, item in enumerate(ranked, start=1):
            item["final_rank"] = rank
        selected = _estimate_baseline_slope(tokens, tolerance)
        expected = ranked[0]["slope"]
        assert selected == expected, (captured["fixture_id"], captured["side"], selected, expected)
        lines, unresolved, measurements = group_physical_lines(tokens)
        singleton_presence_rejections = [
            candidate for candidate in candidate_records
            if "singleton_region_present" in candidate["rejection_reasons"]
            and "fewer_than_two_regions" not in candidate["rejection_reasons"]
        ]
        singleton_only_rejections = [
            candidate for candidate in candidate_records
            if candidate["rejection_reasons"] == ["singleton_region_present"]
        ]
        output_sides.append({
            **{k: v for k, v in captured.items() if k != "tokens"},
            "candidates": candidate_records,
            "selected_slope": selected,
            "best_nonzero_by_raw_score": max(
                (item for item in candidate_records if item["slope"] != 0),
                key=lambda item: (item["cohesion_score"], -abs(item["slope"])),
            ),
            "singleton_presence_rejection_count": len(singleton_presence_rejections),
            "rejected_only_by_singleton_count": len(singleton_only_rejections),
            "singleton_only_candidates_that_score_above_zero": sum(item["would_beat_zero_without_gates"] for item in singleton_only_rejections),
            "line_count": len(lines),
            "ambiguous_source_rows": [item["token_source_row"] for item in unresolved if item["code"] == "ambiguous_line_assignment"],
            "unassigned_source_rows": [item["token_source_row"] for item in unresolved if item["code"] == "unassigned_line_assignment"],
            "measurements": measurements,
            "lines": lines,
            "unresolved": unresolved,
        })
    return {
        "schema": "baseline-slope-landscape-v1",
        "capture_schema": capture_record["schema"],
        "sides": output_sides,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--capture", action="store_true", help="run preprocessing and OCR once per side")
    parser.add_argument("--analyze", action="store_true", help="analyze already captured token TSVs only")
    args = parser.parse_args()
    if args.capture == args.analyze:
        parser.error("choose exactly one of --capture or --analyze")
    capture_path = args.work_dir / "capture.json"
    if args.capture:
        captured = capture(args.work_dir)
    else:
        captured = json.loads(capture_path.read_text(encoding="utf-8"))
    if args.capture:
        landscape = analyze(captured)
        (args.work_dir / "landscape.json").write_text(json.dumps(landscape, indent=2), encoding="utf-8")
        print(f"captured {len(captured['sides'])} sides; landscape: {args.work_dir / 'landscape.json'}")
    else:
        landscape = analyze(captured)
        (args.work_dir / "landscape.json").write_text(json.dumps(landscape, indent=2), encoding="utf-8")
        print(f"analyzed captured sides; landscape: {args.work_dir / 'landscape.json'}")


if __name__ == "__main__":
    main()
