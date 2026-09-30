#!/usr/bin/env python3
"""Run one fresh production OCR capture per final high-resolution-preprocessed side."""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import pytesseract
from PIL import Image
from pytesseract import Output

from normalize.fixtures import FixtureCatalog
from normalize.geometry import group_physical_lines, parse_tsv_rows
from normalize.rendering import preprocess_fixture

ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "fixtures/preprocessing.json"
FIXTURE_IDS = (
    "relativity_pdf10_pp26-27",
    "relativity_pdf17_pp40-41",
    "relativity_pdf23_pp52-53",
    "stella_maris_pdf03_session-I",
    "stella_maris_pdf06_dense-dialogue",
    "stella_maris_pdf18_session-II_p35",
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def inspect_page(fixture_id: str, page: dict, image_path: Path) -> dict:
    with Image.open(image_path) as image:
        image = image.convert("RGB")
        width, height = image.size
        tsv = pytesseract.image_to_data(image, lang="eng", config="--psm 6", output_type=Output.STRING)
    tokens, parse_errors = parse_tsv_rows(tsv, width, height)
    lines, unresolved, measurements = group_physical_lines(tokens)
    memberships = {token.source_row: [] for token in tokens}
    for line in lines:
        for token_id in line["token_ids"]:
            memberships[int(token_id.removeprefix("token-"))].append(line["line_id"])
    for item in unresolved:
        memberships[item["token_source_row"]] = item["candidate_line_ids"]
    return {
        "fixture_id": fixture_id,
        "side": page["side"],
        "dimensions_px": [width, height],
        "raster_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
        "tsv_sha256": sha256_bytes(tsv.encode("utf-8")),
        "token_count": len(tokens),
        "tokens": [
            {
                "source_row": token.source_row,
                "text": token.text,
                "confidence": token.confidence,
                "ids": [token.page_num, token.block_num, token.par_num, token.line_num, token.word_num],
                "box": [token.x, token.y, token.x1, token.y1],
                "membership": memberships[token.source_row],
            }
            for token in tokens
        ],
        "physical_lines": lines,
        "line_count": len(lines),
        "ambiguous": sum(len(ids) > 1 for ids in memberships.values()),
        "unassigned": sum(not ids for ids in memberships.values()),
        "selected_slope": measurements["baseline_slope_px_per_px"],
        "vertical_tolerance": measurements["tolerance_px"],
        "horizontal_gap_limit": measurements["horizontal_gap_limit_px"],
        "parse_errors": parse_errors,
        "blank": page["blank"],
        "preprocessing": page,
    }


def main() -> None:
    catalog = FixtureCatalog.load(ROOT)
    pages = []
    variants = []
    tesseract_version = str(pytesseract.get_tesseract_version()).strip()
    with tempfile.TemporaryDirectory(prefix="normalize-high-resolution-rotation-") as temp:
        temp_root = Path(temp)
        for fixture_id in FIXTURE_IDS:
            out = temp_root / fixture_id
            metadata = catalog.get(fixture_id)
            preprocessing = preprocess_fixture(metadata, CONFIG, out)
            if preprocessing["status"] != "success":
                raise RuntimeError(f"preprocessing failed: {fixture_id}: {preprocessing}")
            for page in preprocessing["pages"]:
                capture = inspect_page(fixture_id, page, out / page["output_path"])
                pages.append(capture)
        # Diagnostic angle perturbations change only the configured angle and
        # rerun preprocessing/OCR on the same 300-DPI page-side source.
        base_record = json.loads(CONFIG.read_text(encoding="utf-8"))
        fixture_id = "relativity_pdf10_pp26-27"
        for angle in (-1.7, -1.9, -2.1):
            record = json.loads(json.dumps(base_record))
            record["profiles"][fixture_id]["page_rotations"]["right"] = angle
            variant_config = temp_root / f"r10r-{angle}.json"
            variant_config.write_text(json.dumps(record), encoding="utf-8")
            out = temp_root / f"r10r-{angle}"
            preprocessing = preprocess_fixture(catalog.get(fixture_id), variant_config, out)
            if preprocessing["status"] != "success":
                raise RuntimeError(f"variant preprocessing failed at {angle}: {preprocessing}")
            page = next(item for item in preprocessing["pages"] if item["side"] == "right")
            capture = inspect_page(fixture_id, page, out / page["output_path"])
            capture["variant_angle_degrees"] = angle
            variants.append(capture)
    result = {
        "schema": "high-resolution-page-side-rotation-results-v1",
        "production_head_before_implementation": "473e639b6fe335ffb527d2338234d38e311189ba",
        "tesseract_version": tesseract_version,
        "ocr_config": {"language": "eng", "psm": 6, "output": "TSV"},
        "ocr_calls": len(pages) + len(variants),
        "pages": pages,
        "relativity10_right_angle_variants": variants,
    }
    destination = ROOT / "research/geometry/high-resolution-page-rotation/results.json"
    destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"OCR calls: {result['ocr_calls']}; wrote {destination}")


if __name__ == "__main__":
    main()
