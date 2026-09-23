"""Research-only measurements of pixel evidence near OCR token geometry.

This module deliberately returns observations rather than a same-line decision,
score, or assignment.  It does not call production geometry.  Regions use
top-left image coordinates and half-open bounds: ``x0 <= x < x1`` and
``y0 <= y < y1``.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import subprocess
import sys
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image, ImageDraw

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
RESEARCH_ROOT = Path(__file__).resolve().parent
DEFAULT_REAL_ROOT = Path("/tmp/normalize-residual-forensics")
HISTORICAL_BASELINE_COMMIT = "699771d01c1a83c6f89c6a7eb2102e79a709b671"
# The prototype itself was introduced by this descendant.  Ordinary reusable
# tests may run from later descendants, subject to the content contract below.
MINIMUM_DESCENDANT_COMMIT = "c0f7ea88493a07e6139e9c71d413a2eda130c17b"
BASELINE_COMMIT = HISTORICAL_BASELINE_COMMIT
PRIOR_RESULTS = REPOSITORY_ROOT / "research/geometry/evidence-corrections/pixel-experiment-results.json"
PRIOR_PIXEL_ROOT = REPOSITORY_ROOT / "research/geometry/evidence-corrections/pixel-cases"
PRIOR_RESIDUAL_ROOT = REPOSITORY_ROOT / "research/geometry/residual-forensics"
VERIFICATION_CONTRACT = REPOSITORY_ROOT / "research/geometry/vertical-stage-ablation/verification-contract.json"
CANVAS = (220, 70)

PARAMETERS: dict[str, Any] = {
    "coordinate_convention": "top-left origin; all rectangles and intervals are half-open",
    "thresholds": [64, 128, 192],
    "component_scales": [1, 2, 4],
    "component_connectivity": [4, 8],
    "downsample_resampling": "BOX",
    "baseline_tolerance_px": 3.0,
    "ink_predicate": "pixel_value < threshold",
    "source_assumptions": [
        "source image is already the preserved preprocessed page image",
        "no deskew, thresholding, denoising, or morphology is applied by this prototype",
        "synthetic images are controlled illustrations, not arbitrary-scan performance evidence",
    ],
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def display_path(path: Path) -> str:
    """Use repository-relative paths for artifacts and absolute paths otherwise."""

    resolved = path.resolve()
    if resolved.is_relative_to(REPOSITORY_ROOT):
        return str(resolved.relative_to(REPOSITORY_ROOT))
    return str(resolved)


def jsonable(value: Any) -> Any:
    if isinstance(value, tuple):
        return [jsonable(item) for item in value]
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    return value


def _canonical_digest(value: Any) -> str:
    return sha256_bytes(json.dumps(jsonable(value), sort_keys=True, separators=(",", ":")).encode())


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPOSITORY_ROOT, check=True, text=True, capture_output=True
    ).stdout.strip()


def _is_ancestor(ancestor: str, revision: str) -> bool:
    return subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, revision],
        cwd=REPOSITORY_ROOT,
    ).returncode == 0


def _load_verification_contract() -> dict[str, Any]:
    try:
        return json.loads(VERIFICATION_CONTRACT.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AssertionError(f"cannot load verification contract: {VERIFICATION_CONTRACT}: {exc}") from exc


def verify_research_contract(*, require_exact_revision: bool = False) -> dict[str, Any]:
    """Verify revision ancestry and only the content that this prototype uses.

    The historical revision remains an explicit opt-in check.  Reusable tests
    instead require it as an ancestor and validate the evidence/prototype
    content contract.  Unrelated repository changes are intentionally ignored.
    """

    current_revision = _git("rev-parse", "HEAD")
    if require_exact_revision:
        if current_revision != HISTORICAL_BASELINE_COMMIT:
            raise AssertionError(
                "historical reproduction requires exact revision "
                f"{HISTORICAL_BASELINE_COMMIT}; found {current_revision}"
            )
    elif not _is_ancestor(HISTORICAL_BASELINE_COMMIT, current_revision):
        raise AssertionError(
            "reusable prototype execution requires a descendant of the "
            f"historical baseline {HISTORICAL_BASELINE_COMMIT}; found {current_revision}"
        )
    elif not _is_ancestor(MINIMUM_DESCENDANT_COMMIT, current_revision):
        raise AssertionError(
            "reusable prototype execution requires the implementation-introducing "
            f"descendant {MINIMUM_DESCENDANT_COMMIT} or later; found {current_revision}"
        )

    contract = _load_verification_contract()
    expected = contract["content_hashes"]
    checks = {
        "production_geometry": REPOSITORY_ROOT / "src/normalize/geometry.py",
        "identity_complete_oracle": REPOSITORY_ROOT / "tests/geometry_oracle.py",
        "prior_experiment_results": PRIOR_RESULTS,
        "prototype_source": Path(__file__).resolve(),
    }
    for name, path in checks.items():
        actual = sha256(path)
        if actual != expected[name]:
            raise AssertionError(
                f"research content mismatch for {name}: expected {expected[name]}, found {actual}"
            )
    for record in contract["preserved_inputs"]:
        path = REPOSITORY_ROOT / record["path"]
        actual = sha256(path)
        if actual != record["sha256"]:
            raise AssertionError(
                f"preserved input mismatch for {record['path']}: expected {record['sha256']}, found {actual}"
            )
    if contract["historical_result_sha256"] != sha256(REPOSITORY_ROOT / contract["historical_result_path"]):
        raise AssertionError("historical pixel-prototype result hash changed")
    if contract["historical_manifest_sha256"] != sha256(REPOSITORY_ROOT / contract["historical_manifest_path"]):
        raise AssertionError("historical pixel-prototype manifest changed")
    return {
        "current_revision": current_revision,
        "historical_baseline": HISTORICAL_BASELINE_COMMIT,
        "exact_revision_required": require_exact_revision,
        "content_hashes": expected,
        "preserved_inputs": contract["preserved_inputs"],
    }


def _package_versions() -> dict[str, str]:
    names = ("normalize", "Pillow", "pytest", "numpy", "opencv-python-headless", "PyMuPDF", "pytesseract", "rapidfuzz")
    versions: dict[str, str] = {}
    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "not installed"
    return versions


def _region(image: Image.Image, interval: Mapping[str, int]) -> Image.Image:
    width, height = image.size
    x0, x1 = int(interval["x0"]), int(interval["x1"])
    y0, y1 = int(interval["y0"]), int(interval["y1"])
    if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
        raise ValueError(f"invalid half-open interval {dict(interval)} for image {image.size}")
    return image.convert("L").crop((x0, y0, x1, y1))


def _empty_runs(columns: Sequence[int]) -> list[int]:
    runs: list[int] = []
    current = 0
    for count in columns:
        if count == 0:
            current += 1
        elif current:
            runs.append(current)
            current = 0
    if current:
        runs.append(current)
    return runs


def _component_measurement(image: Image.Image, threshold: int, scale: int, connectivity: int) -> dict[str, int]:
    if scale == 1:
        scaled = image
    else:
        scaled = image.resize(
            (math.ceil(image.width / scale), math.ceil(image.height / scale)),
            Image.Resampling.BOX,
        )
    points = {
        (x, y)
        for y in range(scaled.height)
        for x in range(scaled.width)
        if scaled.getpixel((x, y)) < threshold
    }
    if connectivity == 4:
        offsets = ((-1, 0), (1, 0), (0, -1), (0, 1))
    elif connectivity == 8:
        offsets = (
            (-1, 0),
            (1, 0),
            (0, -1),
            (0, 1),
            (-1, -1),
            (1, 1),
            (-1, 1),
            (1, -1),
        )
    else:
        raise ValueError(f"unsupported connectivity: {connectivity}")
    count = 0
    largest = 0
    while points:
        count += 1
        start = points.pop()
        queue = deque([start])
        area = 1
        while queue:
            x, y = queue.popleft()
            for dx, dy in offsets:
                neighbor = (x + dx, y + dy)
                if neighbor in points:
                    points.remove(neighbor)
                    queue.append(neighbor)
                    area += 1
        largest = max(largest, area)
    return {"count": count, "largest_area_px": largest}


def _threshold_observation(
    crop: Image.Image,
    threshold: int,
    band: Mapping[str, float],
    region: Mapping[str, int],
) -> dict[str, Any]:
    width, height = crop.size
    pixels = list(crop.tobytes())
    ink = [value < threshold for value in pixels]
    columns = [sum(ink[y * width + x] for y in range(height)) for x in range(width)]
    rows = [sum(ink[y * width : (y + 1) * width]) for y in range(height)]
    occupied = [(x, y) for y in range(height) for x in range(width) if ink[y * width + x]]
    if occupied:
        centroid_x = sum(x + region["x0"] for x, _ in occupied) / len(occupied)
        centroid_y = sum(y + region["y0"] for _, y in occupied) / len(occupied)
    else:
        centroid_x = centroid_y = None

    reference_x = float(band.get("reference_x", (region["x0"] + region["x1"]) / 2))
    baseline_y = float(band["baseline_y"])
    slope = float(band.get("baseline_slope_px_per_px", 0.0))
    tolerance = float(PARAMETERS["baseline_tolerance_px"])
    aligned_pixels = 0
    for x, y in occupied:
        absolute_x = x + region["x0"]
        absolute_y = y + region["y0"]
        expected_y = baseline_y + slope * (absolute_x - reference_x)
        if abs(absolute_y - expected_y) <= tolerance:
            aligned_pixels += 1

    return {
        "threshold": threshold,
        "ink_pixels": len(occupied),
        "ink_occupancy": len(occupied) / (width * height),
        "occupied_column_fraction": sum(value > 0 for value in columns) / width,
        "column_ink_counts": columns,
        "empty_column_runs_px": _empty_runs(columns),
        "max_empty_column_run_px": max(_empty_runs(columns), default=0),
        "row_ink_counts": rows,
        "occupied_row_bounds_px": None
        if not occupied
        else {"y0": min(y for _, y in occupied) + region["y0"], "y1": max(y for _, y in occupied) + region["y0"] + 1},
        "ink_centroid_px": None if not occupied else {"x": centroid_x, "y": centroid_y},
        "baseline_geometry": {
            "baseline_y": baseline_y,
            "baseline_slope_px_per_px": slope,
            "reference_x": reference_x,
            "tolerance_px": tolerance,
        },
        "baseline_aligned_ink_fraction": None if not occupied else aligned_pixels / len(occupied),
    }


def measure_bridge(
    source: Image.Image | Path,
    token_boxes: Sequence[Mapping[str, Any]],
    bridge_interval: Mapping[str, int],
    candidate_token_band: Mapping[str, float],
    parameters: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return raw observations for one proposed horizontal evidence region.

    This function intentionally has no assignment result, ``same_line`` field,
    classifier, or combined score.  ``token_boxes`` and the candidate band are
    contextual geometry only; they do not become pixel-derived authority.
    """

    effective = dict(PARAMETERS)
    if parameters:
        effective.update(parameters)
    image = Image.open(source) if isinstance(source, Path) else source
    image = image.convert("L")
    region = {key: int(bridge_interval[key]) for key in ("x0", "y0", "x1", "y1")}
    crop = _region(image, region)
    observations = {
        "thresholds": {
            str(threshold): _threshold_observation(crop, threshold, candidate_token_band, region)
            for threshold in effective["thresholds"]
        },
        "components": {
            str(threshold): {
                str(scale): {
                    str(connectivity): _component_measurement(crop, threshold, scale, connectivity)
                    for connectivity in effective["component_connectivity"]
                }
                for scale in effective["component_scales"]
            }
            for threshold in effective["thresholds"]
        },
    }
    return {
        "coordinate_convention": effective["coordinate_convention"],
        "region_of_interest": region,
        "region_dimensions_px": {"width": crop.width, "height": crop.height},
        "token_boxes": [dict(box) for box in token_boxes],
        "candidate_token_band": dict(candidate_token_band),
        "parameters": effective,
        "raw_observations": observations,
    }


