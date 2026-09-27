from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def test_manifest_covers_all_canonical_page_sides_and_exact_mapping():
    manifest = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))
    records = manifest["records"]
    assert manifest["reference_dpi"] == 300
    assert manifest["production_dpi"] == 144
    assert len(records) == 12
    assert {(r["fixture_id"], r["side"]) for r in records} == {
        (fixture, side)
        for fixture in (
            "relativity_pdf10_pp26-27",
            "relativity_pdf17_pp40-41",
            "relativity_pdf23_pp52-53",
            "stella_maris_pdf03_session-I",
            "stella_maris_pdf06_dense-dialogue",
            "stella_maris_pdf18_session-II_p35",
        )
        for side in ("left", "right")
    }
    for record in records:
        image_path = HERE / record["relative_path"]
        assert hashlib.sha256(image_path.read_bytes()).hexdigest() == record["sha256"]
        with Image.open(image_path) as image:
            assert image.mode == "RGB"
            assert [image.width, image.height] == [1650, 2550]
            assert [image.width * 12 // 25, image.height * 12 // 25] == [792, 1224]
        assert record["reference_split_boundary_px"] * 12 // 25 == record["production_split_boundary_px"]
        assert record["source_pdf_sha256"]
