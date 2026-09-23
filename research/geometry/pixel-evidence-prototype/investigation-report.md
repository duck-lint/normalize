# Pixel-evidence prototype and adversarial evaluation

This is a source-independent research prototype. It measures observable image
properties around proposed horizontal token intervals; it does not assign
tokens, resolve uncertainty, choose a classifier, or modify production
geometry.

## A. Baseline and evidence integrity

The isolated branch started at
`699771d01c1a83c6f89c6a7eb2102e79a709b671`, with a clean working tree. The
prior evidence corrections branch is an ancestor of this revision's research
history. The existing residual-forensics, diagnostic-investigation, and
evidence-corrections snapshots were read and remain unchanged.

The preserved corrected synthetic inputs are under
`research/geometry/evidence-corrections/pixel-cases/`. Their prior results
file records identical box/TSV inputs, distinct source arrays, and equivalent
complete box-only state. The new prototype re-measures those files and records
their hashes rather than copying them.

Unannotated preprocessed page images are available locally under
`/tmp/normalize-residual-forensics` for this run. They are not repository
artifacts and are not copied into this directory. Their absolute paths and
content hashes are recorded in `results.json` and the manifest. Reproduction
on another checkout requires the same preserved preprocessing output or an
explicitly equivalent, hash-verified input; synthetic pixels are not a
substitute for missing scans.

The Relativity 17 residual remains the stable identity
`(relativity_pdf17_pp40-41, right, 23)`. The distinction between GH-11's
twelve-token lifecycle report and the currently reproduced seven-token
observation is inherited from the prior erratum and is not collapsed here.

Reproduce with:

```text
.venv/bin/python research/geometry/pixel-evidence-prototype/prototype.py --real-root /tmp/normalize-residual-forensics
.venv/bin/python -m pytest -q tests/test_pixel_evidence_prototype.py
.venv/bin/python -m pytest -q
```

## B. Prototype interface

`measure_bridge` accepts a source image, token boxes, a half-open proposed
region, candidate token-band geometry, and explicit parameters. It returns:

- thresholded ink occupancy;
- occupied-column counts and empty-column runs;
- row-wise vertical distribution and ink centroid;
- baseline-relative alignment using the supplied baseline and slope;
- connected components for 4- and 8-connectivity at scales 1, 2, and 4.

Raw observations are separate from interpretations. There is no
`same_line` Boolean, weighted confidence, combined score, or assignment output.
Parameters are fixed and recorded in the result: thresholds 64, 128, and 192;
component scales 1, 2, and 4; connectivity 4 and 8; BOX downsampling; and a
3-pixel baseline-relative tolerance. No deskew, denoising, morphology, or
additional thresholding is applied.

## C. Controlled synthetic results

The corrected two-sided and one-token-per-side pairs remain the initial
controls. Their box-only complete states are equivalent, but their pixel
measurements differ. The deliberately identical-image control reports no raw
measurement difference. A deliberately altered box payload produces a
different input hash and is rejected as an identical-input control.

The seven additional synthetic cases hold the two-sided box geometry constant:

| Case | Construction | Strongest observation | Limitation |
| --- | --- | --- | --- |
| Single-pixel noise bridge | one-pixel path across disconnected regions | occupancy and component connectivity detect a bridge | false-merge signal from noise |
| Disconnected glyphs, same row | separated glyph blocks across the span | occupied columns detect localized ink | components do not establish row identity; spaces remain empty |
| Ordinary word spaces | separated word-like clusters | empty runs expose spacing | a real row can contain large empty runs |
| Genuinely long printed word | dense ink fills the wide span | occupancy and connectedness are high | width/ink cannot distinguish a long word from an OCR span in general |
| Neighboring-row ink | ink is below the candidate band | vertical distribution and baseline alignment localize it | a broad ROI would produce a false continuity signal |
| Skewed continuous text | support follows a sloped baseline | supplied baseline slope changes alignment observations | slope must come from authorized geometry evidence, not a tuned rescue |
| Low-resolution/faint ink | gray support varies by threshold | thresholds 64/128/192 disagree | threshold sensitivity prevents a fixed interpretation |

These are constructed demonstrations, not performance claims about arbitrary
scans. The synthetic signal is therefore useful for falsifying naive
measurements, not for selecting a production threshold.

The results also record exploratory pairwise correlations across the
constructed cases. Occupancy, occupied-column fraction, and empty-run length
are derived views of column ink distribution; their correlation is not
independent evidence. Component counts and vertical alignment vary differently
in some adversarial cases, but that variation does not establish that either
measurement identifies a physical row.

## D. Preserved real-scan results

The prototype analyzed the available unannotated Relativity 17 right-page
image and recorded three geometry-selected regions:

1. `lightning_A_contact`: the boxes overlap from x=509 through x=516; there
   is no positive blank gap to measure. The region is therefore a contact
   corridor, not proof of continuity.
2. `same_band_of_lightning`: the small interval between two adjacent tokens
   recorded in the same preserved physical band.
3. `nearby_distinct_rows_29_30`: a comparable horizontal interval between two
   nearby preserved rows, used as a negative geometric control.

The measurements report ink presence, vertical concentration, and
baseline-relative alignment for each region. They do not change the preserved
assignment observation: token row 23 remains ambiguous between `line-0003` and
`line-0004`. The word text is retained only for locating/provenance labels;
the interpretation uses boxes and pixels, not lexical meaning.

Relativity 10 is referenced as an available horizontal source image only. Its
vertical fragmentation is outside this prototype's scope and is not resolved.

## E. Information boundary

Pixels establish measurable ink properties in a specified region under a
specified preprocessing state. In the corrected synthetic controls, occupancy,
empty-column structure, vertical distribution, baseline-relative alignment, and
component measurements distinguish the constructed images.

They suggest possible evidence when the region is well localized and the
source image is trustworthy. They do not establish physical-line identity:
noise can imitate continuity, glyphs and spaces can interrupt components,
neighboring rows can intrude, skew changes alignment, and thresholds change
what counts as ink. Measurements are also correlated; occupancy, occupied
columns, and empty runs are different views of related evidence rather than
independent proof.

The current evidence supports using pixel measurements as an explicitly
uncertain observation channel. It does not support deterministic assignment,
a universal threshold, or a production classifier.

## F. Next decision

Do not integrate this signal into production yet. A narrowly scoped integration
experiment would require, at minimum:

- hash-verified unannotated page images for all relevant fixture and negative
  controls;
- source-independent labels or an authority-backed evaluation protocol for
  continuity, separation, and justified uncertainty;
- repeated scale, threshold, noise, skew, glyph-spacing, and neighboring-row
  tests;
- complete identity-level assignment comparisons with no fixture-count-only
  optimization; and
- an explicit contract for when pixel evidence abstains rather than assigns.

Until those observations exist, the correct outcome is unresolved uncertainty,
not a production threshold or geometry change. Non-greedy vertical clustering
is not evaluated here.

## Scope

Changed files are confined to this prototype directory and
`tests/test_pixel_evidence_prototype.py`. Production geometry, the
identity-complete oracle, existing research snapshots, fixture contracts,
source PDFs, preprocessing, and SYMPHONY remain unchanged.
