# Page 27 Tesseract Context-Sensitivity Forensics

This research-only experiment holds the page-27 spineless raster, Tesseract
5.3.4, `eng`, and `--psm 6` fixed. It varies only a rectangular crop of the
exact raster. It does not run Normalize geometry.

Run from the repository root with:

```sh
.venv/bin/python research/geometry/page27-tesseract-context-forensics/run_context_study.py
.venv/bin/python -m unittest research/geometry/page27-tesseract-context-forensics/test_context_study.py
```

The runner rebuilds the final 739×1136 raster using the crop and deskew values
stored in the prior spineless study. It checks the JPG, raster, Tesseract
version, and full-page TSV hashes before it runs any experimental crop. A
mismatch stops the run. Diagnostic crop images are not saved; all committed
artifacts are text or JSON.

`crop-manifest.json` records the exact page-coordinate rectangles and pixel
hashes for the target and matched-control windows. `raw-tsv-comparison.json`
contains raw word and line-level observations, page-coordinate boxes, repeated
TSV hashes, and outcome labels. The physical row rectangles are fixed from
visible pixels before crop OCR; OCR wording is only a locator.
