"""Compare Tesseract's raw page-27 observations across fixed pixel contexts.

This is a research-only diagnostic. Every crop is a direct, unscaled view of
the exact raster consumed by the prior spineless study. The first OCR call is
the full-page control; the script refuses to produce crop observations unless
the saved raster and TSV hashes both match.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
from typing import Any

import pytesseract
from PIL import Image
from pytesseract import Output

ROOT = Path(__file__).resolve().parents[3]
PRIOR_DIR = ROOT / "research/geometry/spineless-acquisition-ablation"
PRIOR_RESULTS = PRIOR_DIR / "results.json"
SOURCE = ROOT / "fixtures/einstein/spineless/pg.27.jpg"
OUT_DIR = Path(__file__).resolve().parent
OCR_LANGUAGE = "eng"
OCR_CONFIG = "--psm 6"

# Pixel projection from the unchanged 739x1136 page raster establishes these
# ink rows. Target ink is y=671..685; the adjacent rows are y=643..657 and
# y=699..719. The 10 px framing margin is fixed before any crop OCR is run.
TARGET_ROI = (110, 671, 650, 686)
CONTROL_ROI = (110, 699, 650, 720)
CONTROL_CONTEXT_SHIFT_Y = 31
TEXT_COLUMN = (105, 575, 665, 755)
CROPS: dict[str, tuple[int, int, int, int]] = {
    "A_full_page": (0, 0, 739, 1136),
    "B_text_column_broad_vertical": TEXT_COLUMN,
    "C_target_plus_adjacent_rows": (105, 632, 665, 731),
    "D_target_row_with_vertical_padding": (105, 660, 665, 696),
    "E_tight_target_neighborhood": (110, 660, 650, 696),
    # One diagnostic only: retain B's vertical range while restoring page
    # width, to test horizontal context independently of vertical context.
    "Bx_full_width_broad_vertical": (0, 575, 739, 755),
    "Bx_left_margin_broad_vertical": (0, 575, 665, 755),
    "Bx_left_edge_trimmed_broad_vertical": (70, 575, 665, 755),
    "Bx_right_margin_broad_vertical": (105, 575, 739, 755),
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_prior_page() -> dict[str, Any]:
    return json.loads(PRIOR_RESULTS.read_text())["spineless"]["27"]


def reconstruct_source_raster() -> tuple[Image.Image, dict[str, Any]]:
    """Rebuild the exact prior crop/deskew/downsample using its saved values."""
    prior = load_prior_page()
    if sha256(SOURCE.read_bytes()) != prior["source_sha256"]:
        raise RuntimeError("STOP: spineless source JPG hash differs from prior study")

    script_path = PRIOR_DIR / "run_ablation.py"
    spec = importlib.util.spec_from_file_location("prior_spineless_ablation", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load prior raster preparation implementation")
    prior_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prior_module)
    with Image.open(SOURCE) as source:
        _, _, raster = prior_module.prepare_spineless_raster(
            source,
            tuple(prior["crop_box"]),
            float(prior["angle_correction_degrees"]),
        )
    raster_hash = sha256(raster.tobytes())
    if list(raster.size) != prior["transform"]["final_dimensions"]:
        raise RuntimeError("STOP: reconstructed page dimensions differ from prior")
    if raster_hash != prior["transform"]["final_rgb_sha256"]:
        raise RuntimeError("STOP: reconstructed page raster hash differs from prior")
    return raster, prior


def ocr_tsv(image: Image.Image) -> str:
    """Use the production study's exact OCR API arguments and config."""
    return pytesseract.image_to_data(
        image,
        lang=OCR_LANGUAGE,
        config=OCR_CONFIG,
        output_type=Output.STRING,
    )