def _row(text: str, *, x: int, y: int, width: int, word: int, height: int = 10) -> str:
    return "\t".join(map(str, (5, 1, 1, 1, 1, word, x, y, width, height, 95, text)))


def _draw_token_ink(draw: ImageDraw.ImageDraw, x: int, y: int, width: int, height: int) -> None:
    for offset in range(2, max(3, width - 2), 4):
        draw.rectangle((x + offset, y + 2, min(x + offset + 1, x + width - 1), y + height - 3), fill=0)
    draw.rectangle((x + 1, y + height - 3, x + width - 2, y + height - 2), fill=0)


def _base_synthetic(rows: Sequence[str], mode: str = "L") -> Image.Image:
    image = Image.new(mode, CANVAS, 255)
    draw = ImageDraw.Draw(image)
    for row in rows:
        fields = row.split("\t")
        if fields[-1] == "ocr-wide":
            continue
        x, y, width, height = map(int, fields[6:10])
        _draw_token_ink(draw, x, y, width, height)
    return image


def _two_sided_rows() -> list[str]:
    return [
        _row("same", x=10, y=20, width=10, word=1),
        _row("same", x=25, y=20, width=10, word=2),
        _row("ocr-wide", x=30, y=20, width=115, word=3),
        _row("same", x=145, y=20, width=10, word=4),
        _row("same", x=160, y=20, width=10, word=5),
    ]


