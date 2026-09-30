"""Capture the bound-vs-spineless Relativity page geometry study.

The bound path calls the current production preprocessing and geometry entry
points. The spineless path is deliberately a research-only image adapter: it
uses explicit pixel-established page bounds, estimates one whole-sheet angle
from repeated dark-row pixels, and then calls the same OCR parser and geometry
grouping functions as production.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path
from statistics import median
from typing import Any

import cv2
import numpy as np
import pytesseract
from PIL import Image
from pytesseract import Output

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from normalize.fixtures import FixtureCatalog  # noqa: E402
from normalize import geometry as production_geometry  # noqa: E402
from normalize.geometry import group_physical_lines, parse_tsv_rows, run_geometry  # noqa: E402
from normalize.rendering import preprocess_fixture  # noqa: E402

CONFIG_PATH = ROOT / "fixtures" / "preprocessing.json"
SPINELESS_DIR = ROOT / "fixtures" / "einstein" / "spineless"
OUT_PATH = Path(__file__).with_name("results.json")
PAGES = (26, 27, 40, 41, 52, 53)
# Pixel-only paper/background inspection found the right paper edge at x=1460–
# 1478 and bottom edge at y=2294–2297. This common rectangle retains a 22 px
# minimum right margin and 43 px bottom margin around the fullest observed
# sheet edge while removing most of the scanner bed.
PAGE_BOXES = {page: (0, 0, 1500, 2340) for page in PAGES}
PAGE_FIXTURE = {
    26: ("relativity_pdf10_pp26-27", "left"),
    27: ("relativity_pdf10_pp26-27", "right"),
    40: ("relativity_pdf17_pp40-41", "left"),
    41: ("relativity_pdf17_pp40-41", "right"),
    52: ("relativity_pdf23_pp52-53", "left"),
    53: ("relativity_pdf23_pp52-53", "right"),
}
OUTPUT_SCALE = 144 / 300
OCR_INVOCATIONS = {"bound": 0, "spineless": 0}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def round_half_up(value: float) -> int:
    """Use deterministic nearest-pixel rounding, with exact halves upward."""
    return math.floor(value + 0.5)


def row_correction_angle(image: Image.Image, y0: int, y1: int) -> float:
    """Find the pixel-only rotation maximizing repeated horizontal row energy.

    A thresholded grayscale image is rotated in 0.02-degree increments; the
    score is the sum of squared horizontal dark-pixel projections. The same
    fixed text-column ROI and method are used for each page and region.
    """
    gray = np.asarray(image.convert("L"))[y0:y1, 100:1350]
    mask = np.where(gray < 130, 255, 0).astype(np.uint8)
    height, width = mask.shape
    center = (width / 2, height / 2)
    angles = np.arange(-1.5, 1.5001, 0.02)
    scores = []
    for angle in angles:
        matrix = cv2.getRotationMatrix2D(center, float(angle), 1.0)
        rotated = cv2.warpAffine(
            mask,
            matrix,
            (width, height),
            flags=cv2.INTER_NEAREST,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )
        projection = rotated.sum(axis=1, dtype=np.float64)
        scores.append(float(projection @ projection))
    return float(angles[int(np.argmax(scores))])


def prepare_spineless_raster(
    source: Image.Image,
    crop_box: tuple[int, int, int, int],
    correction_degrees: float,
) -> tuple[Image.Image, Image.Image, Image.Image]:
    """Crop one physical sheet, rigidly deskew it, then match production DPI."""
    cropped = source.convert("RGB").crop(crop_box)
    # Literal zero is an exact no-resample path; the deskew is a whole-page
    # operation and its expanded white canvas retains the complete crop.
    deskewed = cropped if correction_degrees == 0 else cropped.rotate(
        correction_degrees,
        resample=Image.Resampling.BICUBIC,
        expand=True,
        fillcolor=(255, 255, 255),
    )
    final_size = (
        round_half_up(deskewed.width * OUTPUT_SCALE),
        round_half_up(deskewed.height * OUTPUT_SCALE),
    )
    return cropped, deskewed, deskewed.resize(final_size, Image.Resampling.LANCZOS)


def geometry_record(tsv: str, image_size: tuple[int, int]) -> dict[str, Any]:
    tokens, row_errors = parse_tsv_rows(tsv, *image_size)
    lines, unresolved, measurements = group_physical_lines(tokens)
    token_lines = {int(token_id.removeprefix("token-")): line["line_id"]
                   for line in lines for token_id in line["token_ids"]}
    unresolved_by_row = {item["token_source_row"]: item for item in unresolved}
    token_records = []
    for token in tokens:
        token_records.append({
            "source_row": token.source_row,
            "text": token.text,
            "confidence": token.confidence,
            "x": token.x,
            "y": token.y,
            "width": token.width,
            "height": token.height,
            "line_id": token_lines.get(token.source_row),
            "candidate_line_ids": unresolved_by_row.get(token.source_row, {}).get("candidate_line_ids", []),
            "tesseract_ids": [token.page_num, token.block_num, token.par_num, token.line_num, token.word_num],
        })
    return {
        "tokens": token_records,
        "physical_lines": lines,
        "unresolved": unresolved,
        "row_errors": row_errors,
        "measurements": measurements,
        "token_count": len(tokens),
        "line_count": len(lines),
        "ambiguous_count": sum(item["code"] == "ambiguous_line_assignment" for item in unresolved),
        "unassigned_count": sum(item["code"] == "unassigned_line_assignment" for item in unresolved),
    }


def line_texts(geometry: dict[str, Any]) -> list[dict[str, Any]]:
    def line_id(token: dict[str, Any]) -> str | None:
        return token.get("line_id", token.get("physical_line_id"))

    def coordinate(token: dict[str, Any], short: str) -> int:
        return int(token.get(short, token.get(f"{short}_px")))

    by_id = {line_id(token): [] for token in geometry["tokens"] if line_id(token)}
    for token in geometry["tokens"]:
        if line_id(token):
            by_id[line_id(token)].append(token)
    result = []
    for line in geometry["physical_lines"]:
        members = sorted(by_id.get(line["line_id"], []), key=lambda item: coordinate(item, "x"))
        result.append({
            "line_id": line["line_id"],
            "text": " ".join(token["text"] for token in members),
            "source_rows": [token["source_row"] for token in members],
            "bounds": [line.get("left_px"), line.get("top_px"), line.get("right_px"), line.get("bottom_px")],
        })
    return result


def capture_bound() -> dict[str, Any]:
    import tempfile

    catalog = FixtureCatalog.load(ROOT)
    captures: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="normalize-spineless-bound-") as tmp:
        temp_root = Path(tmp)
        for fixture_id in sorted({fixture for fixture, _ in PAGE_FIXTURE.values()}):
            metadata = catalog.get(fixture_id)
            preprocessed = temp_root / f"{fixture_id}-preprocess"
            result = preprocess_fixture(metadata, CONFIG_PATH, preprocessed)
            if result["status"] != "success":
                raise RuntimeError(f"current production preprocessing failed: {fixture_id}: {result}")
            # Capture the exact TSV that run_geometry consumes, while keeping
            # its normal one-call-per-side execution and output untouched.
            captured_tsvs: list[str] = []
            original_ocr_call = production_geometry.pytesseract.image_to_data

            def capture_ocr(*args: Any, **kwargs: Any) -> str:
                tsv = original_ocr_call(*args, **kwargs)
                captured_tsvs.append(tsv)
                OCR_INVOCATIONS["bound"] += 1
                return tsv

            production_geometry.pytesseract.image_to_data = capture_ocr
            try:
                geometry_result = run_geometry(preprocessed, temp_root / f"{fixture_id}-geometry")
            finally:
                production_geometry.pytesseract.image_to_data = original_ocr_call
            if geometry_result["status"] not in ("success", "uncertain"):
                raise RuntimeError(f"current production geometry failed: {fixture_id}: {geometry_result}")
            if len(captured_tsvs) != len(geometry_result["pages"]):
                raise RuntimeError("production OCR capture count did not match physical page count")
            for page_record, tsv in zip(geometry_result["pages"], captured_tsvs, strict=True):
                page_number = next(page for page, value in PAGE_FIXTURE.items() if value == (fixture_id, page_record["side"]))
                image_path = preprocessed / page_record["image_path"]
                geom = {
                    "tokens": page_record["tokens"],
                    "physical_lines": page_record["physical_lines"],
                    "unresolved": [
                        {
                            "code": "ambiguous_line_assignment" if token["candidate_line_ids"] else "unassigned_line_assignment",
                            "token_source_row": token["source_row"],
                            "candidate_line_ids": token["candidate_line_ids"],
                        }
                        for token in page_record["tokens"]
                        if token["physical_line_id"] is None
                    ],
                    "row_errors": page_record["error_details"],
                    "measurements": page_record["measurements"],
                    "token_count": len(page_record["tokens"]),
                    "line_count": len(page_record["physical_lines"]),
                    "ambiguous_count": sum(bool(token["candidate_line_ids"]) for token in page_record["tokens"] if token["physical_line_id"] is None),
                    "unassigned_count": sum(not token["candidate_line_ids"] for token in page_record["tokens"] if token["physical_line_id"] is None),
                }
                captures[str(page_number)] = {
                    "page": page_number,
                    "fixture_id": fixture_id,
                    "side": page_record["side"],
                    "raster_dimensions": [page_record["width_px"], page_record["height_px"]],
                    "raster_sha256": sha256_file(image_path),
                    "tsv_sha256": sha256_bytes(tsv.encode("utf-8")),
                    "geometry": geom,
                    "line_texts": line_texts(geom),
                }
    return captures


def capture_spineless() -> dict[str, Any]:
    captures: dict[str, Any] = {}
    for page_number in PAGES:
        source_path = SPINELESS_DIR / f"pg.{page_number}.jpg"
        with Image.open(source_path) as source_image:
            source = source_image.convert("RGB")
            crop_box = PAGE_BOXES[page_number]
            cropped, _, _ = prepare_spineless_raster(source, crop_box, 0)
        regions = [(350, 900), (900, 1500), (1500, 2200)]
        regional_angles = [row_correction_angle(cropped, y0, y1) for y0, y1 in regions]
        angle = median(regional_angles)
        cropped, deskewed, final_image = prepare_spineless_raster(source, crop_box, angle)
        tsv = pytesseract.image_to_data(final_image, lang="eng", config="--psm 6", output_type=Output.STRING)
        OCR_INVOCATIONS["spineless"] += 1
        geom = geometry_record(tsv, final_image.size)
        page_bytes = final_image.tobytes()
        fixture_id, side = PAGE_FIXTURE[page_number]
        captures[str(page_number)] = {
            "page": page_number,
            "fixture_id": fixture_id,
            "side": side,
            "source_filename": source_path.name,
            "source_dimensions": list(source.size),
            "source_sha256": sha256_file(source_path),
            "crop_box": list(crop_box),
            "crop_dimensions": list(cropped.size),
            "angle_correction_degrees": angle,
            "angle_support": {
                "method": "dark-pixel horizontal-projection energy over 0.02-degree grid",
                "roi_x_px": [100, 1350],
                "regions_y_px": [list(region) for region in regions],
                "regional_corrections_degrees": regional_angles,
                "uncertainty_degrees": (max(regional_angles) - min(regional_angles)) / 2 + 0.02,
                "agreement_range_degrees": max(regional_angles) - min(regional_angles),
                "residual_regional_corrections_degrees": [
                    row_correction_angle(final_image, round(y0 * OUTPUT_SCALE), round(y1 * OUTPUT_SCALE))
                    for y0, y1 in regions
                ],
            },
            "transform": {
                "method": "Pillow Image.rotate",
                "angle_degrees": angle,
                "resampling": "bicubic",
                "expand": True,
                "background_rgb": [255, 255, 255],
                "post_rotation_dimensions": list(deskewed.size),
                "downsample": "Pillow LANCZOS",
                "output_dpi_equivalent": 144,
                "dimension_rounding": "nearest integer, half upward, from 144/300 scale",
                "final_dimensions": list(final_image.size),
                "final_rgb_sha256": sha256_bytes(page_bytes),
            },
            "tsv_sha256": sha256_bytes(tsv.encode("utf-8")),
            "geometry": geom,
            "line_texts": line_texts(geom),
        }
    return captures


def main() -> None:
    catalog_ids = [item.fixture_id for item in FixtureCatalog.load(ROOT)]
    bound = capture_bound()
    spineless = capture_spineless()
    output = {
        "schema": "spineless-acquisition-ablation-v1",
        "engine": {
            "tesseract_version": str(pytesseract.get_tesseract_version()).strip(),
            "language": "eng",
            "config": "--psm 6",
            "production_config": str(CONFIG_PATH.relative_to(ROOT)),
            "fixture_catalog_ids": catalog_ids,
        },
        "ocr_invocations": dict(OCR_INVOCATIONS),
        "bound": bound,
        "spineless": spineless,
    }
    OUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
