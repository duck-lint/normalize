"""Generate canonical 300-DPI page-side PNGs from fixture PDFs.

This reuses the production PDF renderer and preprocessing transforms, changing
only the render scale so reference crops retain more scan detail. The split is
scaled from the configured production raster coordinate system exactly.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pymupdf
from PIL import Image

from normalize.fixtures import FixtureCatalog
from normalize.rendering import _preprocess_image, load_preprocessing_config

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = Path(__file__).resolve().parent / "inputs"
CONFIG_PATH = ROOT / "fixtures" / "preprocessing.json"
REFERENCE_DPI = 300


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate() -> dict:
    config = load_preprocessing_config(CONFIG_PATH)
    catalog = FixtureCatalog.load(ROOT)
    records = []
    for metadata in catalog:
        profile = config.profiles[metadata.fixture_id]
        if profile.result_kind != "spread" or profile.split_boundary is None:
            raise ValueError(f"{metadata.fixture_id}: expected a configured spread profile")
        if config.dpi <= 0:
            raise ValueError("production DPI must be positive")
        scaled_split_exact = profile.split_boundary * REFERENCE_DPI / config.dpi
        if not scaled_split_exact.is_integer():
            raise ValueError(f"{metadata.fixture_id}: split does not map to an integer at {REFERENCE_DPI} DPI")
        split_reference = int(scaled_split_exact)

        with pymupdf.open(metadata.source_pdf) as document:
            page_index = metadata.fixture_pdf_page_index_1_based - 1
            if page_index < 0 or page_index >= document.page_count:
                raise ValueError(f"{metadata.fixture_id}: fixture page index is outside the source PDF")
            page = document.load_page(page_index)
            spread_dimensions_pt = [float(page.rect.width), float(page.rect.height)]
            pdf_rotation = int(page.rotation)
            pixmap = page.get_pixmap(
                matrix=pymupdf.Matrix(REFERENCE_DPI / 72.0, REFERENCE_DPI / 72.0),
                alpha=False,
                annots=False,
            )
            rendered = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)

        # Keep this path in lockstep with production: PDF page rendering first,
        # then configured rotation/crop/deskew, then the configured spread split.
        transformed, transform_ledger = _preprocess_image(rendered, profile)
        if split_reference <= 0 or split_reference >= transformed.width:
            raise ValueError(f"{metadata.fixture_id}: scaled split lies outside rendered spread")
        if transformed.height * config.dpi % REFERENCE_DPI:
            raise ValueError(f"{metadata.fixture_id}: spread height has a non-integral production mapping")
        side_images = {
            "left": transformed.crop((0, 0, split_reference, transformed.height)),
            "right": transformed.crop((split_reference, 0, transformed.width, transformed.height)),
        }
        if split_reference * config.dpi / REFERENCE_DPI != profile.split_boundary:
            raise ValueError(f"{metadata.fixture_id}: reference split does not map to production split")

        spread_dimensions_px = [transformed.width, transformed.height]
        source_hash = sha256(metadata.source_pdf)
        for side in profile.output_order:
            image = side_images[side]
            filename = f"{metadata.fixture_id}.{side}.png"
            output_path = OUTPUT_DIR / filename
            image.save(output_path, format="PNG", optimize=False)
            records.append(
                {
                    "fixture_id": metadata.fixture_id,
                    "source_pdf": str(metadata.source_pdf.relative_to(ROOT)),
                    "source_pdf_sha256": source_hash,
                    "fixture_page_index_1_based": metadata.fixture_pdf_page_index_1_based,
                    "source_page_index_1_based": metadata.source_pdf_page_index_1_based,
                    "pdf_page_rotation_degrees": pdf_rotation,
                    "reference_dpi": REFERENCE_DPI,
                    "production_dpi": config.dpi,
                    "spread_dimensions_pt": spread_dimensions_pt,
                    "spread_dimensions_px": spread_dimensions_px,
                    "production_split_boundary_px": profile.split_boundary,
                    "reference_split_boundary_px": split_reference,
                    "side": side,
                    "side_dimensions_px": [image.width, image.height],
                    "reference_to_production_scale": {
                        "numerator": config.dpi,
                        "denominator": REFERENCE_DPI,
                        "coordinate_rule": "production_px = reference_px * numerator / denominator",
                    },
                    "configured_rotation_degrees_clockwise": profile.rotation_degrees,
                    "configured_crop_px": list(profile.crop) if profile.crop is not None else None,
                    "configured_deskew_degrees_clockwise": profile.deskew_degrees,
                    "preprocessing_transform_ledger": transform_ledger,
                    "relative_path": f"inputs/{filename}",
                    "sha256": sha256(output_path),
                }
            )
    manifest = {
        "schema": "canonical-page-crop-raster-references-v1",
        "purpose": "Manual rectangular crop references; not production preprocessing outputs",
        "reference_dpi": REFERENCE_DPI,
        "production_dpi": config.dpi,
        "mapping": "Reference rasters are rendered from the original fixture PDFs at 300 DPI. Pixel coordinates map to production 144-DPI page-side coordinates by the exact rational scale 12/25. The configured 144-DPI split boundary 792 maps to reference split x=1650.",
        "render_semantics": "Original fixture PDF page selected by fixture_pdf_page_index_1_based; PyMuPDF render at recorded DPI with alpha=False and annots=False; production configured rotation/crop/deskew applied by normalize.rendering._preprocess_image; configured split scaled proportionally from production DPI; sides emitted in configured output_order.",
        "records": records,
    }
    manifest_path = Path(__file__).resolve().parent / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    result = generate()
    print(f"wrote {len(result['records'])} canonical page-side references")
