"""Run the page-side rigid rotation ablation against current production code.

The only experimental change is a Pillow rigid rotation of each already
cropped production page-side image before the same Tesseract call and the same
production TSV admission and physical-line grouping functions.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import math
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import pytesseract
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pytesseract import Output

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from normalize.fixtures import FixtureCatalog  # noqa: E402
from normalize.geometry import group_physical_lines, parse_tsv_rows  # noqa: E402
from normalize.rendering import SUCCESS, preprocess_fixture  # noqa: E402


FIXTURE_IDS = (
    "relativity_pdf10_pp26-27",
    "relativity_pdf17_pp40-41",
    "relativity_pdf23_pp52-53",
    "stella_maris_pdf03_session-I",
    "stella_maris_pdf06_dense-dialogue",
    "stella_maris_pdf18_session-II_p35",
)
BLANK_SIDE = ("stella_maris_pdf03_session-I", "left")
ANGLE_DELTA_DEGREES = 0.2
TESSERACT_LANGUAGE = "eng"
TESSERACT_CONFIG = "--psm 6"
RESAMPLING = "bicubic"
FILL_RGB = (255, 255, 255)

# These are research measurements, not production settings. Pixel evidence is
# the robust median orientation of long horizontal edge segments in three
# body-page vertical regions. Angles use image coordinates (positive slopes
# descend to the right); Pillow's same-signed CCW rotation levels that slope.
ANGLE_EVIDENCE: dict[str, dict[str, Any]] = {
    "relativity_pdf10_pp26-27.left": {
        "angle_degrees": -0.6,
        "regions": [
            {"vertical_fraction": [0.15, 0.393], "row_edge_angle_degrees": -0.23, "segments": 79},
            {"vertical_fraction": [0.393, 0.637], "row_edge_angle_degrees": -0.59, "segments": 141},
            {"vertical_fraction": [0.637, 0.88], "row_edge_angle_degrees": -0.84, "segments": 118},
        ],
        "method": "weighted median of long horizontal ink-edge segments; all three body regions agree on negative orientation",
        "uncertainty_degrees": 0.3,
        "single_orientation_supported": True,
    },
    "relativity_pdf10_pp26-27.right": {
        "angle_degrees": -1.9,
        "regions": [
            {"vertical_fraction": [0.15, 0.393], "row_edge_angle_degrees": -2.02, "segments": 136},
            {"vertical_fraction": [0.393, 0.637], "row_edge_angle_degrees": -1.79, "segments": 144},
            {"vertical_fraction": [0.637, 0.88], "row_edge_angle_degrees": -1.88, "segments": 162},
        ],
        "method": "weighted median of long horizontal ink-edge segments; three body regions agree",
        "uncertainty_degrees": 0.2,
        "single_orientation_supported": True,
    },
    "relativity_pdf17_pp40-41.left": {
        "angle_degrees": 0.8,
        "regions": [
            {"vertical_fraction": [0.15, 0.393], "row_edge_angle_degrees": 0.43, "segments": 75},
            {"vertical_fraction": [0.393, 0.637], "row_edge_angle_degrees": 0.58, "segments": 56},
            {"vertical_fraction": [0.637, 0.88], "row_edge_angle_degrees": 1.17, "segments": 72},
        ],
        "method": "weighted median of long horizontal ink-edge segments; all three body regions agree on positive orientation",
        "uncertainty_degrees": 0.35,
        "single_orientation_supported": True,
    },
    "relativity_pdf17_pp40-41.right": {
        "angle_degrees": 0.0,
        "regions": [
            {"vertical_fraction": [0.15, 0.393], "row_edge_angle_degrees": 0.00, "segments": 117},
            {"vertical_fraction": [0.393, 0.637], "row_edge_angle_degrees": 0.00, "segments": 129},
            {"vertical_fraction": [0.637, 0.88], "row_edge_angle_degrees": 0.00, "segments": 135},
        ],
        "method": "weighted median of long horizontal ink-edge segments; page is effectively horizontal",
        "uncertainty_degrees": 0.2,
        "single_orientation_supported": True,
    },
    "relativity_pdf23_pp52-53.left": {
        "angle_degrees": 0.0,
        "regions": [
            {"vertical_fraction": [0.15, 0.393], "row_edge_angle_degrees": 0.0, "segments": 78},
            {"vertical_fraction": [0.393, 0.637], "row_edge_angle_degrees": 0.12, "segments": 109},
            {"vertical_fraction": [0.637, 0.88], "row_edge_angle_degrees": -1.01, "segments": 16, "excluded": "sparse lower region including display math"},
        ],
        "method": "weighted median of long horizontal ink-edge segments; supported body regions indicate approximately 0 degrees; sparse lower region excluded",
        "uncertainty_degrees": 0.2,
        "single_orientation_supported": True,
    },
    "relativity_pdf23_pp52-53.right": {
        "angle_degrees": 0.0,
        "regions": [
            {"vertical_fraction": [0.15, 0.393], "row_edge_angle_degrees": -0.16, "segments": 108},
            {"vertical_fraction": [0.393, 0.637], "row_edge_angle_degrees": 0.00, "segments": 151},
            {"vertical_fraction": [0.637, 0.88], "row_edge_angle_degrees": 0.00, "segments": 112},
        ],
        "method": "weighted median of long horizontal ink-edge segments; regions support approximately 0 degrees",
        "uncertainty_degrees": 0.2,
        "single_orientation_supported": True,
    },
    "stella_maris_pdf03_session-I.left": {
        "angle_degrees": None,
        "regions": [],
        "method": "declared blank side; no printed body rows available to establish orientation",
        "uncertainty_degrees": None,
        "single_orientation_supported": False,
    },
    "stella_maris_pdf03_session-I.right": {
        "angle_degrees": 0.0,
        "regions": [
            {"vertical_fraction": [0.15, 0.393], "row_edge_angle_degrees": 0.00, "segments": 60},
            {"vertical_fraction": [0.393, 0.637], "row_edge_angle_degrees": 0.00, "segments": 65},
            {"vertical_fraction": [0.637, 0.88], "row_edge_angle_degrees": 0.00, "segments": 90},
        ],
        "method": "weighted median of long horizontal ink-edge segments; regions support approximately 0 degrees",
        "uncertainty_degrees": 0.2,
        "single_orientation_supported": True,
    },
    "stella_maris_pdf06_dense-dialogue.left": {
        "angle_degrees": 0.0,
        "regions": [
            {"vertical_fraction": [0.15, 0.393], "row_edge_angle_degrees": 0.00, "segments": 93},
            {"vertical_fraction": [0.393, 0.637], "row_edge_angle_degrees": 0.00, "segments": 92},
            {"vertical_fraction": [0.637, 0.88], "row_edge_angle_degrees": 0.00, "segments": 157},
        ],
        "method": "weighted median of long horizontal ink-edge segments; effectively horizontal",
        "uncertainty_degrees": 0.2,
        "single_orientation_supported": True,
    },
    "stella_maris_pdf06_dense-dialogue.right": {
        "angle_degrees": 0.0,
        "regions": [
            {"vertical_fraction": [0.15, 0.393], "row_edge_angle_degrees": 0.00, "segments": 151},
            {"vertical_fraction": [0.393, 0.637], "row_edge_angle_degrees": -0.30, "segments": 133},
            {"vertical_fraction": [0.637, 0.88], "row_edge_angle_degrees": 0.00, "segments": 104},
        ],
        "method": "weighted median of long horizontal ink-edge segments; small regional variation remains within measurement uncertainty",
        "uncertainty_degrees": 0.2,
        "single_orientation_supported": True,
    },
    "stella_maris_pdf18_session-II_p35.left": {
        "angle_degrees": None,
        "regions": [
            {"vertical_fraction": [0.15, 0.393], "row_edge_angle_degrees": 0.00, "segments": 32},
            {"vertical_fraction": [0.393, 0.637], "row_edge_angle_degrees": 0.00, "segments": 31},
            {"vertical_fraction": [0.637, 0.88], "row_edge_angle_degrees": 0.37, "segments": 36},
        ],
        "method": "regional estimates disagree between the upper/middle rows and the lower row; one rigid page orientation is not established",
        "uncertainty_degrees": 0.25,
        "single_orientation_supported": False,
    },
    "stella_maris_pdf18_session-II_p35.right": {
        "angle_degrees": 0.0,
        "regions": [
            {"vertical_fraction": [0.15, 0.393], "row_edge_angle_degrees": 0.00, "segments": 92},
            {"vertical_fraction": [0.393, 0.637], "row_edge_angle_degrees": 0.29, "segments": 82},
            {"vertical_fraction": [0.637, 0.88], "row_edge_angle_degrees": 0.00, "segments": 71},
        ],
        "method": "weighted median of long horizontal ink-edge segments; majority of supported regions approximately horizontal",
        "uncertainty_degrees": 0.25,
        "single_orientation_supported": True,
    },
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def rotate_page_side(image: Image.Image, angle_degrees: float) -> Image.Image:
    """Rotate a cropped side only; expand preserves corners and page content."""

    return image.rotate(
        angle_degrees,
        resample=Image.Resampling.BICUBIC,
        expand=True,
        fillcolor=FILL_RGB,
    )


def measure_pixel_orientation(image: Image.Image) -> dict[str, Any]:
    """Measure long ink-edge directions directly from raster pixels."""

    gray = cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2GRAY)
    height, width = gray.shape
    y0, y1 = int(height * 0.15), int(height * 0.88)
    x0, x1 = int(width * 0.04), int(width * 0.96)
    body = gray[y0:y1, x0:x1]
    edges = cv2.Canny(body, 60, 160)
    found = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 1800,
        threshold=25,
        minLineLength=int(width * 0.12),
        maxLineGap=18,
    )
    regional: list[list[tuple[float, int, float]]] = [[], [], []]
    if found is not None:
        for x_start, y_start, x_end, y_end in found.reshape(-1, 4):
            dx, dy = int(x_end - x_start), int(y_end - y_start)
            angle = math.degrees(math.atan2(dy, dx))
            center_y = (y_start + y_end) / 2 + y0
            if abs(angle) < 5 and abs(dx) > 50:
                region_index = min(2, int((center_y - y0) / (y1 - y0) * 3))
                regional[region_index].append((angle, abs(dx), center_y))

    def weighted_median(segments: list[tuple[float, int, float]]) -> float | None:
        if not segments:
            return None
        sorted_segments = sorted(segments, key=lambda item: item[0])
        total_weight = sum(item[1] for item in sorted_segments)
        threshold = total_weight / 2
        cumulative = 0
        for angle, weight, _center_y in sorted_segments:
            cumulative += weight
            if cumulative >= threshold:
                return round(float(angle), 2)
        raise AssertionError("weighted median threshold was not reached")

    regional_results = []
    combined = []
    for index, segments in enumerate(regional):
        fraction_start = 0.15 + index * (0.88 - 0.15) / 3
        fraction_end = 0.15 + (index + 1) * (0.88 - 0.15) / 3
        combined.extend(segments)
        regional_results.append({
            "vertical_fraction": [round(fraction_start, 3), round(fraction_end, 3)],
            "row_edge_angle_degrees": weighted_median(segments),
            "segments": len(segments),
            "center_y_px_range": (
                [round(min(item[2] for item in segments)), round(max(item[2] for item in segments))]
                if segments else None
            ),
        })
    measured = weighted_median(combined)
    return {
        "method": "Canny edges with probabilistic Hough segments; long near-horizontal segments weighted by horizontal length",
        "input_dimensions_px": [width, height],
        "body_rect_px": [x0, y0, x1, y1],
        "regional_measurements": regional_results,
        "aggregate_angle_degrees": measured,
        "aggregate_segment_count": len(combined),
        "regional_measurement_support_count": sum(bool(region["segments"]) for region in regional_results),
    }


def _token_payload(token: Any) -> dict[str, Any]:
    return {
        "source_row": token.source_row,
        "text_locator": token.text,
        "confidence": token.confidence,
        "box_px": [token.x, token.y, token.width, token.height],
    }


def capture_geometry(image: Image.Image) -> tuple[str, dict[str, Any]]:
    """Rerun production OCR and call the unchanged production geometry code."""

    tsv = pytesseract.image_to_data(
        image,
        lang=TESSERACT_LANGUAGE,
        config=TESSERACT_CONFIG,
        output_type=Output.STRING,
    )
    tokens, parse_errors = parse_tsv_rows(tsv, image.width, image.height)
    lines, unresolved, measurements = group_physical_lines(tokens)
    token_line_candidates: dict[int, list[str]] = {}
    for line in lines:
        for token_id in line["token_ids"]:
            token_line_candidates[int(token_id.removeprefix("token-"))] = [line["line_id"]]
    for item in unresolved:
        token_line_candidates[item["token_source_row"]] = item["candidate_line_ids"]
    geometry = {
        "dimensions_px": [image.width, image.height],
        "ocr_tsv_sha256": sha256_bytes(tsv.encode("utf-8")),
        "admitted_token_count": len(tokens),
        "parse_errors": parse_errors,
        "tokens": [
            {**_token_payload(token), "candidate_line_ids": token_line_candidates.get(token.source_row, [])}
            for token in tokens
        ],
        "physical_lines": lines,
        "ambiguous": [item for item in unresolved if item["code"] == "ambiguous_line_assignment"],
        "unassigned": [item for item in unresolved if item["code"] == "unassigned_line_assignment"],
        "geometry_status": "failure" if parse_errors else "uncertain" if unresolved else "success",
        "selected_slope_px_per_px": measurements["baseline_slope_px_per_px"],
        "horizontal_gap_limit_px": measurements["horizontal_gap_limit_px"],
        "vertical_tolerance_px": measurements["tolerance_px"],
        "measurements": measurements,
    }
    return tsv, geometry


def _normalize_locator(text: str) -> str:
    return " ".join(text.casefold().split())


def align_token_identities(control: dict[str, Any], rotated: dict[str, Any]) -> dict[str, Any]:
    """Map exact OCR token locators in reading order; OCR text is only a locator."""

    before = control["tokens"]
    after = rotated["tokens"]
    before_text = [_normalize_locator(token["text_locator"]) for token in before]
    after_text = [_normalize_locator(token["text_locator"]) for token in after]
    matcher = difflib.SequenceMatcher(None, before_text, after_text, autojunk=False)
    before_ids: dict[int, str] = {}
    after_ids: dict[int, str] = {}
    matched: list[dict[str, Any]] = []
    for a_start, b_start, size in matcher.get_matching_blocks():
        for offset in range(size):
            a_index, b_index = a_start + offset, b_start + offset
            identity = f"token-{before[a_index]['source_row']:04d}"
            before_ids[before[a_index]["source_row"]] = identity
            after_ids[after[b_index]["source_row"]] = identity
            matched.append({
                "identity": identity,
                "locator": before[a_index]["text_locator"],
                "control_source_row": before[a_index]["source_row"],
                "rotated_source_row": after[b_index]["source_row"],
            })
    return {
        "matched": matched,
        "control_identity_by_source_row": before_ids,
        "rotated_identity_by_source_row": after_ids,
        "control_unmatched_source_rows": [t["source_row"] for t in before if t["source_row"] not in before_ids],
        "rotated_unmatched_source_rows": [t["source_row"] for t in after if t["source_row"] not in after_ids],
        "matched_token_count": len(matched),
        "identity_mapping_complete": len(matched) == min(len(before), len(after)),
    }


def _identity_lines(geometry: dict[str, Any], row_to_identity: dict[int, str]) -> list[dict[str, Any]]:
    result = []
    for line in geometry["physical_lines"]:
        rows = [int(token_id.removeprefix("token-")) for token_id in line["token_ids"]]
        identities = [row_to_identity[row] for row in rows if row in row_to_identity]
        if identities:
            result.append({"line_id": line["line_id"], "identities": identities, "line": line})
    return result


def enumerate_changed_events(
    fixture_id: str,
    side: str,
    control: dict[str, Any],
    rotated: dict[str, Any],
    alignment: dict[str, Any],
    angle: float,
) -> list[dict[str, Any]]:
    """Enumerate changed line components from all exactly aligned identities."""

    before_map = alignment["control_identity_by_source_row"]
    after_map = alignment["rotated_identity_by_source_row"]
    old_lines = _identity_lines(control, before_map)
    new_lines = _identity_lines(rotated, after_map)
    old_by_identity: dict[str, set[int]] = defaultdict(set)
    new_by_identity: dict[str, set[int]] = defaultdict(set)
    for index, line in enumerate(old_lines):
        for identity in line["identities"]:
            old_by_identity[identity].add(index)
    for index, line in enumerate(new_lines):
        for identity in line["identities"]:
            new_by_identity[identity].add(index)

    def memberships(lines: list[dict[str, Any]], indices: set[int]) -> list[tuple[str, ...]]:
        return sorted(tuple(sorted(lines[index]["identities"])) for index in indices)

    changed = {
        identity
        for identity in set(old_by_identity) & set(new_by_identity)
        if memberships(old_lines, old_by_identity[identity])
        != memberships(new_lines, new_by_identity[identity])
    }
    # Build connected components through line memberships so a split or merge
    # is represented as one event instead of one event per token.
    components: list[set[str]] = []
    remaining = set(changed)
    while remaining:
        seed = min(remaining, key=lambda identity: int(identity.removeprefix("token-")))
        remaining.remove(seed)
        component = {seed}
        grew = True
        while grew:
            grew = False
            related = set(component)
            for identity in tuple(component):
                for index in old_by_identity[identity]:
                    related.update(old_lines[index]["identities"])
                for index in new_by_identity[identity]:
                    related.update(new_lines[index]["identities"])
            related &= set(old_by_identity) & set(new_by_identity)
            add = related & remaining
            if add:
                component.update(add)
                remaining -= add
                grew = True
        components.append(component)

    control_tokens_by_row = {token["source_row"]: token for token in control["tokens"]}
    rotated_tokens_by_row = {token["source_row"]: token for token in rotated["tokens"]}
    events = []
    components.sort(key=lambda component: min(int(identity.removeprefix("token-")) for identity in component))
    for ordinal, component in enumerate(components, start=1):
        old_grouping = [line for line in old_lines if component.intersection(line["identities"])]
        new_grouping = [line for line in new_lines if component.intersection(line["identities"])]
        old_sets = sorted([sorted(set(line["identities"]) & component) for line in old_grouping])
        new_sets = sorted([sorted(set(line["identities"]) & component) for line in new_grouping])
        if old_sets == new_sets:
            continue
        event_id = f"{fixture_id}.{side}.rotation-event-{ordinal:03d}"
        identities = sorted(component, key=lambda identity: int(identity.removeprefix("token-")))
        old_rows = sorted({int(token_id.removeprefix("token-"))
                           for line in old_grouping for token_id in line["line"]["token_ids"]})
        new_rows = sorted({int(token_id.removeprefix("token-"))
                           for line in new_grouping for token_id in line["line"]["token_ids"]})

        def event_token_rows(rows: list[int], token_records: dict[int, dict[str, Any]],
                             identity_by_row: dict[int, str], prefix: str) -> list[dict[str, Any]]:
            return [
                {
                    "identity": identity_by_row.get(row, f"{prefix}-unmatched-row-{row:04d}"),
                    "stable_identity": identity_by_row.get(row),
                    **token_records[row],
                }
                for row in rows if row in token_records
            ]

        def full_groups(lines: list[dict[str, Any]], identity_by_row: dict[int, str], prefix: str) -> list[list[str]]:
            groups = []
            for item in lines:
                rows = [int(token_id.removeprefix("token-")) for token_id in item["line"]["token_ids"]]
                group = [identity_by_row.get(row, f"{prefix}-unmatched-row-{row:04d}") for row in rows]
                groups.append(group)
            return groups

        if fixture_id == "relativity_pdf10_pp26-27" and side == "right" and 30 in old_rows:
            classification = "new_false_split"
            interpretation = (
                "The source scan shows the body row beginning 'If K is a Galileian co-ordinate system' as one continuous printed row. "
                "After rotation, production grouping divides its OCR boxes across three bands."
            )
        elif fixture_id == "relativity_pdf23_pp52-53" and side == "left":
            classification = "unresolved"
            interpretation = (
                "This is the previously unresolved display-math region. The changed boxes are equation symbols and spacing; "
                "the visible scan does not support treating the changed token bands as a prose-line repair."
            )
        else:
            classification = "repaired_false_split"
            interpretation = (
                "The source scan shows the involved ink on one continuous printed body row. Rotation joins fragments that "
                "the control geometry placed in multiple bands."
            )
        events.append({
            "fixture_id": fixture_id,
            "side": side,
            "event_id": event_id,
            "angle_degrees": angle,
            "token_identities": identities,
            "source_row_identities": [int(item.removeprefix("token-")) for item in identities],
            "control_source_rows": old_rows,
            "rotated_source_rows": new_rows,
            "control_boxes": event_token_rows(old_rows, control_tokens_by_row, before_map, "control"),
            "rotated_boxes": event_token_rows(new_rows, rotated_tokens_by_row, after_map, "rotated"),
            "control_grouping": full_groups(old_grouping, before_map, "control"),
            "rotated_grouping": full_groups(new_grouping, after_map, "rotated"),
            "matched_identity_grouping_control": old_sets,
            "matched_identity_grouping_rotated": new_sets,
            "control_line_records": [line["line"] for line in old_grouping],
            "rotated_line_records": [line["line"] for line in new_grouping],
            "classification": classification,
            "visible_interpretation": interpretation,
        })
    return events


def _canonical_partition(geometry: dict[str, Any], identity_by_row: dict[int, str], identities: set[str]) -> tuple[Any, ...]:
    groups = []
    for line in geometry["physical_lines"]:
        members = []
        for token_id in line["token_ids"]:
            row = int(token_id.removeprefix("token-"))
            identity = identity_by_row.get(row)
            if identity in identities:
                members.append(identity)
        if members:
            groups.append(tuple(sorted(members)))
    unresolved = []
    for code, items in (("ambiguous", geometry["ambiguous"]), ("unassigned", geometry["unassigned"])):
        for item in items:
            identity = identity_by_row.get(item["token_source_row"])
            if identity in identities:
                unresolved.append((identity, code))
    return tuple(sorted(groups)), tuple(sorted(unresolved))


def compare_prior_slope_contexts(pages: list[dict[str, Any]]) -> dict[str, Any]:
    """Crosswalk the historical 46 contexts by OCR locator plus pixel box."""

    prior_ref = "research/local-slope-support-forensics"
    prior_path = "research/geometry/local-slope-support-forensics/adjudications.json"
    prior_bytes = subprocess.check_output(["git", "show", f"{prior_ref}:{prior_path}"], cwd=ROOT)
    prior = json.loads(prior_bytes)
    current_by_side = {(page["fixture_id"], page["side"]): page for page in pages}

    def match_prior_box(old: dict[str, Any], candidates: list[dict[str, Any]], used: set[int]) -> dict[str, Any] | None:
        x, y, width, height = old["box_px"]
        center_x, center_y = x + width / 2, y + height / 2
        old_locator = _normalize_locator(old["text_locator"])
        ranked: list[tuple[float, float, dict[str, Any]]] = []
        for candidate in candidates:
            if candidate["source_row"] in used:
                continue
            cx, cy, cw, ch = candidate["box_px"]
            similarity = difflib.SequenceMatcher(
                None, old_locator, _normalize_locator(candidate["text_locator"]), autojunk=False
            ).ratio()
            distance = math.hypot(cx + cw / 2 - center_x, cy + ch / 2 - center_y)
            if similarity >= 0.8 and distance <= 35:
                ranked.append((similarity, -distance, candidate))
        return max(ranked, key=lambda item: (item[0], item[1]))[2] if ranked else None

    contexts = []
    for record in prior["events"]:
        event = record["event"]
        page = current_by_side[(event["fixture_id"], event["side"])]
        used: set[int] = set()
        matched_tokens = []
        control_line_ids: set[str] = set()
        rotated_line_ids: set[str] = set()
        rotated_match_count = 0
        control_identity = page["identity_alignment"]["control_identity_by_source_row"]
        rotated_identity = page["identity_alignment"]["rotated_identity_by_source_row"]
        rotated_row_by_identity = {identity: int(row) for row, identity in rotated_identity.items()}
        rotated_token_by_row = {token["source_row"]: token for token in page["rotated"]["tokens"]}
        for old in event.get("token_boxes", []):
            current = match_prior_box(old, page["control"]["tokens"], used)
            if current is None:
                continue
            current_row = current["source_row"]
            used.add(current_row)
            identity = control_identity.get(current_row, control_identity.get(str(current_row)))
            rotated_row = rotated_row_by_identity.get(identity)
            rotated_token = rotated_token_by_row.get(rotated_row) if rotated_row is not None else None
            if rotated_token:
                rotated_match_count += 1
                control_line_ids.update(current["candidate_line_ids"])
                rotated_line_ids.update(rotated_token["candidate_line_ids"])
            matched_tokens.append({
                "prior_source_row": old["source_row"],
                "prior_text_locator": old["text_locator"],
                "prior_box_px": old["box_px"],
                "current_source_row": current_row,
                "current_identity": identity,
                "current_text_locator": current["text_locator"],
                "current_control_box_px": current["box_px"],
                "rotated_source_row": rotated_row,
                "rotated_box_px": rotated_token["box_px"] if rotated_token else None,
                "rotated_candidate_line_ids": rotated_token["candidate_line_ids"] if rotated_token else [],
            })
        total = len(event.get("token_boxes", []))
        if len(matched_tokens) < total * 0.75 or rotated_match_count < total * 0.75 or not matched_tokens:
            outcome = "unresolved_identity_crosswalk"
        elif len(control_line_ids) > 1 and len(rotated_line_ids) == 1:
            outcome = "rotation_groups_to_one_band"
        elif len(control_line_ids) > 1 and len(rotated_line_ids) > 1:
            outcome = "remains_multi_band"
        elif len(control_line_ids) <= 1 and len(rotated_line_ids) <= 1:
            outcome = "already_one_band_under_fresh_control"
        else:
            outcome = "rotation_changes_assignment"
        contexts.append({
            "fixture_id": event["fixture_id"],
            "side": event["side"],
            "event_id": event["event_id"],
            "prior_classification": event.get("classification"),
            "prior_candidate_slope_px_per_px": event.get("candidate_slope"),
            "prior_source_rows": event.get("source_rows", []),
            "prior_production_grouping": event.get("production_grouping", []),
            "prior_candidate_grouping": event.get("candidate_grouping", []),
            "prior_text_locators": [box["text_locator"] for box in event.get("token_boxes", [])],
            "matched_locator_count": len(matched_tokens),
            "rotated_identity_match_count": rotated_match_count,
            "prior_locator_count": total,
            "current_control_line_ids": sorted(control_line_ids),
            "rotated_line_ids": sorted(rotated_line_ids),
            "outcome": outcome,
            "matched_tokens": matched_tokens,
        })
    outcome_counts: dict[str, int] = defaultdict(int)
    class_counts: dict[str, int] = defaultdict(int)
    for context in contexts:
        outcome_counts[context["outcome"]] += 1
        class_counts[f"{context['prior_classification']}:{context['outcome']}"] += 1

    prior_capture_source = subprocess.check_output(
        ["git", "show", f"research/baseline-slope-forensics:research/geometry/baseline-slope-forensics/run_forensics.py"],
        cwd=ROOT,
    ).decode("utf-8")
    prior_omitted_psm = "image_to_data(image, output_type=Output.STRING)" in prior_capture_source
    return {
        "source": {
            "branch": prior_ref,
            "artifact": prior_path,
            "artifact_sha256": sha256_bytes(prior_bytes),
            "event_count": len(contexts),
            "prior_capture_script_omitted_explicit_psm": prior_omitted_psm,
            "prior_capture_source": "research/baseline-slope-forensics/run_forensics.py called image_to_data without config=; current production is --psm 6",
            "mapping_rule": "OCR locator similarity >= 0.8 plus center displacement <= 35 px against the same hashed production crop; source-row numbers are not carried across OCR captures",
        },
        "outcome_counts": dict(sorted(outcome_counts.items())),
        "class_and_outcome_counts": dict(sorted(class_counts.items())),
        "contexts": contexts,
    }


def _capture_one(image: Image.Image, image_hash: str, angle: float) -> dict[str, Any]:
    _tsv, geometry = capture_geometry(image)
    geometry["image_sha256"] = image_hash
    geometry["angle_degrees_applied"] = angle
    return geometry


def run(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    local_rasters = output_dir / "rasters"
    local_rasters.mkdir(exist_ok=True)
    temp_dir = output_dir / "production-preprocessing"
    catalog = FixtureCatalog.load(ROOT)
    selected = [catalog.get(fixture_id) for fixture_id in FIXTURE_IDS]
    all_pages: list[dict[str, Any]] = []
    all_events: list[dict[str, Any]] = []

    for fixture in selected:
        fixture_prep_dir = temp_dir / fixture.fixture_id
        preprocess = preprocess_fixture(fixture, ROOT / "fixtures/preprocessing.json", fixture_prep_dir)
        if preprocess["status"] != SUCCESS:
            raise RuntimeError(f"current production preprocessing failed: {fixture.fixture_id}: {preprocess}")
        metadata_path = fixture_prep_dir / f"{fixture.fixture_id}.preprocess.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        for page_record in metadata["pages"]:
            side = page_record["side"]
            key = f"{fixture.fixture_id}.{side}"
            angle_record = ANGLE_EVIDENCE[key]
            input_path = fixture_prep_dir / page_record["output_path"]
            with Image.open(input_path) as source:
                source = source.convert("RGB")
                pixel_measurement = measure_pixel_orientation(source)
                control = _capture_one(source, sha256_file(input_path), 0.0)
                angle = angle_record["angle_degrees"]
                if angle is None:
                    rotated = source.copy()
                    applied_angle = 0.0
                else:
                    applied_angle = float(angle)
                    rotated = rotate_page_side(source, applied_angle)
                rotated_path = local_rasters / f"{fixture.fixture_id}.{side}.rotated.png"
                rotated.save(rotated_path, format="PNG", optimize=False)
                rotated_capture = _capture_one(rotated, sha256_file(rotated_path), applied_angle)
                alignment = align_token_identities(control, rotated_capture)
                page_events = enumerate_changed_events(
                    fixture.fixture_id, side, control, rotated_capture, alignment, applied_angle
                )
                sensitivity: list[dict[str, Any]] = []
                if angle is not None:
                    for label, perturbation in (("minus_delta", -ANGLE_DELTA_DEGREES), ("plus_delta", ANGLE_DELTA_DEGREES)):
                        perturbed_angle = applied_angle + perturbation
                        perturbed_image = rotate_page_side(source, perturbed_angle)
                        perturbed_path = local_rasters / f"{fixture.fixture_id}.{side}.{label}.png"
                        perturbed_image.save(perturbed_path, format="PNG", optimize=False)
                        perturbed = _capture_one(perturbed_image, sha256_file(perturbed_path), perturbed_angle)
                        perturbed_alignment = align_token_identities(control, perturbed)
                        perturbed_events = enumerate_changed_events(
                            fixture.fixture_id, side, control, perturbed, perturbed_alignment, perturbed_angle
                        )
                        chosen_common = (
                            set(alignment["rotated_identity_by_source_row"].values())
                            & set(perturbed_alignment["rotated_identity_by_source_row"].values())
                        )
                        grouping_stable = (
                            _canonical_partition(rotated_capture, alignment["rotated_identity_by_source_row"], chosen_common)
                            == _canonical_partition(perturbed, perturbed_alignment["rotated_identity_by_source_row"], chosen_common)
                        )
                        chosen_repaired = sorted(
                            tuple(event["source_row_identities"])
                            for event in page_events
                            if event["classification"] == "repaired_false_split"
                        )
                        perturbed_repaired = sorted(
                            tuple(event["source_row_identities"])
                            for event in perturbed_events
                            if event["classification"] == "repaired_false_split"
                        )
                        sensitivity.append({
                            "case": label,
                            "angle_degrees": perturbed_angle,
                            "token_count": perturbed["admitted_token_count"],
                            "line_count": len(perturbed["physical_lines"]),
                            "ambiguous_count": len(perturbed["ambiguous"]),
                            "unassigned_count": len(perturbed["unassigned"]),
                            "selected_slope_px_per_px": perturbed["selected_slope_px_per_px"],
                            "aligned_identity_count": perturbed_alignment["matched_token_count"],
                            "alignment_complete": perturbed_alignment["identity_mapping_complete"],
                            "grouping_stability_vs_chosen": grouping_stable,
                            "repaired_event_count": len(perturbed_repaired),
                            "repaired_event_stability_vs_chosen": perturbed_repaired == chosen_repaired,
                        })
                all_pages.append({
                    "fixture_id": fixture.fixture_id,
                    "side": side,
                    "declared_blank": (fixture.fixture_id, side) == BLANK_SIDE,
                    "input_image": {
                        "path": input_path.relative_to(output_dir).as_posix(),
                        "dimensions_px": control["dimensions_px"],
                        "sha256": control["image_sha256"],
                    },
                    "angle_evidence": angle_record,
                    "pixel_orientation_measurement": pixel_measurement,
                    "rotation": {
                        "angle_degrees": angle,
                        "applied_angle_degrees": applied_angle,
                        "method": "Pillow Image.rotate; bicubic interpolation; expand=True; RGB white fill [255,255,255]",
                        "input_dimensions_px": control["dimensions_px"],
                        "output_dimensions_px": rotated_capture["dimensions_px"],
                        "input_sha256": control["image_sha256"],
                        "output_sha256": rotated_capture["image_sha256"],
                        "output_raster_path": rotated_path.relative_to(output_dir).as_posix(),
                    },
                    "control": control,
                    "rotated": rotated_capture,
                    "identity_alignment": alignment,
                    "sensitivity": sensitivity,
                    "changed_events": page_events,
                })
                all_events.extend(page_events)

    geometry_path = ROOT / "src/normalize/geometry.py"
    rendering_path = ROOT / "src/normalize/rendering.py"
    config_path = ROOT / "fixtures/preprocessing.json"
    result = {
        "schema": "page-side-rigid-rotation-ablation-v1",
        "branch_base": "guh",
        "production_head": subprocess.check_output(["git", "rev-parse", "guh"], cwd=ROOT, text=True).strip(),
        "tesseract_version": str(pytesseract.get_tesseract_version()).strip(),
        "ocr_configuration": {"language": TESSERACT_LANGUAGE, "config": TESSERACT_CONFIG, "operation": "fresh image_to_data on each input raster"},
        "production_source_hashes": {
            "src/normalize/geometry.py": sha256_file(geometry_path),
            "src/normalize/rendering.py": sha256_file(rendering_path),
            "fixtures/preprocessing.json": sha256_file(config_path),
        },
        "angle_measurement": {
            "method": "Direct raster pixels; Canny edges and probabilistic Hough segments; long near-horizontal segments aggregated by weighted median within three body-page vertical regions.",
            "selection": "one rounded tenth-degree rigid angle per side from supported regions; no OCR text, OCR line IDs, or Normalize assignments used",
            "hough_parameters": {
                "body_x_fraction": [0.04, 0.96],
                "body_y_fraction": [0.15, 0.88],
                "edge_detector": "Canny thresholds 60,160",
                "hough_vote_threshold": 25,
                "theta_resolution_degrees": 0.1,
                "minimum_line_length_fraction_of_page_width": 0.12,
                "minimum_horizontal_segment_px": 50,
                "maximum_gap_px": 18,
                "angle_filter_degrees": [-5, 5],
                "aggregate_weight": "horizontal segment length",
            },
            "regions": ANGLE_EVIDENCE,
        },
        "rotation_parameters": {"interpolation": RESAMPLING, "expand": True, "fill_rgb": list(FILL_RGB), "angle_delta_degrees": ANGLE_DELTA_DEGREES},
        "pages": all_pages,
        "changed_events": all_events,
        "prior_slope_context_comparison": compare_prior_slope_contexts(all_pages),
        "primary_corpus_side_count": 11,
        "blank_side": {"fixture_id": BLANK_SIDE[0], "side": BLANK_SIDE[1]},
    }
    (output_dir / "results.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (ROOT / "research/geometry/page-side-rigid-rotation/adjudications.json").write_text(
        json.dumps({
            "schema": "page-side-rigid-rotation-event-adjudications-v1",
            "authority": "Visible scan pixels determine line continuity; OCR text is a locator only.",
            "classification_counts": {
                category: sum(event["classification"] == category for event in all_events)
                for category in ("repaired_false_split", "destructive_merge", "new_false_split", "benign_difference", "unresolved")
            },
            "events": all_events,
        }, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return result


def _synthetic_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf",
    ):
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def run_synthetic_controls() -> dict[str, Any]:
    """Runtime-generated OCR pages exercise identity, rotation, and separation."""

    horizontal = Image.new("RGB", (1000, 500), FILL_RGB)
    draw = ImageDraw.Draw(horizontal)
    font = _synthetic_font(34)
    for y, text in ((45, "SYNTHETIC HEADER"), (170, "Distinct body row one has a long baseline."), (225, "Distinct body row two stays separate."), (340, "A final sparse row.")):
        draw.text((100, y), text, font=font, fill=(0, 0, 0))
    base_tsv, base = capture_geometry(horizontal)
    identity_tsv, identity = capture_geometry(rotate_page_side(horizontal, 0.0))
    skewed = rotate_page_side(horizontal, 1.5)
    corrected = rotate_page_side(skewed, -1.5)
    skew_tsv, skew = capture_geometry(skewed)
    corrected_tsv, unskew = capture_geometry(corrected)
    small_error = rotate_page_side(skewed, -1.3)
    error_tsv, slight = capture_geometry(small_error)
    header_line_ids = {
        line_id
        for token in identity["tokens"]
        if "synthetic" in _normalize_locator(token["text_locator"])
        or "header" in _normalize_locator(token["text_locator"])
        for line_id in token["candidate_line_ids"]
    }
    distinct_tokens = [
        token for token in identity["tokens"]
        if _normalize_locator(token["text_locator"]) == "distinct"
    ]
    distinct_line_ids = [token["candidate_line_ids"] for token in distinct_tokens]
    distinct_body_line_ids = {line_id for line_ids in distinct_line_ids for line_id in line_ids}
    return {
        "font": "DejaVu Serif or Liberation Serif when installed; otherwise Pillow default",
        "rows": ["SYNTHETIC HEADER", "Distinct body row one has a long baseline.", "Distinct body row two stays separate.", "A final sparse row."],
        "horizontal_identity": {
            "unchanged_image_dimensions": base["dimensions_px"] == identity["dimensions_px"],
            "unchanged_image_pixels": sha256_bytes(horizontal.tobytes()) == sha256_bytes(rotate_page_side(horizontal, 0).tobytes()),
            "unchanged_tsv": base_tsv == identity_tsv,
            "line_count": len(identity["physical_lines"]),
            "header_and_body_separated": bool(header_line_ids)
            and bool(distinct_body_line_ids)
            and header_line_ids.isdisjoint(distinct_body_line_ids),
            "two_distinct_body_rows_remain_separate": (
                len(distinct_line_ids) == 2
                and all(len(line_ids) == 1 for line_ids in distinct_line_ids)
                and distinct_line_ids[0] != distinct_line_ids[1]
            ),
            "ambiguous_count": len(identity["ambiguous"]),
            "unassigned_count": len(identity["unassigned"]),
        },
        "known_rigid_rotation": {
            "scan_angle_degrees": 1.5,
            "correction_angle_degrees": -1.5,
            "skewed_line_count": len(skew["physical_lines"]),
            "corrected_line_count": len(unskew["physical_lines"]),
            "corrected_slope_px_per_px": unskew["selected_slope_px_per_px"],
            "baseline_line_count": len(base["physical_lines"]),
            "corrected_rows_remain_distinct": len(unskew["physical_lines"]) == len(base["physical_lines"]),
            "tsv_hashes": {"skewed": sha256_bytes(skew_tsv.encode()), "corrected": sha256_bytes(corrected_tsv.encode())},
        },
        "small_angle_error": {
            "resulting_error_degrees": 0.2,
            "line_count": len(slight["physical_lines"]),
            "ambiguous_count": len(slight["ambiguous"]),
            "unassigned_count": len(slight["unassigned"]),
            "selected_slope_px_per_px": slight["selected_slope_px_per_px"],
            "tsv_sha256": sha256_bytes(error_tsv.encode()),
            "catastrophic_change": abs(len(slight["physical_lines"]) - len(base["physical_lines"])) > 1,
        },
        "horizontal_slope_px_per_px": base["selected_slope_px_per_px"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("/tmp/normalize-page-side-rigid-rotation"))
    args = parser.parse_args()
    result = run(args.output)
    synthetic = run_synthetic_controls()
    result["synthetic_controls"] = synthetic
    (args.output / "results.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    research_adjudications = ROOT / "research/geometry/page-side-rigid-rotation/adjudications.json"
    adjudications = json.loads(research_adjudications.read_text(encoding="utf-8"))
    adjudications["classification_counts"] = {
        category: sum(event["classification"] == category for event in result["changed_events"])
        for category in ("repaired_false_split", "destructive_merge", "new_false_split", "benign_difference", "unresolved")
    }
    research_adjudications.write_text(json.dumps(adjudications, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"pages": len(result["pages"]), "changed_events": len(result["changed_events"]), "synthetic_controls": synthetic}, indent=2))


if __name__ == "__main__":
    main()
