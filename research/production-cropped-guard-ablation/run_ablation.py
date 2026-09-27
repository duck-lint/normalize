"""Run a paired oversized-extent ablation on current Slice 1 outputs.

The production preprocessing and OCR entry points are called unchanged. OCR
TSV is captured once per page, then both geometry variants consume the same
parsed token objects. The off variant changes only whether a token's true
right edge extends horizontal coverage; the production slope is fixed for
both calls so this experiment isolates that grouping treatment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from normalize import geometry, rendering  # noqa: E402
from normalize.fixtures import FixtureCatalog  # noqa: E402
from PIL import Image  # noqa: E402
import pytesseract  # noqa: E402


FIXTURES = (
    "relativity_pdf10_pp26-27",
    "relativity_pdf17_pp40-41",
    "relativity_pdf23_pp52-53",
    "stella_maris_pdf03_session-I",
    "stella_maris_pdf06_dense-dialogue",
    "stella_maris_pdf18_session-II_p35",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def line_groups(lines: list[dict[str, Any]]) -> list[set[int]]:
    return [
        {int(token_id.removeprefix("token-")) for token_id in line["token_ids"]}
        for line in lines
    ]


def token_memberships(
    tokens: list[geometry._Token],
    lines: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
) -> dict[int, tuple[tuple[int, ...], ...]]:
    by_line = {line["line_id"]: set(group) for line, group in zip(lines, line_groups(lines))}
    memberships: dict[int, list[tuple[int, ...]]] = defaultdict(list)
    for source_row, candidates in _candidate_rows(tokens, lines, unresolved).items():
        memberships[source_row] = [tuple(sorted(by_line[candidate])) for candidate in candidates if candidate in by_line]
    return {row: tuple(sorted(groups)) for row, groups in memberships.items()}


def _candidate_rows(tokens, lines, unresolved):
    result = {token.source_row: [] for token in tokens}
    for line in lines:
        for token_id in line["token_ids"]:
            row = int(token_id.removeprefix("token-"))
            result[row] = [line["line_id"]]
    for item in unresolved:
        result[item["token_source_row"]] = list(item["candidate_line_ids"])
    return result


def _initial_bands(tokens, tolerance, slope):
    """Production `_line_bands` vertical predicate, before its final split."""
    ordered = sorted(
        tokens,
        key=lambda token: (geometry._adjusted_center_y(token, slope), token.x, token.source_row),
    )
    bands: list[list[geometry._Token]] = []
    gap_limit = geometry._horizontal_gap_limit(tokens)
    for token in ordered:
        if bands:
            center = statistics.median(geometry._adjusted_center_y(item, slope) for item in bands[-1])
            median_support = abs(geometry._adjusted_center_y(token, slope) - center) <= tolerance
            neighbor_support = any(
                abs(geometry._adjusted_center_y(token, slope) - geometry._adjusted_center_y(item, slope)) <= tolerance
                and geometry._horizontally_adjacent(item, token, gap_limit)
                for item in bands[-1]
            )
            if median_support or neighbor_support:
                bands[-1].append(token)
                continue
        bands.append([token])
    return bands


def trace_guard_on(tokens, tolerance, slope, gap_limit):
    records: list[dict[str, Any]] = []
    for band_index, band in enumerate(_initial_bands(tokens, tolerance, slope)):
        ordered = sorted(band, key=lambda token: (token.x, token.source_row))
        bridge_ids = geometry._supported_bridge_ids(ordered, gap_limit)
        current: list[geometry._Token] = []
        covered_right: int | None = None
        for token in ordered:
            oversized = geometry._is_oversized(token, gap_limit)
            supported = id(token) in bridge_ids
            actual_gap = None if covered_right is None else token.x - covered_right
            split = bool(current and actual_gap is not None and actual_gap > gap_limit)
            if split:
                responsible = [t for t in current if geometry._is_oversized(t, gap_limit) and id(t) not in bridge_ids]
                records.append({
                    "band_index": band_index,
                    "event": "horizontal_split",
                    "before_source_rows": [t.source_row for t in current],
                    "next_source_row": token.source_row,
                    "covered_right_px": covered_right,
                    "next_left_px": token.x,
                    "stale_covered_gap_px": actual_gap,
                    "actual_box_gap_px": token.x - max(t.x1 for t in current),
                    "gap_limit_px": gap_limit,
                    "oversized_tokens_responsible": [t.source_row for t in responsible],
                    "threshold_px": gap_limit * 1.5,
                    "selected_slope": slope,
                })
                current = []
            current.append(token)
            contributes = not oversized or supported
            before = covered_right
            if contributes:
                covered_right = max(covered_right or token.x1, token.x1)
            elif covered_right is None:
                covered_right = token.x
            records.append({
                "band_index": band_index,
                "event": "token_extent",
                "source_row": token.source_row,
                "bbox_px": [token.x, token.y, token.x1, token.y1],
                "text_locator": token.text,
                "width_px": token.width,
                "oversized_threshold_px": gap_limit * 1.5,
                "is_oversized": oversized,
                "supported_bridge": supported,
                "true_right_extent_contributes": contributes,
                "covered_right_before_px": before,
                "covered_right_after_px": covered_right,
            })
        if current:
            records.append({
                "band_index": band_index,
                "event": "region_end",
                "region_source_rows": [token.source_row for token in current],
            })
    return records


def off_split(bands, gap_limit):
    """Guard-off copy of production splitting; only extent treatment differs."""
    regions = []
    for band in bands:
        ordered = sorted(band, key=lambda token: (token.x, token.source_row))
        # Retain the production support calculation as an observed predicate;
        # guard-off no longer uses it to withhold an observed box's extent.
        geometry._supported_bridge_ids(ordered, gap_limit)
        current = []
        covered_right = None
        for token in ordered:
            if current and covered_right is not None and token.x - covered_right > gap_limit:
                regions.append(current)
                current = []
            current.append(token)
            covered_right = max(covered_right or token.x1, token.x1)
        if current:
            regions.append(current)
    return regions


def off_candidate_supported(band, token, gap_limit):
    """Use the ordinary gap predicate over every observed box extent."""
    ordered = sorted((*band, token), key=lambda item: (item.x, item.source_row))
    return all(
        right.x - left.x1 <= gap_limit
        for left, right in zip(ordered, ordered[1:])
    )


def run_guard_on(tokens):
    """Call the current production grouping entry point without replacement."""
    return geometry.group_physical_lines(tokens)


def run_guard_on_traced(tokens, production_slope):
    """Run the production predicates at the already selected production slope.

    Recording this function's calls captures both the region-split support
    checks and the final candidate-support checks without repeating the broad
    slope search or invoking OCR.
    """
    original_estimator = geometry._estimate_baseline_slope
    original_support = geometry._supported_bridge_ids
    calls = []

    def record_support_call(band_tokens, gap_limit):
        supported_ids = original_support(band_tokens, gap_limit)
        calls.append({
            "input_source_rows": [token.source_row for token in band_tokens],
            "oversized_source_rows": [
                token.source_row for token in band_tokens
                if geometry._is_oversized(token, gap_limit)
            ],
            "supported_bridge_source_rows": [
                token.source_row for token in band_tokens
                if id(token) in supported_ids
            ],
            "gap_limit_px": gap_limit,
        })
        return supported_ids

    geometry._estimate_baseline_slope = (
        lambda _tokens, _tolerance, fixed=production_slope: fixed
    )
    geometry._supported_bridge_ids = record_support_call
    try:
        lines, unresolved, measurements = geometry.group_physical_lines(tokens)
    finally:
        geometry._estimate_baseline_slope = original_estimator
        geometry._supported_bridge_ids = original_support
    return lines, unresolved, measurements, calls


def run_guard_off(tokens, selected_production_slope):
    """Hold the observed production slope and replace only oversized handling."""
    originals = (
        geometry._split_horizontal_regions,
        geometry._estimate_baseline_slope,
        geometry._horizontal_candidate_supported,
    )
    geometry._estimate_baseline_slope = (
        lambda _tokens, _tolerance, fixed=selected_production_slope: fixed
    )
    geometry._split_horizontal_regions = off_split
    geometry._horizontal_candidate_supported = off_candidate_supported
    try:
        return geometry.group_physical_lines(tokens)
    finally:
        (
            geometry._split_horizontal_regions,
            geometry._estimate_baseline_slope,
            geometry._horizontal_candidate_supported,
        ) = originals


def connected_events(tokens, on_lines, on_unresolved, off_lines, off_unresolved):
    on = token_memberships(tokens, on_lines, on_unresolved)
    off = token_memberships(tokens, off_lines, off_unresolved)
    changed = {row for row in on if on[row] != off[row]}
    parent = {row: row for row in changed}

    def find(row):
        while parent[row] != row:
            parent[row] = parent[parent[row]]
            row = parent[row]
        return row

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    # Relate changed identities that occupy the same line in either variant.
    for memberships in (on, off):
        for groups in memberships.values():
            for group in groups:
                members = [row for row in group if row in changed]
                for row in members[1:]:
                    union(members[0], row)
    components: dict[int, set[int]] = defaultdict(set)
    for row in changed:
        components[find(row)].add(row)
    return [sorted(rows) for rows in sorted(components.values(), key=lambda values: min(values))], on, off


def pixel_metrics(image_path: Path, tokens: list[geometry._Token], rows: Iterable[int]):
    metrics = {}
    with Image.open(image_path).convert("L") as image:
        for token in tokens:
            if token.source_row not in rows:
                continue
            box = (token.x, token.y, token.x1, token.y1)
            crop = image.crop(box)
            pixels = list(crop.getdata())
            dark = [(i % crop.width, i // crop.width, value) for i, value in enumerate(pixels) if value < 180]
            metrics[token.source_row] = {
                "bbox_px": [token.x, token.y, token.x1, token.y1],
                "dark_pixel_threshold": 180,
                "dark_pixels": len(dark),
                "box_pixels": crop.width * crop.height,
                "dark_occupancy": len(dark) / (crop.width * crop.height),
                "dark_centroid_local_px": (
                    [sum(x for x, _y, _v in dark) / len(dark), sum(y for _x, y, _v in dark) / len(dark)]
                    if dark else None
                ),
                "vertical_ink_extent_local_px": ([min(y for _x, y, _v in dark), max(y for _x, y, _v in dark)] if dark else None),
            }
    return metrics


def event_pairs(groups):
    pairs = set()
    for memberships in groups.values():
        for group in memberships:
            ordered = sorted(group)
            for i, left in enumerate(ordered):
                pairs.update((left, right) for right in ordered[i + 1 :])
    return pairs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "research/production-cropped-guard-ablation/results.json")
    parser.add_argument("--work", type=Path, default=Path("/tmp/normalize-guard-ablation"))
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)

    catalog = FixtureCatalog.load(ROOT)
    selected = [catalog.get(fixture_id) for fixture_id in FIXTURES]
    missing = [str(item.source_pdf) for item in selected if not item.source_pdf.is_file()]
    if missing:
        raise SystemExit("exact fixture availability gate failed: " + ", ".join(missing))

    pages_out = []
    for metadata in selected:
        fixture_dir = args.work / "preprocess" / metadata.fixture_id
        pre = rendering.preprocess_fixture(metadata, ROOT / "fixtures/preprocessing.json", fixture_dir)
        if pre.get("status") != rendering.SUCCESS:
            raise RuntimeError(f"preprocessing failed for {metadata.fixture_id}: {pre}")
        original_ocr = geometry.pytesseract.image_to_data
        captured_tsv: list[str] = []

        def capture_once(*args, **kwargs):
            value = original_ocr(*args, **kwargs)
            captured_tsv.append(value)
            return value

        geometry.pytesseract.image_to_data = capture_once
        try:
            baseline = geometry.run_geometry(fixture_dir, args.work / "production-geometry" / metadata.fixture_id)
        finally:
            geometry.pytesseract.image_to_data = original_ocr
        if len(captured_tsv) != 2:
            raise AssertionError(f"expected exactly two OCR calls for {metadata.fixture_id}, got {len(captured_tsv)}")
        if baseline.get("status") not in (rendering.SUCCESS, rendering.UNCERTAIN):
            raise RuntimeError(f"production geometry failed for {metadata.fixture_id}: {baseline}")
        pre_meta_path = next(fixture_dir.glob("*.preprocess.json"))
        pre_meta = json.loads(pre_meta_path.read_text(encoding="utf-8"))

        for page_index, page_record in enumerate(pre_meta["pages"]):
            image_path = fixture_dir / page_record["output_path"]
            tsv = captured_tsv[page_index]
            tokens, row_errors = geometry.parse_tsv_rows(tsv, page_record["width_px"], page_record["height_px"])
            if row_errors:
                raise AssertionError(f"TSV admission errors for {metadata.fixture_id}.{page_record['side']}: {row_errors}")
            production_page = baseline["pages"][page_index]
            production_slope = production_page["measurements"]["baseline_slope_px_per_px"]
            on_lines, on_unresolved, on_measurements, bridge_support_calls = run_guard_on_traced(
                tokens, production_slope
            )
            if [line["token_ids"] for line in on_lines] != [line["token_ids"] for line in production_page["physical_lines"]]:
                raise AssertionError("paired guard-on call differs from production baseline")
            slope = on_measurements["baseline_slope_px_per_px"]
            tolerance = on_measurements["tolerance_px"]
            gap_limit = on_measurements["horizontal_gap_limit_px"]
            trace = trace_guard_on(tokens, tolerance, slope, gap_limit)
            traced_regions = [
                sorted(record.get("region_source_rows", record.get("before_source_rows", [])))
                for record in trace
                if record.get("event") in {"horizontal_split", "region_end"}
            ]
            production_regions = sorted(
                sorted(token.source_row for token in band)
                for band in geometry._line_bands(tokens, tolerance, slope)
            )
            if sorted(traced_regions) != production_regions:
                raise AssertionError("diagnostic guard trace does not reproduce production horizontal partitions")

            # Freeze the production-selected slope in both variants. Otherwise
            # changing the horizontal guard could indirectly alter the slope
            # search's cohesion score and confound this single-factor test.
            off_lines, off_unresolved, off_measurements = run_guard_off(tokens, slope)

            assert off_measurements["baseline_slope_px_per_px"] == slope
            assert off_measurements["tolerance_px"] == tolerance
            assert off_measurements["horizontal_gap_limit_px"] == gap_limit
            token_identity_digest = digest_bytes(json.dumps(
                [(token.source_row, token.payload()) for token in tokens],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode())
            events, on_memberships, off_memberships = connected_events(tokens, on_lines, on_unresolved, off_lines, off_unresolved)
            token_by_row = {token.source_row: token for token in tokens}
            page_events = []
            pairs_on, pairs_off = event_pairs(on_memberships), event_pairs(off_memberships)
            for event_number, rows in enumerate(events, 1):
                rows_set = set(rows)
                related_trace = [
                    record for record in trace
                    if record.get("source_row") in rows_set
                    or record.get("next_source_row") in rows_set
                    or rows_set.intersection(record.get("before_source_rows", []))
                    or rows_set.intersection(record.get("region_source_rows", []))
                ]
                new_pairs = sorted([list(pair) for pair in (pairs_off - pairs_on) if set(pair) <= rows_set])
                lost_pairs = sorted([list(pair) for pair in (pairs_on - pairs_off) if set(pair) <= rows_set])
                page_events.append({
                    "event_id": f"{metadata.fixture_id}.{page_record['side']}.event-{event_number:03d}",
                    "token_source_rows": rows,
                    "tokens": [{
                        "token_id": f"token-{row:04d}",
                        "source_row": row,
                        "text_locator": token_by_row[row].text,
                        "confidence": token_by_row[row].confidence,
                        "bbox_px": [token_by_row[row].x, token_by_row[row].y, token_by_row[row].x1, token_by_row[row].y1],
                    } for row in rows],
                    "guard_on_memberships": {str(row): [list(group) for group in on_memberships[row]] for row in rows},
                    "guard_off_memberships": {str(row): [list(group) for group in off_memberships[row]] for row in rows},
                    "newly_joined_pairs": new_pairs,
                    "newly_separated_pairs": lost_pairs,
                    "oversized_tokens_responsible": sorted({
                        row for record in related_trace for row in record.get("oversized_tokens_responsible", [])
                    } | {
                        row for record in related_trace if record.get("event") == "token_extent" and record.get("is_oversized") and record.get("true_right_extent_contributes") is False for row in [record["source_row"]]
                    }),
                    "predicate_trace": related_trace,
                    "pixel_metrics": pixel_metrics(image_path, tokens, rows_set),
                    "adjudication": "unresolved",
                    "adjudication_evidence": "Requires visible inspection of the local diagnostic crop; metrics are descriptive, not a decision rule.",
                })

            oversized_tokens = [token for token in tokens if geometry._is_oversized(token, gap_limit)]
            guard_triggering = [record for record in trace if record.get("event") == "token_extent" and record["is_oversized"] and not record["true_right_extent_contributes"]]
            page_out = {
                "fixture_id": metadata.fixture_id,
                "side": page_record["side"],
                "blank": page_record["blank"],
                "dimensions_px": [page_record["width_px"], page_record["height_px"]],
                "crop_rectangle_px": page_record["page_crop"]["rect_px"],
                "source_pdf_sha256": pre_meta["source_pdf_sha256"],
                "preprocess_metadata_sha256": sha256(pre_meta_path),
                "output_image_sha256": sha256(image_path),
                "tsv_sha256": digest_bytes(tsv.encode("utf-8")),
                "admitted_tokens": [{
                    "token_id": f"token-{token.source_row:04d}",
                    "source_row": token.source_row,
                    "text_locator": token.text,
                    "confidence": token.confidence,
                    "bbox_px": [token.x, token.y, token.x1, token.y1],
                } for token in tokens],
                "guard_on": {
                    "token_count": len(tokens),
                    "physical_line_count": len(on_lines),
                    "ambiguous_count": sum(len(item["candidate_line_ids"]) > 1 for item in on_unresolved),
                    "unassigned_count": sum(not item["candidate_line_ids"] for item in on_unresolved),
                    "selected_slope": slope,
                    "median_token_width_px": statistics.median(token.width for token in tokens) if tokens else None,
                    "horizontal_gap_limit_px": gap_limit,
                    "oversized_threshold_px": gap_limit * 1.5,
                    "oversized_classification_count": len(oversized_tokens),
                    "guard_triggering_count": len(guard_triggering),
                    "measurements": on_measurements,
                },
                "guard_off": {
                    "physical_line_count": len(off_lines),
                    "ambiguous_count": sum(len(item["candidate_line_ids"]) > 1 for item in off_unresolved),
                    "unassigned_count": sum(not item["candidate_line_ids"] for item in off_unresolved),
                    "selected_slope": off_measurements["baseline_slope_px_per_px"],
                    "tolerance_px": off_measurements["tolerance_px"],
                    "median_token_width_px": statistics.median(token.width for token in tokens) if tokens else None,
                    "horizontal_gap_limit_px": off_measurements["horizontal_gap_limit_px"],
                    "oversized_threshold_px": off_measurements["horizontal_gap_limit_px"] * 1.5,
                },
                "guard_on_memberships_by_source_row": {
                    str(row): [list(group) for group in groups]
                    for row, groups in on_memberships.items()
                },
                "guard_off_memberships_by_source_row": {
                    str(row): [list(group) for group in groups]
                    for row, groups in off_memberships.items()
                },
                "guard_trace": trace,
                "supported_bridge_predicate_calls": bridge_support_calls,
                "changed_events": page_events,
                "guard_on_token_identity_sha256": token_identity_digest,
                "guard_off_token_identity_sha256": token_identity_digest,
                "ocr_token_identity_sha256": token_identity_digest,
                "same_ocr_inputs_proven": True,
            }
            pages_out.append(page_out)
            print(f"{metadata.fixture_id}.{page_record['side']}: tokens={len(tokens)} lines={len(on_lines)}/{len(off_lines)} oversized={len(oversized_tokens)} trigger={len(guard_triggering)} events={len(page_events)} blank={page_record['blank']}")

    result = {
        "schema": "production-cropped-guard-ablation-v1",
        "branch_base": "origin/guh",
        "dpi": 144,
        "ocr_calls": 12,
        "tesseract_config": "--psm 6",
        "same_ocr_for_both_variants": True,
        "variant_difference": "only the horizontal extent update: guard-off always advances covered_right to token.x1; all other predicates and tokens are held constant",
        "primary_blank_exclusion": "stella_maris_pdf03_session-I.left",
        "pages": pages_out,
    }
    # Visual decisions are kept as a separate human-reviewed record so a
    # fresh OCR run cannot silently inherit or regenerate page adjudications.
    adjudication_path = args.out.parent / "adjudications.json"
    if adjudication_path.is_file():
        adjudications = json.loads(adjudication_path.read_text(encoding="utf-8"))
        by_id = adjudications.get("events", {})
        seen = set()
        for page in pages_out:
            for event in page["changed_events"]:
                record = by_id.get(event["event_id"])
                if record is not None:
                    event["adjudication"] = record["adjudication"]
                    event["adjudication_evidence"] = record["evidence"]
                    seen.add(event["event_id"])
        required = {
            event["event_id"]
            for page in pages_out
            if not page["blank"]
            for event in page["changed_events"]
        }
        if seen.intersection(required) != required:
            missing = sorted(required - seen)
            raise RuntimeError(f"missing human review for changed primary event(s): {missing}")
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
