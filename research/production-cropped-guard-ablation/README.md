# Production-cropped oversized-guard ablation

This directory records a research-only paired comparison on the twelve 144-DPI page-side outputs currently produced by Slice 1 for the six configured fixture PDFs.

- `report.md` gives the decision and summary.
- `results.json` stores input hashes, one shared OCR observation per page, complete source-row memberships, guard trace, changed-event pixel measurements, and control evidence.
- `adjudications.json` stores human visual decisions separately from generated geometry evidence.
- `run_ablation.py` runs current production preprocessing and `run_geometry`, captures one Tesseract TSV per page, then evaluates both grouping variants using the same admitted tokens.
- `test_ablation.py` covers paired-run invariants and the stored identity-complete corpus result.

Run from the repository root with project dependencies and the exact six local fixture PDFs available:

```sh
python3.12 research/production-cropped-guard-ablation/run_ablation.py
PYTHONPATH=src:research/production-cropped-guard-ablation python3.12 -m pytest research/production-cropped-guard-ablation/test_ablation.py
```

The run writes production page PNGs and geometry annotations only under `/tmp/normalize-guard-ablation/`. The event review sheets used for the committed human adjudications were also kept local under `/tmp/normalize-guard-ablation/event-sheets/`. No page pixels are committed. If a new run produces changed events absent from `adjudications.json`, it stops for human review rather than inheriting a decision by token string.

The result is bounded to this fixture corpus. It supports a separate production-removal task; it does not remove the guard.
