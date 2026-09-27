from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from recover_crop import AmbiguousCropError, CropRecoveryError, find_exact_subcrop_bounds


def write_rgb(path: Path, pixels: list[list[tuple[int, int, int]]]) -> None:
    height = len(pixels)
    width = len(pixels[0])
    image = Image.new("RGB", (width, height))
    image.putdata([pixel for row in pixels for pixel in row])
    image.save(path, format="PNG")


def patterned(width: int, height: int) -> list[list[tuple[int, int, int]]]:
    return [
        [((x * 31 + y * 7) % 256, (x * 13 + y * 19) % 256, (x * 3 + y * 47) % 256) for x in range(width)]
        for y in range(height)
    ]


def crop_pixels(pixels, x0: int, y0: int, x1: int, y1: int):
    return [row[x0:x1] for row in pixels[y0:y1]]


@pytest.fixture
def page_files(tmp_path):
    reference, crop = tmp_path / "reference.png", tmp_path / "crop.png"
    pixels = patterned(9, 8)
    write_rgb(reference, pixels)
    return reference, crop, pixels


def test_recovers_exact_subcrop(page_files):
    reference, crop, pixels = page_files
    write_rgb(crop, crop_pixels(pixels, 2, 1, 7, 6))
    assert find_exact_subcrop_bounds(reference, crop) == [2, 1, 7, 6]


@pytest.mark.parametrize(
    ("bounds", "expected"),
    [
        ((0, 2, 4, 6), [0, 2, 4, 6]),
        ((5, 2, 9, 6), [5, 2, 9, 6]),
        ((2, 0, 7, 4), [2, 0, 7, 4]),
        ((2, 4, 7, 8), [2, 4, 7, 8]),
    ],
)
def test_recovers_crops_touching_each_boundary(page_files, bounds, expected):
    reference, crop, pixels = page_files
    write_rgb(crop, crop_pixels(pixels, *bounds))
    assert find_exact_subcrop_bounds(reference, crop) == expected


def test_full_image_returns_full_bounds(page_files):
    reference, crop, pixels = page_files
    write_rgb(crop, pixels)
    assert find_exact_subcrop_bounds(reference, crop) == [0, 0, 9, 8]


def test_identical_region_at_multiple_locations_is_ambiguous(tmp_path):
    reference, crop = tmp_path / "reference.png", tmp_path / "crop.png"
    pixels = [[(0, 0, 0)] * 8 for _ in range(4)]
    write_rgb(reference, pixels)
    write_rgb(crop, [[(0, 0, 0)] * 3 for _ in range(2)])
    with pytest.raises(AmbiguousCropError):
        find_exact_subcrop_bounds(reference, crop)


def test_resized_input_is_rejected(page_files):
    reference, crop, pixels = page_files
    source = Image.new("RGB", (4, 4))
    source.putdata([item for row in crop_pixels(pixels, 1, 1, 5, 5) for item in row])
    source.resize((6, 6), Image.Resampling.NEAREST).save(crop, format="PNG")
    with pytest.raises(CropRecoveryError, match="No exact rectangular pixel subset"):
        find_exact_subcrop_bounds(reference, crop)


def test_rotated_input_is_rejected(page_files):
    reference, crop, pixels = page_files
    rotated = Image.new("RGB", (4, 5))
    rotated.putdata([item for row in crop_pixels(pixels, 1, 1, 6, 5) for item in row])
    rotated.transpose(Image.Transpose.ROTATE_90).save(crop, format="PNG")
    with pytest.raises(CropRecoveryError, match="No exact rectangular pixel subset"):
        find_exact_subcrop_bounds(reference, crop)


def test_one_pixel_difference_is_rejected(page_files):
    reference, crop, pixels = page_files
    changed = crop_pixels(pixels, 2, 1, 7, 6)
    row, column = 2, 2
    old = changed[row][column]
    changed[row][column] = ((old[0] + 1) % 256, old[1], old[2])
    write_rgb(crop, changed)
    with pytest.raises(CropRecoveryError, match="No exact rectangular pixel subset"):
        find_exact_subcrop_bounds(reference, crop)
