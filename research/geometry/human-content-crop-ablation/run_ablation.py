"""Run OCR/geometry on the six user-supplied human content crops.

The manual JPEGs are authoritative inputs. This harness records their
provenance, measures one page-wide correction from pixels, applies the prior
study's bicubic-expand / white-fill / LANCZOS 300-to-144-DPI-equivalent path,
then invokes Tesseract once per page and the unchanged production parser and
geometry functions. It does not detect or revise crop bounds.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
import math
import sys
import tempfile
from pathlib import Path
from statistics import median
from typing import Any

import cv2
import numpy as np
import pytesseract
from PIL import Image
from pytesseract import Output

ROOT = Path(__file__).resolve().parents[3]
SOURCE_DIR = ROOT / "fixtures/einstein/spineless"
MANUAL_DIR = SOURCE_DIR / "manual_crops"
PRIOR_DIR = ROOT / "research/geometry/spineless-acquisition-ablation"
PRIOR_RESULTS_PATH = PRIOR_DIR / "results.json"
ORACLE_PATH = Path(__file__).with_name("row-oracle.json")
PHYSICAL_BASELINE_PATH = Path(__file__).with_name("physical-sheet-baseline.json")
PRIOR_ROW_CLASSES_PATH = Path(__file__).with_name("prior-row-classifications.json")
OUT_DIR = Path(__file__).resolve().parent
PAGES = (26, 27, 40, 41, 52, 53)
SCALE = 144 / 300
OCR_LANGUAGE = "eng"
OCR_CONFIG = "--psm 6"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_safe(value: Any) -> Any:
    """Preserve image metadata values without emitting non-JSON byte objects."""
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex()}
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def round_half_up(value: float) -> int:
    return math.floor(value + 0.5)


def prior_studies() -> tuple[dict[str, Any], dict[str, Any]]:
    return json.loads(PRIOR_RESULTS_PATH.read_text()), json.loads(ORACLE_PATH.read_text())


def jpeg_quantization(path: Path) -> dict[str, Any]:
    """Record JPEG quantization tables as evidence of encoding differences."""
    with Image.open(path) as image:
        tables = {str(key): list(value) for key, value in sorted((image.quantization or {}).items())}
    serialized = json.dumps(tables, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"tables": tables, "tables_sha256": sha256(serialized)}


def estimate_regional_correction(image: Image.Image) -> dict[str, Any]:
    """Use the prior study's dark-row projection method on three crop regions."""
    gray = np.asarray(image.convert("L"))
    height, width = gray.shape
    x0, x1 = int(width * 0.06), int(width * 0.94)
    regions = [
        (int(height * 0.22), int(height * 0.48)),
        (int(height * 0.46), int(height * 0.72)),
        (int(height * 0.68), int(height * 0.92)),
    ]
    angle_grid = np.arange(-1.5, 1.5001, 0.02)
    corrections: list[float] = []
    for y0, y1 in regions:
        mask = np.where(gray[y0:y1, x0:x1] < 130, 255, 0).astype(np.uint8)
        roi_height, roi_width = mask.shape
        center = (roi_width / 2, roi_height / 2)
        scores = []
        for angle in angle_grid:
            matrix = cv2.getRotationMatrix2D(center, float(angle), 1.0)
            rotated = cv2.warpAffine(
                mask,
                matrix,
                (roi_width, roi_height),
                flags=cv2.INTER_NEAREST,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=0,
            )
            projection = rotated.sum(axis=1, dtype=np.float64)
            scores.append(float(projection @ projection))
        corrections.append(float(angle_grid[int(np.argmax(scores))]))
    return {
        "method": "dark-pixel horizontal-projection energy, grayscale<130, 0.02-degree grid; prior spineless method",
        "roi_x_px": [x0, x1],
        "regions_y_px": [list(bounds) for bounds in regions],
        "regional_corrections_degrees": corrections,
        "used_correction_degrees": float(median(corrections)),
        "median_absolute_deviation_degrees": float(median(abs(value - median(corrections)) for value in corrections)),
        "agreement_range_degrees": max(corrections) - min(corrections),
    }


