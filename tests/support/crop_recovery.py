"""Find an exact rectangular pixel subset of a canonical reference PNG."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from PIL import Image


class CropRecoveryError(ValueError):
    """The supplied crop could not be recovered exactly from the reference."""


class AmbiguousCropError(CropRecoveryError):
    """More than one exact rectangular occurrence exists in the reference."""


def _read_rgb_bytes(path: Path) -> tuple[int, int, bytes]:
    with Image.open(path) as source:
        source.load()
        if source.mode != "RGB":
            raise CropRecoveryError(f"{path}: expected an RGB PNG; found mode {source.mode}")
        if source.format != "PNG":
            raise CropRecoveryError(f"{path}: expected PNG input")
        return source.width, source.height, source.tobytes()


def _count_occurrences(row: bytes, needle: bytes) -> int:
    count = 0
    offset = 0
    while True:
        offset = row.find(needle, offset)
        if offset < 0:
            return count
        count += 1
        offset += 1


def find_exact_subcrop_bounds(reference_path: Path, crop_path: Path) -> list[int]:
    """Return unique exact bounds `[x0, y0, x1, y1]` in reference pixels.

    Pixel equality is byte-for-byte RGB equality. A crop that has been resized,
    rotated, color-adjusted, or otherwise changed has no match and is rejected.
    If identical pixels occur at multiple locations, ambiguity is explicit.
    """
    ref_width, ref_height, ref_bytes = _read_rgb_bytes(Path(reference_path))
    crop_width, crop_height, crop_bytes = _read_rgb_bytes(Path(crop_path))
    if crop_width > ref_width or crop_height > ref_height:
        raise CropRecoveryError("No exact rectangular pixel subset found; crop may have been transformed rather than merely cropped.")

    channels = 3
    ref_stride = ref_width * channels
    crop_stride = crop_width * channels
    ref_rows = [ref_bytes[y * ref_stride : (y + 1) * ref_stride] for y in range(ref_height)]
    crop_rows = [crop_bytes[y * crop_stride : (y + 1) * crop_stride] for y in range(crop_height)]

    # Choose the least-repeated full crop row as an anchor. This keeps the exact
    # search tractable on page-sized rasters with large uniform margins.
    anchor_indices = sorted({
        round(index * (crop_height - 1) / 31)
        for index in range(32)
    })
    candidates: list[tuple[int, int, bytes]] = []
    for crop_y in anchor_indices:
        crop_row = crop_rows[crop_y]
        occurrences = sum(_count_occurrences(reference_row, crop_row) for reference_row in ref_rows)
        if occurrences == 0:
            raise CropRecoveryError("No exact rectangular pixel subset found; crop may have been transformed rather than merely cropped.")
        candidates.append((occurrences, crop_y, crop_row))
        if occurrences == 1:
            break
    _, anchor_crop_y, anchor = min(candidates, key=lambda item: item[0])

    matches: list[tuple[int, int, int, int]] = []
    for anchor_y, reference_row in enumerate(ref_rows):
        offset = 0
        while True:
            offset = reference_row.find(anchor, offset)
            if offset < 0:
                break
            if offset % channels == 0:
                x0 = offset // channels
                y0 = anchor_y - anchor_crop_y
                if y0 >= 0 and y0 + crop_height <= ref_height and x0 + crop_width <= ref_width:
                    if all(
                        ref_rows[y0 + row_index][x0 * channels : x0 * channels + crop_stride] == crop_row
                        for row_index, crop_row in enumerate(crop_rows)
                    ):
                        bounds = (x0, y0, x0 + crop_width, y0 + crop_height)
                        if bounds not in matches:
                            matches.append(bounds)
                            if len(matches) > 1:
                                raise AmbiguousCropError(f"Multiple exact matches found: {matches[:2]}")
            offset += channels

    if not matches:
        raise CropRecoveryError("No exact rectangular pixel subset found; crop may have been transformed rather than merely cropped.")
    return list(matches[0])


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference_png", type=Path)
    parser.add_argument("cropped_png", type=Path)
    args = parser.parse_args(argv)
    try:
        bounds = find_exact_subcrop_bounds(args.reference_png, args.cropped_png)
    except CropRecoveryError as exc:
        parser.exit(2, f"crop recovery failed: {exc}\n")
    print(bounds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
