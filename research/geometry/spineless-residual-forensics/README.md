# Spineless residual geometry forensics

This read-only study reproduces the prior six-page spineless OCR observations,
then traces four residual prose contexts through current TSV admission and
geometry functions. It reuses the prior study's measured crop and deskew
values. It does not estimate angles or change OCR, preprocessing, or
production geometry.

Run from the repository root:

```sh
.venv/bin/python research/geometry/spineless-residual-forensics/run_forensics.py
.venv/bin/python -m pytest -q research/geometry/spineless-residual-forensics/test_forensics.py
```

`results.json` records the six reproduced source/raster/TSV hashes and geometry
counts. `stage-traces.json` contains target-region raw TSV records, parser
outcomes, matched-control token inventories, and vertical-band,
horizontal-region, and candidate-assignment traces. `adjudications.json`
records the manually reviewed first-divergence decisions.

OCR text locators identify pixel regions and source rows; they are not lexical
authority. Visible page pixels remain the authority for physical-row
interpretation.