def prepare_final_raster(image: Image.Image, angle: float) -> tuple[Image.Image, Image.Image]:
    """Apply one rigid page correction, then the established 144/300 reduction."""
    source = image.convert("RGB")
    rotated = source if angle == 0 else source.rotate(
        angle,
        resample=Image.Resampling.BICUBIC,
        expand=True,
        fillcolor=(255, 255, 255),
    )
    final_size = (
        round_half_up(rotated.width * SCALE),
        round_half_up(rotated.height * SCALE),
    )
    return rotated, rotated.resize(final_size, Image.Resampling.LANCZOS)


def register_images(source: np.ndarray, destination: np.ndarray) -> dict[str, Any]:
    """Estimate a pixel-only similarity transform for row identity crosswalk."""
    source_gray = cv2.cvtColor(source, cv2.COLOR_RGB2GRAY) if source.ndim == 3 else source
    destination_gray = cv2.cvtColor(destination, cv2.COLOR_RGB2GRAY) if destination.ndim == 3 else destination
    orb = cv2.ORB_create(nfeatures=20000, scaleFactor=1.2, nlevels=8, edgeThreshold=15, fastThreshold=8)
    source_points, source_descriptors = orb.detectAndCompute(source_gray, None)
    destination_points, destination_descriptors = orb.detectAndCompute(destination_gray, None)
    matches = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(source_descriptors, destination_descriptors, k=2)
    good = [first for first, second in matches if first.distance < 0.72 * second.distance]
    source_xy = np.float32([source_points[match.queryIdx].pt for match in good])
    destination_xy = np.float32([destination_points[match.trainIdx].pt for match in good])
    cv2.setRNGSeed(271828)
    affine, inlier_mask = cv2.estimateAffinePartial2D(
        source_xy,
        destination_xy,
        method=cv2.RANSAC,
        ransacReprojThreshold=2.5,
        maxIters=5000,
        confidence=0.999,
    )
    if affine is None or inlier_mask is None or int(inlier_mask.sum()) < 100:
        raise RuntimeError("pixel registration failed to establish page-row correspondence")
    inliers = inlier_mask.ravel().astype(bool)
    projected = cv2.transform(source_xy[inliers].reshape(1, -1, 2), affine)[0]
    residual = np.linalg.norm(projected - destination_xy[inliers], axis=1)
    scale = float(math.hypot(affine[0, 0], affine[1, 0]))
    angle = float(math.degrees(math.atan2(affine[1, 0], affine[0, 0])))
    return {
        "method": "ORB correspondences + RANSAC similarity affine; pixels only",
        "source_keypoints": len(source_points),
        "destination_keypoints": len(destination_points),
        "ratio_test_matches": len(good),
        "inliers": int(inliers.sum()),
        "inlier_fraction_of_matches": float(inliers.sum() / max(len(good), 1)),
        "median_inlier_reprojection_error_px": float(np.median(residual)),
        "affine_source_to_destination": affine.tolist(),
        "scale": scale,
        "rotation_degrees": angle,
        "translation_xy": [float(affine[0, 2]), float(affine[1, 2])],
    }


def register_manual_to_original(source: np.ndarray, manual: np.ndarray) -> dict[str, Any]:
    reg = register_images(manual, source)
    tx, ty = reg["translation_xy"]
    x0, y0 = round(tx), round(ty)
    h, w = manual.shape[:2]
    source_slice = source[y0:y0 + h, x0:x0 + w]
    if source_slice.shape != manual.shape:
        raise RuntimeError("manual crop registration maps outside original source dimensions")
    delta = np.abs(source_slice.astype(np.int16) - manual.astype(np.int16))
    reg.update({
        "rounded_source_crop_xyxy": [x0, y0, x0 + w, y0 + h],
        "same_dimensions_as_source_rectangle": True,
        "decoded_pixel_equal_fraction": float(np.all(delta == 0, axis=2).mean()),
        "decoded_rgb_mean_absolute_difference": float(delta.mean()),
        "decoded_rgb_p95_absolute_difference": float(np.percentile(delta, 95)),
        "decoded_rgb_max_absolute_difference": int(delta.max()),
        "pixel_subset_exact": bool(np.array_equal(source_slice, manual)),
        "interpretation": "same-resolution source crop with lossy pixel differences consistent with JPEG recompression",
    })
    return reg


