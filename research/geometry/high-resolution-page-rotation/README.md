# High-resolution page-side rotation

This research change applies configured page-side angles at 300 DPI after the exact established page crop and before LANCZOS reduction to the 144-DPI OCR raster. The renderer contains no fixture-name angle logic; angles live in `fixtures/preprocessing.json`.

The captured control is the unmodified `guh` preprocessing/OCR run at `473e639b6fe335ffb527d2338234d38e311189ba`. `baseline.json` stores all twelve page-side OCR observations and geometry. `results.json` stores fresh OCR/geometry for all twelve new outputs and three Relativity 10 right sensitivity variants. `adjudications.json` crosswalks exact OCR-token sequence identities, boxes, line groups, and prior event IDs. Generated raster inputs remain local in `/tmp`.

Run the experiment from the repository root with:

```sh
.venv/bin/python research/geometry/high-resolution-page-rotation/run_ablation.py
```

Run focused preprocessing checks with:

```sh
.venv/bin/pytest -q tests/test_page_rotation_preprocessing.py tests/test_page_side_cropping.py tests/test_slice1.py
```

The angle application is tested here; automatic angle estimation remains out of scope. See `report.md` for findings and the merge decision.