def _two_sided_payload() -> dict[str, Any]:
    result = json.loads(PRIOR_RESULTS.read_text(encoding="utf-8"))
    return next(item["input"] for item in result["pairs"] if item["pair_id"] == "two_ordinary_tokens_each_side")


def _two_sided_boxes() -> list[dict[str, Any]]:
    payload = _two_sided_payload()
    boxes = []
    for source_row, row in enumerate(payload["rows"], start=1):
        fields = row.split("\t")
        boxes.append({"source_row": source_row, "text": fields[-1], "x": int(fields[6]), "y": int(fields[7]), "width": int(fields[8]), "height": int(fields[9])})
    return boxes


def _synthetic_cases(output_root: Path) -> dict[str, Any]:
    payload = _two_sided_payload()
    rows = _two_sided_rows()
    roi = {"x0": 35, "x1": 145, "y0": 20, "y1": 30}
    band = {"band_y0": 20, "band_y1": 30, "baseline_y": 25.0, "baseline_slope_px_per_px": 0.0, "reference_x": 90.0}
    prior_pair = json.loads(PRIOR_RESULTS.read_text(encoding="utf-8"))["pairs"][0]
    continuous_path = PRIOR_PIXEL_ROOT / "two_ordinary_tokens_each_side__continuous.png"
    disconnected_path = PRIOR_PIXEL_ROOT / "two_ordinary_tokens_each_side__disconnected.png"

    output_root.mkdir(parents=True, exist_ok=True)
    image_root = output_root / "synthetic"
    image_root.mkdir(parents=True, exist_ok=True)
    base = Image.open(disconnected_path).convert("L")
    cases: list[tuple[str, Image.Image, str]] = []
    cases.append(("single_pixel_noise_bridge", base.copy(), "disconnected regions with a one-pixel noise path"))
    draw = ImageDraw.Draw(cases[-1][1])
    draw.line((roi["x0"], 25, roi["x1"] - 1, 25), fill=0, width=1)

    glyphs = base.copy()
    glyph_draw = ImageDraw.Draw(glyphs)
    for x in range(roi["x0"] + 2, roi["x1"] - 2, 13):
        glyph_draw.rectangle((x, 23, min(x + 4, roi["x1"] - 1), 27), fill=0)
    cases.append(("disconnected_glyphs_same_row", glyphs, "separate glyph components in one genuine physical row"))

    spaces = base.copy()
    spaces_draw = ImageDraw.Draw(spaces)
    for x in (38, 63, 91, 119):
        spaces_draw.rectangle((x, 24, min(x + 6, roi["x1"] - 1), 27), fill=0)
    cases.append(("ordinary_word_spaces", spaces, "ordinary spaces interrupt ink although the printed row is continuous"))

    long_word = base.copy()
    long_draw = ImageDraw.Draw(long_word)
    for x in range(31, 144, 5):
        long_draw.rectangle((x, 22, min(x + 2, 144), 28), fill=0)
    cases.append(("genuinely_long_printed_word", long_word, "one genuinely long printed word fills the wide OCR rectangle"))

    neighbor = base.copy()
    neighbor_draw = ImageDraw.Draw(neighbor)
    neighbor_draw.line((roi["x0"], 46, roi["x1"] - 1, 46), fill=0, width=2)
    cases.append(("neighboring_row_ink", neighbor, "ink crosses the horizontal span but belongs to a neighboring row"))

    skewed = base.copy()
    skew_draw = ImageDraw.Draw(skewed)
    skew_draw.line((roi["x0"], 22, roi["x1"] - 1, 28), fill=0, width=2)
    cases.append(("skewed_continuous_text", skewed, "continuous support follows a sloped baseline"))

    low_resolution = base.copy()
    low_draw = ImageDraw.Draw(low_resolution)
    for x in range(roi["x0"], roi["x1"], 9):
        low_draw.rectangle((x, 24, min(x + 5, roi["x1"] - 1), 26), fill=120)
    cases.append(("threshold_sensitive_low_resolution_ink", low_resolution, "low-contrast sparse ink changes visibility with threshold"))

    outputs: dict[str, Any] = {
        "shared_input": payload,
        "shared_input_sha256": _canonical_digest(payload),
        "box_only_reference": {
            "source": str(PRIOR_RESULTS.relative_to(REPOSITORY_ROOT)),
            "complete_state_equal": prior_pair["checks"]["box_only_complete_assignment_state_equivalent"],
            "continuous_state_sha256": prior_pair["continuous"]["box_only_output"]["canonical_state_sha256"],
            "disconnected_state_sha256": prior_pair["disconnected"]["box_only_output"]["canonical_state_sha256"],
        },
        "controls": {},
        "adversarial_cases": [],
    }
    for name, image, interpretation in cases:
        path = image_root / f"{name}.png"
        image.save(path)
        measurement = measure_bridge(path, _two_sided_boxes(), roi, band)
        outputs["adversarial_cases"].append({
            "case_id": name,
            "source_image": display_path(path),
            "source_image_sha256": sha256(path),
            "physical_interpretation_by_construction": interpretation,
            "measurements": measurement,
        })
    outputs["measurement_relationships"] = _measurement_relationships(outputs["adversarial_cases"])

    continuous_measurement = measure_bridge(continuous_path, _two_sided_boxes(), roi, band)
    disconnected_measurement = measure_bridge(disconnected_path, _two_sided_boxes(), roi, band)
    outputs["controls"]["corrected_two_sided_pair"] = {
        "continuous_source": display_path(continuous_path),
        "continuous_sha256": sha256(continuous_path),
        "disconnected_source": display_path(disconnected_path),
        "disconnected_sha256": sha256(disconnected_path),
        "measurement_comparison": _compare_measurements(continuous_measurement, disconnected_measurement),
        "continuous_measurements": continuous_measurement,
        "disconnected_measurements": disconnected_measurement,
    }
    one_pair = json.loads(PRIOR_RESULTS.read_text(encoding="utf-8"))["pairs"][1]
    one_cont = PRIOR_PIXEL_ROOT / "one_ordinary_token_each_side__continuous.png"
    one_disc = PRIOR_PIXEL_ROOT / "one_ordinary_token_each_side__disconnected.png"
    one_roi = {"x0": 20, "x1": 150, "y0": 20, "y1": 30}
    one_band = {"band_y0": 20, "band_y1": 30, "baseline_y": 25.0, "baseline_slope_px_per_px": 0.0, "reference_x": 85.0}
    outputs["controls"]["corrected_one_sided_pair"] = {
        "continuous_source": display_path(one_cont),
        "continuous_sha256": sha256(one_cont),
        "disconnected_source": display_path(one_disc),
        "disconnected_sha256": sha256(one_disc),
        "measurement_comparison": _compare_measurements(measure_bridge(one_cont, [], one_roi, one_band), measure_bridge(one_disc, [], one_roi, one_band)),
        "box_only_state_equal": one_pair["checks"]["box_only_complete_assignment_state_equivalent"],
    }
    outputs["controls"]["identical_pixel_negative_control"] = {
        "measurement_comparison": _compare_measurements(continuous_measurement, continuous_measurement),
        "rejected_as_distinct": not _compare_measurements(continuous_measurement, continuous_measurement)["any_raw_difference"],
    }
    altered_payload = json.loads(json.dumps(payload))
    altered_payload["rows"][0] = altered_payload["rows"][0].replace("\t10\t20\t10\t10\t95\tsame", "\t11\t20\t10\t10\t95\tsame")
    outputs["controls"]["different_box_input_negative_control"] = {
        "original_input_sha256": _canonical_digest(payload),
        "altered_input_sha256": _canonical_digest(altered_payload),
        "rejected_as_same_input": _canonical_digest(payload) == _canonical_digest(altered_payload),
    }
    return outputs