def parse_raw_words(tsv: str) -> list[dict[str, Any]]:
    words = []
    for source_row, row in enumerate(csv.DictReader(io.StringIO(tsv), delimiter="\t"), start=1):
        if row.get("level") != "5" or not row.get("text", "").strip():
            continue
        left, top, width, height = (int(row[key]) for key in ("left", "top", "width", "height"))
        words.append({
            "source_tsv_row": source_row,
            "ids": [int(row[key]) for key in ("page_num", "block_num", "par_num", "line_num", "word_num")],
            "box_xyxy": [left, top, left + width, top + height],
            "confidence": float(row["conf"]),
            "text_locator": row["text"],
        })
    return words


def production_geometry(tsv: str, size: tuple[int, int]) -> dict[str, Any]:
    """Call the current parser and grouping functions without altering them."""
    from normalize.geometry import group_physical_lines, parse_tsv_rows

    tokens, row_errors = parse_tsv_rows(tsv, *size)
    lines, unresolved, measurements = group_physical_lines(tokens)
    token_to_line: dict[int, str] = {}
    for line in lines:
        for token_id in line["token_ids"]:
            token_to_line[int(token_id.removeprefix("token-"))] = line["line_id"]
    unresolved_by_row = {item["token_source_row"]: item for item in unresolved}
    token_records = []
    for token in tokens:
        token_records.append({
            "source_row": token.source_row,
            "text_locator": token.text,
            "confidence": token.confidence,
            "ids": [token.page_num, token.block_num, token.par_num, token.line_num, token.word_num],
            "box_xyxy": [token.x, token.y, token.x1, token.y1],
            "center_xy": [(token.x + token.x1) / 2, token.center_y],
            "physical_line_id": token_to_line.get(token.source_row),
            "candidate_line_ids": unresolved_by_row.get(token.source_row, {}).get("candidate_line_ids", []),
        })
    return {
        "tokens": token_records,
        "physical_lines": lines,
        "unresolved": unresolved,
        "row_errors": row_errors,
        "measurements": measurements,
        "admitted_token_count": len(tokens),
        "physical_line_count": len(lines),
        "ambiguous_count": sum(item["code"] == "ambiguous_line_assignment" for item in unresolved),
        "unassigned_count": sum(item["code"] == "unassigned_line_assignment" for item in unresolved),
    }


def build_prior_raster(page: int, prior_page: dict[str, Any]) -> Image.Image:
    """Rebuild the archived physical-sheet raster to register the row oracle."""
    spec = importlib.util.spec_from_file_location("prior_spineless_ablation", PRIOR_DIR / "run_ablation.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot import prior spineless raster preparation")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source_path = SOURCE_DIR / f"pg.{page}.jpg"
    with Image.open(source_path) as source:
        _, _, final = module.prepare_spineless_raster(
            source,
            tuple(prior_page["crop_box"]),
            float(prior_page["angle_correction_degrees"]),
        )
    if sha256(final.tobytes()) != prior_page["transform"]["final_rgb_sha256"]:
        raise RuntimeError(f"prior page-{page} physical-sheet raster did not reproduce")
    return final


def transform_point(affine: list[list[float]], x: float, y: float) -> tuple[float, float]:
    return (
        affine[0][0] * x + affine[0][1] * y + affine[0][2],
        affine[1][0] * x + affine[1][1] * y + affine[1][2],
    )


