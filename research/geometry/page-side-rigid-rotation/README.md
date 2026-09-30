# Page-Side Rigid Rotation Ablation

Research-only test of whether correcting one rigid orientation per physical
page side before OCR improves current physical-line geometry.

Run from the repository root with:

```bash
PYTHONPATH=src .venv/bin/python research/geometry/page-side-rigid-rotation/run_rotation_ablation.py \
  --output /tmp/normalize-page-side-rigid-rotation
```

The runner calls current production preprocessing to obtain each cropped side.
It captures fresh control OCR, rotates that side image with Pillow
`Image.rotate` (`bicubic`, `expand=True`, white RGB fill), then reruns the exact
production Tesseract configuration (`eng`, `--psm 6`). It passes both TSVs to
the unchanged `normalize.geometry.parse_tsv_rows` and
`normalize.geometry.group_physical_lines` functions. Page-side angles and their
pixel evidence are stored in the runner and result record; no angle is written
to production configuration.

The output directory contains generated PNG rasters and a full `results.json`.
Those rasters are local diagnostics. The checked-in `results.json` is text-only.
`adjudications.json` lists every matched-token grouping change, its control and
rotated boxes, group memberships, and the pixel-based interpretation.

The primary corpus has eleven nonblank sides. Stella Maris 03 left is processed
for blank-side diagnostics and excluded from the correctness decision. Synthetic
pages are generated at runtime; they are not stored as image fixtures.
