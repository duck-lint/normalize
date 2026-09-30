# Frozen-OCR page-coordinate rotation ablation

This research-only experiment keeps OCR observations fixed while moving each
admitted token rectangle into the page-side coordinate frame established by the
prior pixel-orientation study. It imports the current production crop, TSV
admission, and physical-line grouping functions. Production source and fixture
expectations are not changed.

## Reproduction

Run the one-capture stage with output outside the repository so generated
rasters stay local:

```bash
.venv/bin/python research/geometry/frozen-ocr-page-transform/run_ablation.py \
  --output-dir /tmp/normalize-frozen-ocr-page-transform
```

This preprocesses the six production fixtures and calls Tesseract once for each
of their twelve page sides. Its `results.json` contains the frozen admitted
token records. Recompute all affine variants and adjudication from that saved
capture, without invoking OCR again:

```bash
.venv/bin/python research/geometry/frozen-ocr-page-transform/run_ablation.py \
  --reuse-frozen-json /tmp/normalize-frozen-ocr-page-transform/results.json \
  --output-dir /tmp/normalize-frozen-ocr-page-transform/recomputed
```

The committed [results.json](results.json) is the rebuilt result. It includes
all frozen token records, control and transformed geometry, affine matrices,
angle perturbations, prior-event crosswalks, and hashes. Generated page images
are not committed.

Focused checks:

```bash
.venv/bin/python -m pytest -q research/geometry/frozen-ocr-page-transform/test_frozen_transform.py
```

See [report.md](report.md) for the complete interpretation and limits.
