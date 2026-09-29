# Local slope support forensics

Research-only falsification study based on the 46 adjudication records in
[`baseline-slope-forensics`](../baseline-slope-forensics/README.md). It
measures per-event pixel support, tests a label-blind local gate against
synthetic geometry, and reruns the unchanged full-page grouping/assignment
path with shear applied only to the target event's token identities.

The result does **not** authorize production work. The gate retains 29 of 37
previously adjudicated repairs, but it creates three additional false splits
and allows three distinct prior harmful contexts through. It abstains on the
display-math event. See [`report.md`](report.md), complete measurements and
holdouts in [`results.json`](results.json), and identity-complete event
records in [`adjudications.json`](adjudications.json).

Run with the repository environment:

```bash
.venv/bin/python research/geometry/local-slope-support-forensics/run_forensics.py
.venv/bin/python -m pytest research/geometry/local-slope-support-forensics/test_local_support.py
```

Rasters are hash-verified against the prior capture and stay under
`/tmp/baseline-slope-forensics`. No OCR was rerun. No raster or PDF is part of
this research directory.