def map_row_oracle(
    page: int,
    oracle_page: dict[str, Any],
    affine: list[list[float]],
) -> list[dict[str, Any]]:
    rows = []
    for block in oracle_page["blocks"]:
        for ordinal, (y0, y1) in enumerate(block["rows"], start=1):
            x0, x1 = oracle_page["pixel_roi_x"]
            corners = [
                transform_point(affine, x0, y0),
                transform_point(affine, x1, y0),
                transform_point(affine, x0, y1),
                transform_point(affine, x1, y1),
            ]
            row_id = f"p{page}-{block['block_id']}-row-{ordinal:02d}"
            rows.append({
                "physical_row_id": row_id,
                "page": page,
                "source_oracle_band_y": [y0, y1],
                "source_oracle_x_roi": [x0, x1],
                "human_final_pixel_quad": [[round(x, 3), round(y, 3)] for x, y in corners],
                "human_final_pixel_envelope": [
                    math.floor(min(point[0] for point in corners)),
                    math.floor(min(point[1] for point in corners)),
                    math.ceil(max(point[0] for point in corners)),
                    math.ceil(max(point[1] for point in corners)),
                ],
            })
    return rows


def assign_tokens_to_physical_rows(
    page_rows: list[dict[str, Any]],
    tokens: list[dict[str, Any]],
    max_center_distance_px: float = 16.0,
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    """Map token centers to nearest registered pixel band, never by wording."""
    bands = []
    for row in page_rows:
        quad = row["human_final_pixel_quad"]
        center_y = sum(point[1] for point in quad) / 4
        y_min = min(point[1] for point in quad)
        y_max = max(point[1] for point in quad)
        bands.append((row, center_y, y_min, y_max))
    assigned = {row["physical_row_id"]: [] for row in page_rows}
    unassociated = []
    for token in tokens:
        x0, y0, x1, y1 = token["box_xyxy"]
        center_x, center_y = (x0 + x1) / 2, (y0 + y1) / 2
        candidates = []
        for row, row_center, row_y0, row_y1 in bands:
            quad = row["human_final_pixel_quad"]
            row_x0 = min(point[0] for point in quad)
            row_x1 = max(point[0] for point in quad)
            if center_x < row_x0 - 8 or center_x > row_x1 + 8:
                continue
            distance = abs(center_y - row_center)
            overlap = max(0.0, min(y1, row_y1) - max(y0, row_y0))
            candidates.append((distance, -overlap, row))
        if not candidates:
            unassociated.append({"source_row": token["source_row"], "reason": "center outside oracle x extent"})
            continue
        distance, negative_overlap, selected = min(candidates, key=lambda item: (item[0], item[1]))
        if distance > max_center_distance_px and negative_overlap == 0:
            unassociated.append({"source_row": token["source_row"], "reason": "center outside physical ink-band assignment radius", "nearest_distance_px": distance})
            continue
        assigned[selected["physical_row_id"]].append(token)
    return assigned, unassociated


def adjudicate_rows(
    page_rows: list[dict[str, Any]],
    assigned: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    all_memberships: dict[str, set[str]] = {}
    for physical_row_id, tokens in assigned.items():
        for token in tokens:
            line_id = token["physical_line_id"]
            if line_id:
                all_memberships.setdefault(line_id, set()).add(physical_row_id)
    results = []
    for row in page_rows:
        physical_row_id = row["physical_row_id"]
        tokens = assigned[physical_row_id]
        line_ids = sorted({token["physical_line_id"] for token in tokens if token["physical_line_id"]})
        neighbor_row_ids = sorted({
            other for line_id in line_ids for other in all_memberships.get(line_id, set())
            if other != physical_row_id
        })
        if not tokens or not line_ids:
            classification = "unresolved"
        elif len(line_ids) > 1:
            classification = "false_split"
        elif neighbor_row_ids:
            classification = "destructive_merge"
        else:
            classification = "correct_single_line"
        results.append({
            **row,
            "classification": classification,
            "mapped_token_source_rows": [token["source_row"] for token in tokens],
            "mapped_token_locators": [token["text_locator"] for token in tokens],
            "production_line_ids": line_ids,
            "merged_with_physical_row_ids": neighbor_row_ids,
        })
    return results


def run() -> dict[str, Any]:
    prior_acquisition, oracle = prior_studies()
    physical_baseline = json.loads(PHYSICAL_BASELINE_PATH.read_text())["pages"]
    prior_row_classes = json.loads(PRIOR_ROW_CLASSES_PATH.read_text())["pages"]
    version = str(pytesseract.get_tesseract_version()).strip()
    if version != "5.3.4":
        raise RuntimeError(f"expected Tesseract 5.3.4, found {version}")
    pages: dict[str, Any] = {}
    row_results: dict[str, Any] = {}
    raw_comparisons: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="normalize-human-content-crop-") as temp:
        temp_root = Path(temp)
        for page in PAGES:
            source_path = SOURCE_DIR / f"pg.{page}.jpg"
            manual_path = MANUAL_DIR / f"pg.{page}_cropped.jpg"
            with Image.open(source_path) as source_image:
                source_rgb = np.asarray(source_image.convert("RGB"))
                source_info = dict(source_image.info)
                source_size = source_image.size
                source_quantization = jpeg_quantization(source_path)
            with Image.open(manual_path) as opened:
                manual = opened.convert("RGB")
                manual_info = dict(opened.info)
                manual_size = opened.size
                manual_mode = opened.mode
                manual_rgb = np.asarray(manual)
                manual_quantization = jpeg_quantization(manual_path)
            prior_page = prior_acquisition["spineless"][str(page)]
            if sha256(source_path.read_bytes()) != prior_page["source_sha256"]:
                raise RuntimeError(f"source page-{page} hash differs from prior study")
            source_registration = register_manual_to_original(source_rgb, manual_rgb)
            orientation = estimate_regional_correction(manual)
            applied_angle = orientation["used_correction_degrees"]
            rotated, final = prepare_final_raster(manual, applied_angle)
            final_hash = sha256(final.tobytes())

            # This is the only OCR invocation on the human crop for this page.
            tsv = pytesseract.image_to_data(
                final,
                lang=OCR_LANGUAGE,
                config=OCR_CONFIG,
                output_type=Output.STRING,
            )
            raw_words = parse_raw_words(tsv)
            geometry = production_geometry(tsv, final.size)
            oracle_page = oracle["pages"][str(page)]
            baseline = build_prior_raster(page, prior_page)
            registration = register_images(
                np.asarray(baseline.convert("RGB")),
                np.asarray(final.convert("RGB")),
            )
            mapped_rows = map_row_oracle(
                page,
                oracle_page,
                registration["affine_source_to_destination"],
            )
            assigned, unassociated = assign_tokens_to_physical_rows(mapped_rows, geometry["tokens"])
            adjudicated = adjudicate_rows(mapped_rows, assigned)
            prior_class_by_band = {
                tuple(item["source_oracle_band_y"]): item["classification"]
                for item in prior_row_classes[str(page)]["rows"]
            }
            for row in adjudicated:
                prior_classification = prior_class_by_band[tuple(row["source_oracle_band_y"])]
                row["physical_sheet_classification"] = prior_classification
                row["transition"] = (
                    "repaired_false_split"
                    if prior_classification == "false_split" and row["classification"] == "correct_single_line"
                    else "persistent_false_split"
                    if prior_classification == "false_split" and row["classification"] == "false_split"
                    else "new_false_split"
                    if prior_classification == "correct_single_band" and row["classification"] == "false_split"
                    else "both_correct"
                    if prior_classification == "correct_single_band" and row["classification"] == "correct_single_line"
                    else "changed_oracle_classification"
                )
            row_counts = {
                name: sum(row["classification"] == name for row in adjudicated)
                for name in ("correct_single_line", "false_split", "destructive_merge", "unresolved")
            }
            source_row = {
                "page": page,
                "source_filename": source_path.name,
                "source_dimensions": list(source_size),
                "source_sha256": sha256(source_path.read_bytes()),
                "source_mode": "RGB",
                "source_jpeg_metadata": {**json_safe(source_info), "quantization": source_quantization},
                "manual_filename": manual_path.name,
                "manual_dimensions": list(manual_size),
                "manual_mode": manual_mode,
                "manual_sha256": sha256(manual_path.read_bytes()),
                "manual_jpeg_metadata": {**json_safe(manual_info), "quantization": manual_quantization},
                "manual_to_source_registration": source_registration,
                "orientation": {
                    **orientation,
                    "prior_spineless_correction_degrees": prior_page["angle_correction_degrees"],
                    "difference_from_prior_degrees": applied_angle - prior_page["angle_correction_degrees"],
                    "applied": applied_angle,
                    "rationale": "manual crop registration shows no prior rotation; independently measured median correction is close to prior physical-sheet estimate",
                },
                "transform": {
                    "input_dimensions": list(manual_size),
                    "rotation": "Pillow Image.rotate",
                    "angle_degrees": applied_angle,
                    "interpolation": "bicubic",
                    "expand": True,
                    "background_rgb": [255, 255, 255],
                    "post_rotation_dimensions": list(rotated.size),
                    "downsample": "Pillow LANCZOS",
                    "dimension_rule": "nearest integer, half upward, at 144/300 scale",
                    "final_dimensions": list(final.size),
                    "final_rgb_sha256": final_hash,
                },
            }
            pages[str(page)] = {
                **source_row,
                "ocr": {
                    "tesseract_version": version,
                    "language": OCR_LANGUAGE,
                    "config": OCR_CONFIG,
                    "invocations_on_manual_crop": 1,
                    "raw_tsv_sha256": sha256(tsv.encode("utf-8")),
                    "raw_tsv_word_count": len(raw_words),
                    "admitted_token_count": geometry["admitted_token_count"],
                    "physical_line_count": geometry["physical_line_count"],
                    "ambiguous_count": geometry["ambiguous_count"],
                    "unassigned_count": geometry["unassigned_count"],
                    "median_admitted_confidence": float(median(token["confidence"] for token in geometry["tokens"])) if geometry["tokens"] else None,
                    "production_measurements": geometry["measurements"],
                    "row_errors": geometry["row_errors"],
                    "unresolved": geometry["unresolved"],
                    "line_memberships": [
                        {
                            "line_id": line["line_id"],
                            "token_ids": line["token_ids"],
                            "bounds_xyxy": [line["left_px"], line["top_px"], line["right_px"], line["bottom_px"]],
                            "median_center_y_px": line["median_center_y_px"],
                        }
                        for line in geometry["physical_lines"]
                    ],
                    "tokens": geometry["tokens"],
                    "raw_word_records": raw_words,
                    "raw_tsv": tsv,
                },
                "row_oracle_registration_from_prior_spineless": registration,
                "row_oracle_counts": row_counts,
                "row_oracle_unassociated_token_count": len(unassociated),
            }
            row_results[str(page)] = {
                "page": page,
                "oracle_source_commit": "22912345ceee5330bffe02bc189ce2b38075ce52",
                "oracle_raster_sha256": oracle_page["raster_sha256"],
                "registration": registration,
                "max_center_assignment_distance_px": 16.0,
                "counts": row_counts,
                "unassociated_tokens": unassociated,
                "rows": adjudicated,
            }
            raw_comparisons[str(page)] = {
                "page": page,
                "physical_sheet_prior": {
                    "raw_tsv_sha256": prior_page["tsv_sha256"],
                    "raw_word_count": physical_baseline[str(page)]["raw_word_count"],
                    "raw_word_count_available": True,
                    "admitted_token_count": prior_page["geometry"]["token_count"],
                    "physical_line_count": prior_page["geometry"]["line_count"],
                    "ambiguous_count": prior_page["geometry"]["ambiguous_count"],
                    "unassigned_count": prior_page["geometry"]["unassigned_count"],
                    "median_admitted_confidence": physical_baseline[str(page)]["median_admitted_confidence"],
                    "selected_slope": prior_page["geometry"]["measurements"]["baseline_slope_px_per_px"],
                    "vertical_tolerance": prior_page["geometry"]["measurements"]["tolerance_px"],
                    "horizontal_gap_limit": prior_page["geometry"]["measurements"]["horizontal_gap_limit_px"],
                    "tokens": prior_page["geometry"]["tokens"],
                    "line_memberships": prior_page["line_texts"],
                },
                "human_content_crop": pages[str(page)]["ocr"],
            }

    all_rows = [row for page_data in row_results.values() for row in page_data["rows"]]
    total_counts = {
        name: sum(row["classification"] == name for row in all_rows)
        for name in ("correct_single_line", "false_split", "destructive_merge", "unresolved")
    }
    return {
        "schema": "human-content-crop-ablation-v1",
        "starting_commit": "2d7918efa63e89357fa4bc6239da1aadbe2ac367",
        "historical_inputs": {
            "spineless_acquisition_commit": "53ece235af82ef37fc7fe49be027301a25a8d104",
            "residual_forensics_commit": "2d7918efa63e89357fa4bc6239da1aadbe2ac367",
            "vertical_anchor_oracle_commit": "22912345ceee5330bffe02bc189ce2b38075ce52",
            "page27_context_forensics_commit": "5b644c1edad2dc0318b7cd8fbeee54299a5c7577",
        },
        "discarded_harness_attempt": {
            "manual_crop_ocr_invocations": 6,
            "reason": "The first complete run finished all six OCR calls but failed while serializing JPEG metadata bytes to JSON; the metadata encoder was corrected and the successful captured run repeated the same six page/config pairs.",
            "first_attempt_tsv_outputs_saved": False,
            "successful_recorded_primary_invocations": 6,
            "actual_manual_crop_tesseract_invocations_in_task": 12,
        },
        "production_code_modified": False,
        "tesseract": {"version": version, "language": OCR_LANGUAGE, "config": OCR_CONFIG},
        "manual_page_ocr_invocations": len(PAGES),
        "row_oracle_total_rows": len(all_rows),
        "row_oracle_total_counts": total_counts,
        "physical_sheet_oracle_counts": json.loads(PRIOR_ROW_CLASSES_PATH.read_text())["total_counts"],
        "pages": pages,
        "row_comparison": row_results,
        "ocr_comparison": raw_comparisons,
    }


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "src"))
    run_result = run()
    # Share one compact JSON ledger for raw OCR and production geometry.
    (OUT_DIR / "results.json").write_text(json.dumps(run_result, indent=2, ensure_ascii=False) + "\n")
    (OUT_DIR / "row-comparison.json").write_text(json.dumps(run_result["row_comparison"], indent=2, ensure_ascii=False) + "\n")
    (OUT_DIR / "ocr-comparison.json").write_text(json.dumps(run_result["ocr_comparison"], indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({
        "manual_ocr_invocations": run_result["manual_page_ocr_invocations"],
        "row_counts": run_result["row_oracle_total_counts"],
        "pages": {
            page: {
                "angle": record["orientation"]["applied"],
                "final_dimensions": record["transform"]["final_dimensions"],
                "tokens": record["ocr"]["admitted_token_count"],
                "lines": record["ocr"]["physical_line_count"],
                "ambiguous": record["ocr"]["ambiguous_count"],
                "unassigned": record["ocr"]["unassigned_count"],
                "slope": record["ocr"]["production_measurements"]["baseline_slope_px_per_px"],
                "oracle": record["row_oracle_counts"],
            }
            for page, record in run_result["pages"].items()
        },
    }, indent=2))
