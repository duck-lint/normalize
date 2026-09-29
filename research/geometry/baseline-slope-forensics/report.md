# Baseline slope estimator: bounded triage

## Status and decision

This is an incomplete research record. The requested current-crop, current-OCR
and pixel-evidence study could not run in this environment. The available
evidence does not establish that production slope `0.0` is physically wrong on
any current fixture page, and does not identify which mechanism selected zero
on any particular page.

**Decision: unresolved human review required.** This is an execution/evidence
gap, not a finding that zero is correct or that the global linear model is
valid. No production estimator experiment is authorized by this record.

## Start state and environment

- Expected production tip was verified: `473e639b6fe335ffb527d2338234d38e311189ba`.
- Work is on `research/baseline-slope-forensics`; `guh` was not changed.
- The repository contains the six ignored fixture PDFs and `/usr/bin/tesseract`.
- `/usr/bin/python3` is Python 3.12.3, but `pytest`, `pip`, PyMuPDF (`fitz`),
  Pillow, pytesseract, NumPy, OpenCV, and RapidFuzz are unavailable.
- `python3 -m pytest` failed with `No module named pytest`; the test suite and
  production preprocessing/OCR therefore were not run.
- Only recovered preprocessing JSON for Relativity 10 and 17 exists in the
  checked-in prior investigation. It does not provide the twelve current
  production rasters and token captures; historical geometry JSON uses a
  different horizontal-region formula and is not substituted for current
  inputs.
- The ordinary expected baseline (~189 collected, 188 passed, 1 optional
  raster audit skipped) was not reproduced.

## Current estimator mechanics (source inspection)

The unchanged implementation in `src/normalize/geometry.py` evaluates exactly
201 candidates: integer thousandths from `-100` through `+100`, inclusive,
converted to `-0.100` through `+0.100` px/px. Candidate order is ascending,
so negative values are visited before zero and positive values.

For token `t`, adjusted vertical position is `center_y - slope * x`. For each
candidate, `_line_bands` sorts by adjusted center, x, and source row; it adds a
token to the latest band when it is within the rounded page tolerance of that
band's median **or** is within tolerance of a horizontally adjacent token in
that band. The same horizontal gap limit is used to split bands into continuous
regions. The limit is `max(1, 2 * median(positive token widths))`.

The score is the sum across resulting regions of `n * (n - 1) / 2`. Thus it
counts token pairs within a region; it does not directly measure physical-row
truth. Zero's score is computed separately. A nonzero candidate is rejected,
in order, if it produces fewer than two regions, if **any** resulting region
has fewer than two tokens, or if its score is less than or equal to zero's
score. The code does not retain rejection reasons or the candidate landscape.
Among candidates that survive, the largest score wins; equal scores prefer
smaller absolute slope. If no nonzero candidate survives, zero remains selected.

This confirms the singleton gate exists and can veto a candidate regardless
of its score. It does **not** establish that a better-scoring candidate was
vetoed on any fixture. Nor does code inspection alone distinguish “zero has a
better score” from “all better nonzero candidates fail admissibility.” The
per-page difference requires the missing token inputs and instrumentation.

The search is not a direct baseline detector: its objective is coordinate
cohesion subject to those admissibility rules. The score is a model criterion,
not independent physical evidence. Tesseract line IDs are not used by this
estimator.

## Evidence not established

No current 144-DPI side outputs were regenerated. Consequently this record
contains no defensible current-side dimensions, source/output/TSV/token hashes,
admitted token counts, tolerance values, candidate landscapes, singleton
identities, physical-line counts, or unresolved identities. The blank side
was not reprocessed. No row-local pixel slope, fit residual, human row
adjudication, page-global slope comparison, or real changed-event
classification was performed.

The synthetic oracle matrix, alternative estimators, stage-isolated
comparisons, permutation/perturbation/scaling checks, and focused research
tests were also not run. In particular, no zero destructive merges or false
splits can be claimed. Historical residual locators are not reinterpreted.

## Scope boundary

The production estimator, preprocessing, crop config, OCR behavior, horizontal
gap predicate, reconciliation, and fixture expectations are unchanged. No
production geometry experiment should follow from this source inspection
alone. Completion requires a dependency-capable run that captures one shared
OCR input per side, instruments all candidates, and independently adjudicates
physical rows from the matching current page pixels. If current dependencies
remain unavailable, that is a reproducibility blocker rather than evidence
about the geometry mechanism.

## Verification performed

- Verified HEAD and branch start state.
- Inspected the estimator and its direct banding/gap helpers.
- Attempted baseline `python3 -m pytest`; unavailable because pytest is not
  installed.
- Confirmed fixture PDFs are present locally and Tesseract is on PATH.
- Confirmed Python imports for all required libraries fail.
- No raster or PDF is included in this research record.
- Full suite, fixture preprocessing/OCR, focused research checks,
  `git diff --check`, and the tracked-binary check remain required.
