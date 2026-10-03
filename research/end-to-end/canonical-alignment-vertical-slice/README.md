# Canonical alignment vertical slice

This acceptance run consumes the six frozen exact-source geometry observations
from the prior research commit `3087f18bb20f562e5dbcdf3a36771b1e14fdde0b`.
It does not rerun OCR. The acquisition metadata records all six exact-source
capture matches, source hashes, rectangles, angles, raster/TSV hashes, and OCR
configuration.

The harness maps the existing canonical raw fixture byte ranges to page IDs,
converts those byte offsets to decoded-character offsets, and calls the new
production `reconstruct_document` and `emit_markdown` functions. It writes the
generated outputs and verifies lexical token order before loading any
`*.expected.json` or `*.normalized.md` oracle.

Run the deterministic downstream harness with:

```bash
./.venv/bin/python research/end-to-end/canonical-alignment-vertical-slice/run_vertical_slice.py
```

The CLI command `normalize reconstruct` accepts raw text, production geometry,
and an explicit page-span manifest. See
`harness/project-spec/DOWNSTREAM_RECONSTRUCTION.md` for the production data
contract and matching/reconstruction rules.

Artifacts:

- `generated.md` — all six pages in order, with fixture-pair boundaries.
- `per-page/*.md` — convenience output for each printed page.
- `per-page/26-27.md`, `40-41.md`, `52-53.md` — paired outputs retaining cross-page continuity.
- matching `.json` files — alignment, structural-block, and provenance sidecars.
- `geometry-observations.json`, `page-spans.json` — frozen geometry and source-range inputs.
- `results.json`, `comparison.json`, `diagnostics.json`, `defects.json`, `propagation.json`, `report.md` — acceptance evidence.

No source image, OCR output, or generated raster is tracked.
