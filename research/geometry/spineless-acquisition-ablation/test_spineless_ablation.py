from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


MODULE_PATH = Path(__file__).with_name("run_ablation.py")
SPEC = importlib.util.spec_from_file_location("spineless_ablation", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
ablation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ablation)


def synthetic_page() -> Image.Image:
    image = Image.new("RGB", (1500, 2340), "white")
    draw = ImageDraw.Draw(image)
    for y in (450, 550, 650, 750, 850, 1050, 1150, 1250, 1350, 1550, 1650, 1750):
        draw.line((180, y, 1320, y), fill="black", width=4)
    return image


def test_flat_page_zero_rotation_is_exact_and_one_page_input_stays_one_page():
    source = synthetic_page()
    cropped, deskewed, final = ablation.prepare_spineless_raster(
        source, (0, 0, 1500, 2340), 0.0
    )
    assert cropped.size == (1500, 2340)
    assert deskewed.tobytes() == cropped.tobytes()
    assert isinstance(final, Image.Image)  # one source page remains one page; no spread split
    assert final.size == (720, 1123)


def test_crop_then_whole_page_deskew_restores_rows_without_clipping():
    upright = synthetic_page()
    tilted = upright.rotate(-0.7, resample=Image.Resampling.BICUBIC, expand=True, fillcolor="white")
    # A crop is established from page pixels before estimating/applying angle.
    # Keep a generous margin to retain the full rotated synthetic sheet.
    crop_box = (0, 0, tilted.width, tilted.height)
    correction = ablation.row_correction_angle(tilted, 350, 2200)
    assert abs(correction - 0.7) <= 0.08
    cropped, deskewed, final = ablation.prepare_spineless_raster(tilted, crop_box, correction)
    assert deskewed.width >= cropped.width
    assert deskewed.height >= cropped.height
    assert final.size == (
        ablation.round_half_up(deskewed.width * ablation.OUTPUT_SCALE),
        ablation.round_half_up(deskewed.height * ablation.OUTPUT_SCALE),
    )
    residual = ablation.row_correction_angle(deskewed, 350, min(2200, deskewed.height))
    assert abs(residual) <= 0.08
    # All original dark rows remain represented after expanded rotation.
    pixels = np.asarray(deskewed.convert("L"))
    assert int((pixels < 80).sum()) > 30_000
