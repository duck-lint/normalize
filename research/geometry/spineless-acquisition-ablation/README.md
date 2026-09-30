# Spineless acquisition A/B study

This research compares the current bound Relativity fixture path with six local
JPG scans of the same printed pages. The JPGs are read directly; they are not
wrapped in a PDF and no production source adapter is changed.

The bound control uses `preprocess_fixture` and `run_geometry` from the current
production tree. A small wrapper captures the TSV returned by the normal OCR
call, so each bound side is OCRed once. The spineless path crops one whole
sheet, estimates one rigid correction from pixel rows, deskews the page, and
reduces the 300-DPI scan to a 144-DPI-equivalent raster before calling
Tesseract (`eng`, `--psm 6`) and the production `parse_tsv_rows` and
`group_physical_lines` functions. No spread split, line-specific transform,
slope change, or grouping change is used.

The physical-page crop rectangles are recorded in `results.json`. They were
set from the observed aged-paper/scanner-bed color boundary, with enough right
and bottom margin to retain the furthest observed sheet edge. All inputs have
the same sheet placement, so one bounding rectangle is used. The top and left
sheet edges meet the image boundaries; the crop retains the entire available
image on those edges. Crop bounds are not based on OCR.

Deskew angles are the median of three independent vertical regions. Each
regional angle maximizes squared horizontal projections of dark pixels over a
fixed image ROI and a `0.02°` grid from `-1.5°` to `+1.5°`. Positive values are
Pillow counter-clockwise corrections. The observed regional agreement and
post-deskew residual estimates are preserved per page. This is a measurement
for these six scans, not a production angle detector.

The final dimensions use nearest-pixel rounding with exact halves upward from
the `144/300` scale; Pillow LANCZOS performs the downsample. Tesseract and
production geometry run on that final raster. Runtime images stay in memory
or under `/tmp`; only JSON, Python, and Markdown are checked in.

Run the capture from the repository root with:

```sh
.venv/bin/python research/geometry/spineless-acquisition-ablation/run_ablation.py
```

Run the synthetic checks with:

```sh
.venv/bin/pytest -q research/geometry/spineless-acquisition-ablation/test_spineless_ablation.py
```

The OCR strings remain locating evidence. Physical row interpretation is
adjudicated against the visible page pixels, and the copied `.raw.md` text
remains the lexical authority.
