# Baseline slope forensics

Completed research-only study of the production baseline-slope search at
`473e639b6fe335ffb527d2338234d38e311189ba`. It establishes the current
singleton-veto mechanism, records all 201 candidate slopes on each nonblank
production side, measures text-row slope from current scan pixels, compares two
slope substitutions, and adjudicates every changed grouping event.

The result does **not** authorize a production estimator experiment. The
pixel-row prototype repairs many real false splits but creates new ones; the
token-cohesion alternative fails synthetic counterexamples. See
[`report.md`](report.md), full machine-readable candidate results in
[`results.json`](results.json), identity-complete changes in
[`adjudications.json`](adjudications.json), and the once-captured admitted OCR
records in [`admitted_tokens.json`](admitted_tokens.json).

All rasters and raw TSVs remain local under `/tmp/baseline-slope-forensics`.
No production source, crop configuration, fixture expectation, PNG, or PDF is
included in the research commit.