def parse_tsv(tsv: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source_row, raw in enumerate(csv.DictReader(io.StringIO(tsv), delimiter="\t"), start=1):
        if not raw:
            continue
        record: dict[str, Any] = {"source_row": source_row}
        for name in (
            "level", "page_num", "block_num", "par_num", "line_num", "word_num",
            "left", "top", "width", "height",
        ):
            record[name] = int(raw[name])
        record["confidence"] = float(raw["conf"])
        record["text"] = raw["text"]
        record["x1"] = record["left"] + record["width"]
        record["y1"] = record["top"] + record["height"]
        rows.append(record)
    return rows


def intersects(box: tuple[int, int, int, int], roi: tuple[int, int, int, int]) -> bool:
    x0, y0, x1, y1 = box
    rx0, ry0, rx1, ry1 = roi
    return max(x0, rx0) < min(x1, rx1) and max(y0, ry0) < min(y1, ry1)


def mapped_records(
    tsv: str,
    crop_box: tuple[int, int, int, int],
    roi: tuple[int, int, int, int],
) -> list[dict[str, Any]]:
    """Return raw word rows whose mapped boxes intersect the fixed page ROI."""
    crop_x, crop_y = crop_box[:2]
    output = []
    for row in parse_tsv(tsv):
        if row["level"] != 5 or row["width"] <= 0 or row["height"] <= 0:
            continue
        local_box = (row["left"], row["top"], row["x1"], row["y1"])
        page_box = (
            row["left"] + crop_x,
            row["top"] + crop_y,
            row["x1"] + crop_x,
            row["y1"] + crop_y,
        )
        if intersects(page_box, roi):
            output.append({
                "source_tsv_row": row["source_row"],
                "hierarchy_ids": [row[name] for name in ("page_num", "block_num", "par_num", "line_num", "word_num")],
                "text_locator": row["text"],
                "confidence": row["confidence"],
                "crop_local_box_xyxy": list(local_box),
                "page_box_xyxy": list(page_box),
                "intersects_fixed_roi": True,
            })
    return output


def mapped_line_hierarchy(tsv: str, crop_box: tuple[int, int, int, int], roi: tuple[int, int, int, int]) -> list[dict[str, Any]]:
    """Retain line-level TSV parents that cover the physical target ink."""
    crop_x, crop_y = crop_box[:2]
    output = []
    for row in parse_tsv(tsv):
        if row["level"] != 4:
            continue
        page_box = (
            row["left"] + crop_x,
            row["top"] + crop_y,
            row["x1"] + crop_x,
            row["y1"] + crop_y,
        )
        if intersects(page_box, roi):
            output.append({
                "source_tsv_row": row["source_row"],
                "hierarchy_ids": [row[name] for name in ("page_num", "block_num", "par_num", "line_num", "word_num")],
                "page_box_xyxy": list(page_box),
                "confidence": row["confidence"],
                "text": row["text"],
            })
    return output


def classify_target(records: list[dict[str, Any]], target_roi: tuple[int, int, int, int]) -> str:
    """Geometry-first label, followed by a report-level visual adjudication."""
    if not records:
        return "missing_observation"
    y0, y1 = target_roi[1], target_roi[3]
    target_records = [r for r in records if r["page_box_xyxy"][1] < y1 and r["page_box_xyxy"][3] > y0]
    if not target_records:
        return "missing_observation"
    heights = [r["page_box_xyxy"][3] - r["page_box_xyxy"][1] for r in target_records]
    largest_height = max(heights)
    if largest_height >= 35:
        return "multirow_merged_observation"
    # Tiny boxes (for example 3x2 px fragments labeled as whole words) are
    # counted in the raw ledger but do not qualify as usable word geometry.
    usable = [
        r for r in target_records
        if r["page_box_xyxy"][2] - r["page_box_xyxy"][0] >= 8
        and r["page_box_xyxy"][3] - r["page_box_xyxy"][1] >= 8
    ]
    if len(usable) >= 6:
        return "normal_per_word_observation"
    if usable:
        return "partial_per_word_observation"
    if target_records:
        return "other_malformed_observation"
    return "partial_per_word_observation"


def validate_crop_source(raster: Image.Image, crop_box: tuple[int, int, int, int]) -> Image.Image:
    """Use Pillow's direct crop only; no pixel or dimension transformation."""
    crop = raster.crop(crop_box)
    expected = raster.crop(crop_box)
    if crop.size != (crop_box[2] - crop_box[0], crop_box[3] - crop_box[1]):
        raise AssertionError("crop dimensions do not match crop rectangle")
    if crop.tobytes() != expected.tobytes():
        raise AssertionError("crop pixels differ from the corresponding source view")
    return crop


def run_study() -> dict[str, Any]:
    raster, prior = reconstruct_source_raster()
    version = str(pytesseract.get_tesseract_version())
    if version != "5.3.4":
        raise RuntimeError(f"STOP: expected Tesseract 5.3.4, found {version}")

    # Full-page control is deliberately first. No experimental crops run unless
    # its exact raw TSV hash and the malformed source records reproduce.
    control_tsv = ocr_tsv(raster)
    control_hash = sha256(control_tsv.encode("utf-8"))
    if control_hash != prior["tsv_sha256"]:
        raise RuntimeError("STOP: full-page TSV hash differs from prior study")
    control_records = parse_tsv(control_tsv)
    expected_malformed = {
        "See": (190, [7, 640, 624, 696], 14.663147),
        "ae": (191, [625, 671, 639, 686], 33.175888),
    }
    for text, (source_row, box, confidence) in expected_malformed.items():
        matching = [r for r in control_records if r["level"] == 5 and r["text"] == text]
        if not matching:
            raise RuntimeError(f"STOP: full-page malformed word {text!r} absent")
        record = matching[0]
        actual_box = [record["left"], record["top"], record["x1"], record["y1"]]
        if record["source_row"] != source_row or actual_box != box or abs(record["confidence"] - confidence) > 1e-5:
            raise RuntimeError(f"STOP: malformed word {text!r} differs from prior observation")

    # The target and highlighted comparison row are located by physical pixels.
    # All crop bounds are fixed constants above and are not adapted to OCR.
    records_by_crop: dict[str, Any] = {}
    crop_manifest: dict[str, Any] = {}
    for crop_id, crop_box in CROPS.items():
        target_crop = validate_crop_source(raster, crop_box)
        control_crop_box = crop_box if crop_id == "A_full_page" else (
            crop_box[0], crop_box[1] + CONTROL_CONTEXT_SHIFT_Y,
            crop_box[2], crop_box[3] + CONTROL_CONTEXT_SHIFT_Y,
        )
        control_crop = validate_crop_source(raster, control_crop_box)
        target_tsv_runs: list[str] = []
        control_tsv_runs: list[str] = []
        for repeat in range(2):
            target_tsv_runs.append(ocr_tsv(target_crop))
            control_tsv_runs.append(ocr_tsv(control_crop))
        target_runs = [mapped_records(tsv, crop_box, TARGET_ROI) for tsv in target_tsv_runs]
        control_runs = [mapped_records(tsv, control_crop_box, CONTROL_ROI) for tsv in control_tsv_runs]
        target_deterministic = target_tsv_runs[0] == target_tsv_runs[1]
        control_deterministic = control_tsv_runs[0] == control_tsv_runs[1]
        target_pixel_hash = sha256(target_crop.tobytes())
        control_pixel_hash = sha256(control_crop.tobytes())
        crop_manifest[crop_id] = {
            "target_bounds_xyxy_page": list(crop_box),
            "target_dimensions": list(target_crop.size),
            "target_source_pixel_sha256": target_pixel_hash,
            "control_bounds_xyxy_page": list(control_crop_box),
            "control_dimensions": list(control_crop.size),
            "control_source_pixel_sha256": control_pixel_hash,
            "resized": False,
            "redeskewed": False,
        }
        records_by_crop[crop_id] = {
            "target_crop_box_xyxy_page": list(crop_box),
            "target_crop_dimensions": list(target_crop.size),
            "target_source_pixel_sha256": target_pixel_hash,
            "resized": False,
            "redeskewed": False,
            "target_outcome": classify_target(target_runs[0], TARGET_ROI),
            "target_records_first_run": target_runs[0],
            "target_records_repeat_run": target_runs[1],
            "target_line_hierarchy_first_run": mapped_line_hierarchy(target_tsv_runs[0], crop_box, TARGET_ROI),
            "target_record_identity_stable": target_runs[0] == target_runs[1],
            "target_raw_tsv_sha256_repeats": [sha256(tsv.encode("utf-8")) for tsv in target_tsv_runs],
            "target_raw_tsv_deterministic": target_deterministic,
            "control_crop_box_xyxy_page": list(control_crop_box),
            "control_crop_dimensions": list(control_crop.size),
            "control_source_pixel_sha256": control_pixel_hash,
            "highlighted_control_outcome": classify_target(control_runs[0], CONTROL_ROI),
            "highlighted_control_records_first_run": control_runs[0],
            "highlighted_control_records_repeat_run": control_runs[1],
            "control_record_identity_stable": control_runs[0] == control_runs[1],
            "control_raw_tsv_sha256_repeats": [sha256(tsv.encode("utf-8")) for tsv in control_tsv_runs],
            "control_raw_tsv_deterministic": control_deterministic,
            "raw_tsv_deterministic": target_deterministic and control_deterministic,
        }

    if not all(item["raw_tsv_deterministic"] for item in records_by_crop.values()):
        raise RuntimeError("identical crop OCR produced non-identical raw TSV")

    result = {
        "source": {
            "filename": SOURCE.name,
            "source_sha256": prior["source_sha256"],
            "page_raster_dimensions": list(raster.size),
            "page_raster_rgb_sha256": prior["transform"]["final_rgb_sha256"],
            "page_raster_rebuilt_exactly": True,
            "preprocessing_reused": {
                "crop_box_source_300dpi": prior["crop_box"],
                "deskew_degrees": prior["angle_correction_degrees"],
                "prior_method": prior["transform"],
            },
        },
        "ocr": {
            "tesseract_version": version,
            "language": OCR_LANGUAGE,
            "config": OCR_CONFIG,
            "api": "pytesseract.image_to_data(output_type=Output.STRING)",
            "full_page_tsv_sha256": control_hash,
            "full_page_tsv_matches_prior": True,
            "production_geometry_run": False,
        },
        "fixed_pixel_regions": {
            "target_text_locator": "affords an insufficient foundation for the physical",
            "target_ink_y_span_px": [671, 685],
            "target_roi_xyxy": list(TARGET_ROI),
            "row_above_ink_y_span_px": [643, 657],
            "row_below_ink_y_span_px": [699, 719],
            "control_text_locator": "description of all natural phenomena",
            "highlighted_control_ink_y_span_px": [699, 719],
            "highlighting": "cyan marker visibly crosses glyph rows for target and control",
            "text_column_crop_bounds": list(TEXT_COLUMN),
            "bounds_established_from_pixels_before_crop_ocr": True,
        },
        "full_page_control_target_records": mapped_records(control_tsv, CROPS["A_full_page"], TARGET_ROI),
        "full_page_target_line_hierarchy": mapped_line_hierarchy(control_tsv, CROPS["A_full_page"], TARGET_ROI),
        "full_page_control_control_records": mapped_records(control_tsv, CROPS["A_full_page"], CONTROL_ROI),
        "crop_manifest": crop_manifest,
        "crop_runs": records_by_crop,
        "raw_tsv_artifacts": {"full_page_control_tsv_sha256": control_hash},
    }
    return result


def main() -> None:
    result = run_study()
    path = OUT_DIR / "raw-tsv-comparison.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    manifest = {
        "source_raster_dimensions": result["source"]["page_raster_dimensions"],
        "source_raster_sha256": result["source"]["page_raster_rgb_sha256"],
        "fixed_pixel_regions": result["fixed_pixel_regions"],
        "crops": result["crop_manifest"],
    }
    (OUT_DIR / "crop-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    summary = {
        "decision": "full_page_context_segmentation_failure",
        "page": 27,
        "source_raster_dimensions": result["source"]["page_raster_dimensions"],
        "source_raster_sha256": result["source"]["page_raster_rgb_sha256"],
        "full_page_tsv_sha256": result["ocr"]["full_page_tsv_sha256"],
        "full_page_control_matches_prior": result["ocr"]["full_page_tsv_matches_prior"],
        "first_crop_away_from_multirow_merge": "B_text_column_broad_vertical",
        "first_crop_with_normal_per_word_observation": "C_target_plus_adjacent_rows",
        "crop_outcomes": {key: value["target_outcome"] for key, value in result["crop_runs"].items()},
        "control_outcomes": {key: value["highlighted_control_outcome"] for key, value in result["crop_runs"].items()},
        "all_repeated_raw_tsv_deterministic": all(value["raw_tsv_deterministic"] for value in result["crop_runs"].values()),
    }
    (OUT_DIR / "results.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({
        "full_page_tsv_sha256": result["ocr"]["full_page_tsv_sha256"],
        "crop_outcomes": summary["crop_outcomes"],
        "control_outcomes": summary["control_outcomes"],
        "deterministic": all(value["raw_tsv_deterministic"] for value in result["crop_runs"].values()),
    }, indent=2))


if __name__ == "__main__":
    main()
