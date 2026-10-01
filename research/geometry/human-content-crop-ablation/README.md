# Human OCR-content crop ablation

This research-only study compares six locally supplied, human-selected OCR-content JPEG crops with the hash-reproduced spineless physical-sheet inputs. It runs one global deskew on each crop, downsamples with the prior study's 144/300 convention, captures raw Tesseract TSV, and calls the current production parser and physical-line geometry unchanged.

The crops are the authority for this experiment. The harness does not change crop bounds, image appearance, OCR settings, or geometry. It records the source-to-crop pixel registration and JPEG encoding differences. Source scans and human crops are local fixture inputs and are intentionally not committed.

## Reproduction

From the repository root, with the local spineless fixture images available:

```sh
PYTHONPATH=. .venv/bin/python research/geometry/human-content-crop-ablation/run_ablation.py
```

This invokes Tesseract. The committed JSON files preserve the captured observations, so the focused unit test does not invoke OCR. See [report.md](report.md) for the measured outcomes and the recorded duplicate invocation caused by a failed JSON serialization attempt.

## Files

- `results.json`: input provenance, orientation, transforms, raw TSV, production geometry, and row-oracle mapping.
- `row-oracle.json`: pixel-row oracle carried forward from the accepted vertical-anchor study.
- `row-comparison.json`: physical-row classifications for all 105 oracle rows.
- `physical-sheet-baseline.json`: exact-hash reproduction of the prior spineless control OCR.
- `prior-row-classifications.json`: prior physical-sheet classifications.
- `ocr-comparison.json`: raw and admitted OCR comparisons.
- `adjudications.json`: known-context crosswalks and page-27 target evidence.
- `run_ablation.py`: research harness.