def _compare_measurements(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    left_thresholds = left["raw_observations"]["thresholds"]
    right_thresholds = right["raw_observations"]["thresholds"]
    fields = ("ink_occupancy", "occupied_column_fraction", "max_empty_column_run_px", "row_ink_counts", "baseline_aligned_ink_fraction")
    comparisons: dict[str, Any] = {}
    for threshold in left_thresholds:
        comparisons[threshold] = {field: left_thresholds[threshold][field] != right_thresholds[threshold][field] for field in fields}
    comparisons["components"] = left["raw_observations"]["components"] != right["raw_observations"]["components"]
    return {
        "raw_field_differences": comparisons,
        "any_raw_difference": any(
            value
            for key, value in comparisons.items()
            if key == "components" or isinstance(value, bool)
        )
        or any(any(values.values()) for key, values in comparisons.items() if isinstance(values, dict)),
        "interpretation": "difference means the measured observations differ; it does not establish physical-line identity",
    }


def _measurement_relationships(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Record exploratory pairwise relationships without combining signals."""

    fields = {
        "ink_occupancy": lambda observations: observations["thresholds"]["128"]["ink_occupancy"],
        "occupied_column_fraction": lambda observations: observations["thresholds"]["128"]["occupied_column_fraction"],
        "max_empty_column_run_px": lambda observations: observations["thresholds"]["128"]["max_empty_column_run_px"],
        "native_8_component_count": lambda observations: observations["components"]["128"]["1"]["8"]["count"],
    }
    values: dict[str, list[float]] = {name: [] for name in fields}
    for case in cases:
        observations = case["measurements"]["raw_observations"]
        for name, extractor in fields.items():
            values[name].append(float(extractor(observations)))

    def correlation(left: Sequence[float], right: Sequence[float]) -> float | None:
        left_mean = sum(left) / len(left)
        right_mean = sum(right) / len(right)
        numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right))
        left_norm = math.sqrt(sum((a - left_mean) ** 2 for a in left))
        right_norm = math.sqrt(sum((b - right_mean) ** 2 for b in right))
        return None if not left_norm or not right_norm else numerator / (left_norm * right_norm)

    relationships = {}
    names = list(fields)
    for index, left_name in enumerate(names):
        for right_name in names[index + 1 :]:
            relationships[f"{left_name}__{right_name}"] = {
                "sample_count": len(cases),
                "pearson_r": correlation(values[left_name], values[right_name]),
                "interpretation": "exploratory correlation across constructed cases; not independent evidence or a production combination",
            }
    return relationships


def _geometry_page(fixture_id: str, side: str) -> tuple[dict[str, Any], Path]:
    path = PRIOR_RESIDUAL_ROOT / fixture_id / "geometry.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return next(page for page in payload["pages"] if page["side"] == side), path


def _real_case(
    image_root: Path,
    fixture_id: str,
    side: str,
    image_path: Path,
    case_id: str,
    source_rows: Sequence[int],
    interval: Mapping[str, int],
    band: Mapping[str, float],
) -> dict[str, Any]:
    page, geometry_path = _geometry_page(fixture_id, side)
    token_by_row = {token["source_row"]: token for token in page["tokens"]}
    boxes = [
        {
            "source_row": token_by_row[row]["source_row"],
            "x": token_by_row[row]["x_px"],
            "y": token_by_row[row]["y_px"],
            "width": token_by_row[row]["width_px"],
            "height": token_by_row[row]["height_px"],
        }
        for row in source_rows
    ]
    measurement = measure_bridge(image_path, boxes, interval, band)
    return {
        "case_id": case_id,
        "fixture_id": fixture_id,
        "side": side,
        "stable_token_identities": [[fixture_id, side, row] for row in source_rows],
        "geometry_source": str(geometry_path.relative_to(REPOSITORY_ROOT)),
        "geometry_source_sha256": sha256(geometry_path),
        "image_reference": str(image_path),
        "image_sha256": sha256(image_path),
        "image_dimensions_px": Image.open(image_path).size,
        "region_of_interest": dict(interval),
        "candidate_token_band": dict(band),
        "measurements": measurement,
        "assignment_observation": {
            "recorded_geometry_state": [
                {"source_row": token_by_row[row]["source_row"], "physical_line_id": token_by_row[row]["physical_line_id"], "candidate_line_ids": token_by_row[row]["candidate_line_ids"]}
                for row in source_rows
            ],
            "authority": "preserved assignment observation, not a pixel-derived result",
        },
    }


def _real_scan_results(real_root: Path) -> dict[str, Any]:
    image_path = real_root / "relativity_pdf17_pp40-41/preprocessed/relativity_pdf17_pp40-41.right.png"
    image10 = real_root / "relativity_pdf10_pp26-27/preprocessed/relativity_pdf10_pp26-27.left.png"
    if not image_path.is_file() or not image10.is_file():
        return {
            "available": False,
            "limitation": f"Required preserved preprocessed images were not available under {real_root}; no synthetic substitute was used.",
            "cases": [],
        }
    page17, _ = _geometry_page("relativity_pdf17_pp40-41", "right")
    tokens17 = {token["source_row"]: token for token in page17["tokens"]}
    lightning = tokens17[22]
    token_a = tokens17[23]
    same_line = tokens17[21]
    distinct_row = tokens17[30]
    cases = [
        _real_case(
            real_root,
            "relativity_pdf17_pp40-41",
            "right",
            image_path,
            "lightning_A_contact",
            [22, 23],
            {"x0": token_a["x_px"], "x1": lightning["x_px"] + lightning["width_px"], "y0": min(token_a["y_px"], lightning["y_px"]), "y1": max(token_a["bottom_px"], lightning["bottom_px"])},
            {"band_y0": 118, "band_y1": 146, "baseline_y": 131.5, "baseline_slope_px_per_px": 0.0, "reference_x": 515.0},
        ),
        _real_case(
            real_root,
            "relativity_pdf17_pp40-41",
            "right",
            image_path,
            "same_band_of_lightning",
            [21, 22],
            {"x0": same_line["x_px"] + same_line["width_px"], "x1": lightning["x_px"], "y0": 122, "y1": 142},
            {"band_y0": 122, "band_y1": 142, "baseline_y": 132.25, "baseline_slope_px_per_px": 0.0, "reference_x": 405.0},
        ),
        _real_case(
            real_root,
            "relativity_pdf17_pp40-41",
            "right",
            image_path,
            "nearby_distinct_rows_29_30",
            [29, 30],
            {"x0": tokens17[29]["x_px"] + tokens17[29]["width_px"], "x1": distinct_row["x_px"], "y0": 151, "y1": 166},
            {"band_y0": 151, "band_y1": 166, "baseline_y": 158.5, "baseline_slope_px_per_px": 0.0, "reference_x": 361.0},
        ),
    ]
    interpretations = {
        "lightning_A_contact": "Ink is present in the overlap corridor and partly baseline-aligned, but the boxes overlap and provide no positive blank bridge interval; continuity remains inconclusive.",
        "same_band_of_lightning": "The same preserved band has a blank inter-token gap; blank space is compatible with ordinary word spacing and does not refute one physical row.",
        "nearby_distinct_rows_29_30": "The nearby distinct-row interval is blank in its candidate band; this is a negative geometric control, not a general separation proof.",
    }
    for case in cases:
        case["interpretation"] = interpretations[case["case_id"]]
    # One Relativity 10 observation is included only as a horizontal control;
    # the vertical-fragmentation question is explicitly out of scope here.
    return {
        "available": True,
        "root": str(real_root),
        "cases": cases,
        "relativity10_horizontal_reference": {
            "fixture_id": "relativity_pdf10_pp26-27",
            "image_sha256": sha256(image10),
            "image_reference": str(image10),
            "note": "available as a possible horizontal observation; no vertical residual was resolved",
        },
    }


def _artifact_inventory(root: Path) -> list[dict[str, Any]]:
    inventory = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "manifest.json" or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        inventory.append({"path": str(path.relative_to(REPOSITORY_ROOT)), "sha256": sha256(path), "size_bytes": path.stat().st_size})
    return inventory


def run_prototype(
    output_root: Path = RESEARCH_ROOT,
    *,
    real_root: Path = DEFAULT_REAL_ROOT,
    include_real: bool = True,
    write_manifest: bool = True,
    require_exact_revision: bool = False,
) -> dict[str, Any]:
    verification = verify_research_contract(require_exact_revision=require_exact_revision)
    output_root.mkdir(parents=True, exist_ok=True)
    synthetic = _synthetic_cases(output_root)
    real = _real_scan_results(real_root) if include_real else {"available": False, "skipped": True, "cases": []}
    result = {
        "schema": "normalize-pixel-evidence-prototype-v1",
        "baseline_commit": BASELINE_COMMIT,
        "verification": verification,
        "geometry_module_used": False,
        "identity_complete_oracle_used_for_assignments": False,
        "measurement_interface": {
            "function": "measure_bridge",
            "returns": "raw observations only",
            "assignment_decision": False,
            "same_line_classifier": False,
            "combined_score": False,
        },
        "parameters": PARAMETERS,
        "synthetic": synthetic,
        "real_scan": real,
        "information_boundary": {
            "established": [
                "occupancy, occupied columns, empty runs, vertical distributions, baseline-relative alignment, and components distinguish the corrected constructed pairs",
                "the box-only assignment state is inherited from the preserved identity-complete evidence and remains equivalent for those pairs",
            ],
            "not_established": [
                "a measurement that identifies physical-line identity for arbitrary scans",
                "a threshold independent of scale, noise, skew, text size, spacing, neighboring rows, and preprocessing",
                "that detected ink belongs to the same physical line rather than a neighboring row or artifact",
            ],
        },
    }
    result_path = output_root / "results.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if write_manifest:
        manifest = {
            "schema": "normalize-pixel-evidence-prototype-manifest-v1",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "experiment_start": {
                "git_commit_sha": BASELINE_COMMIT,
                "git_branch": "pixel-evidence-prototype",
                "git_status": "clean (verified before research edits)",
            },
            "generation_state": {
                "git_commit_sha": _git("rev-parse", "HEAD"),
                "git_branch": _git("branch", "--show-current"),
                "git_status_porcelain": _git("status", "--short"),
            },
            "verification": verification,
            "environment": {
                "python": sys.version,
                "python_executable": sys.executable,
                "packages": _package_versions(),
                "geometry_module_import_path": str((REPOSITORY_ROOT / "src/normalize/geometry.py").resolve()),
                "tesseract": subprocess.run(["tesseract", "--version"], check=True, text=True, capture_output=True).stdout.splitlines()[0],
            },
            "commands": [
                ".venv/bin/python research/geometry/pixel-evidence-prototype/prototype.py --real-root /tmp/normalize-residual-forensics",
                ".venv/bin/python -m pytest -q tests/test_pixel_evidence_prototype.py",
                ".venv/bin/python -m pytest -q",
            ],
            "input_provenance": {
                "prior_corrected_experiment_results": {"path": str(PRIOR_RESULTS.relative_to(REPOSITORY_ROOT)), "sha256": sha256(PRIOR_RESULTS)},
                "synthetic_box_input_sha256": synthetic["shared_input_sha256"],
                "prior_corrected_pixel_inputs": [
                    {"path": str(path.relative_to(REPOSITORY_ROOT)), "sha256": sha256(path), "source": "preserved synthetic source image"}
                    for path in sorted(PRIOR_PIXEL_ROOT.glob("*.png"))
                ],
                "preserved_real_scan_references": [
                    {"path": str(path.relative_to(REPOSITORY_ROOT)), "sha256": sha256(path)}
                    for path in (PRIOR_RESIDUAL_ROOT / "relativity_pdf17_pp40-41/geometry.json", PRIOR_RESIDUAL_ROOT / "relativity_pdf10_pp26-27/geometry.json")
                ],
                "real_scan_external_local_root": str(real_root),
                "real_scan_image_inputs": [
                    {"reference": reference, "sha256": image_hash}
                    for reference, image_hash in sorted({
                        (case["image_reference"], case["image_sha256"])
                        for case in real.get("cases", [])
                    })
                ],
                "source_pdfs_copied": False,
            },
            "measurement_parameters": PARAMETERS,
            "real_scan_availability": {"available": real.get("available", False), "root": str(real_root)},
            "artifact_paths_and_hashes": _artifact_inventory(output_root),
            "restrictions": {
                "production_geometry_modified": False,
                "identity_complete_oracle_modified": False,
                "existing_research_snapshots_modified": False,
                "fixture_contracts_modified": False,
                "source_pdfs_committed": False,
                "dependencies_installed": False,
                "symphony_modified": False,
            },
        }
        (output_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=RESEARCH_ROOT)
    parser.add_argument("--real-root", type=Path, default=DEFAULT_REAL_ROOT)
    parser.add_argument("--skip-real", action="store_true")
    parser.add_argument(
        "--exact-historical-revision",
        action="store_true",
        help="require the historical baseline revision instead of a verified descendant",
    )
    args = parser.parse_args()
    result = run_prototype(
        args.output_root,
        real_root=args.real_root,
        include_real=not args.skip_real,
        require_exact_revision=args.exact_historical_revision,
    )
    print(json.dumps({"output": str(args.output_root), "synthetic_cases": len(result["synthetic"]["adversarial_cases"]), "real_scan_available": result["real_scan"]["available"]}, indent=2))


if __name__ == "__main__":
    main()
