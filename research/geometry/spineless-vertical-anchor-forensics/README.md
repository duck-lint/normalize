# Spineless vertical-anchor representation study

This research-only study compares the current `center_y` observation with the lower box edge `y1` while holding the six prior spineless OCR captures fixed. It does not alter Normalize behavior or rerun OCR.

The physical-row oracle is stored in `row-oracle.json`. Its row bounds were drawn from horizontal ink runs in the hash-verified final rasters and manually checked against the pixels. Page furniture, display math, the page-40 figure, and specified malformed OCR regions are excluded from the primary prose rows. Each included row keeps its source TSV row identities and box coordinates in `anchor-comparison.json`.

The shadow replay keeps the production tolerance (4 px), selected page slope (0.0), running median, horizontal-neighbor test, cumulative horizontal extent, candidate generation, and assignment rules. The only primary variant change is `center_y` to `y1`. The center replay must match the saved production line partitions on every page before the comparison is accepted.

Run from the repository root:

```sh
.venv/bin/python research/geometry/spineless-vertical-anchor-forensics/run_anchor_study.py
.venv/bin/python -m pytest research/geometry/spineless-vertical-anchor-forensics/test_anchor_study.py
```

Raster reconstruction in the runner is used only to check saved source and pixel hashes. It does not call Tesseract. Diagnostic output is JSON/text; generated page images are not part of this study's committed artifacts.
