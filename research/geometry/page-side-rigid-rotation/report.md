# Page-Side Rigid Rotation Ablation

## Scope and method

This experiment starts from the verified `guh` production head, `473e639`
(`Remove oversized token grouping guard`). It does not change production
preprocessing, OCR, geometry, grouping, slope estimation, or fixture expectations.

For each side, the control uses current production preprocessing and its cropped
page-side raster. The experimental path rotates that raster, reruns Tesseract
with the current production settings (`eng`, `--psm 6`), then calls the same
`parse_tsv_rows` and `group_physical_lines` functions. The rotation is Pillow
`Image.rotate`, bicubic interpolation, `expand=True`, white RGB fill. No token
coordinates are transformed after OCR.

Orientation evidence comes from page pixels: Canny edges and long near
horizontal Hough segments in three page-side body regions. Text and OCR line
IDs were not used to estimate angles. Angles are rounded to tenths for the
ablation and are not production settings. The chosen angle is the raster
orientation in image coordinates; the same signed Pillow rotation levels it.

## A. Physical-page orientation

Regional values are the weighted median segment directions in the upper,
middle, and lower body strips. Segment counts and exact measured values are in
`results.json`.

| Fixture side | Chosen correction | Regional pixel estimates | Uncertainty / support |
|---|---:|---|---|
| Relativity 10 left | −0.6° | −0.23°, −0.59°, −0.84° | ±0.3°; all strips agree on negative orientation |
| Relativity 10 right | −1.9° | −2.02°, −1.79°, −1.88° | ±0.2°; strong agreement |
| Relativity 17 left | +0.8° | +0.43°, +0.58°, +1.17° | ±0.35°; same direction in all strips, with a wider spread |
| Relativity 17 right | 0.0° | 0.0°, 0.0°, 0.0° | ±0.1°; effectively horizontal |
| Relativity 23 left | 0.0° | 0.0°, +0.12°, −1.01° (16 low-support segments excluded) | ±0.2°; body strips support horizontal; sparse lower region includes display math |
| Relativity 23 right | 0.0° | −0.16°, 0.0°, 0.0° | ±0.2°; effectively horizontal |
| Stella Maris 03 left | unresolved | No row segments | Declared blank; no printed row can establish orientation |
| Stella Maris 03 right | 0.0° | 0.0°, 0.0°, 0.0° | ±0.1°; effectively horizontal |
| Stella Maris 06 left | 0.0° | 0.0°, 0.0°, 0.0° | ±0.1°; effectively horizontal |
| Stella Maris 06 right | 0.0° | 0.0°, −0.30°, 0.0° | ±0.2°; approximately horizontal |
| Stella Maris 18 left | unresolved | 0.0°, 0.0°, +0.37° | ±0.25°; regional disagreement does not establish one rigid orientation |
| Stella Maris 18 right | 0.0° | 0.0°, +0.29°, 0.0° | ±0.25°; approximately horizontal |

The blank side and Stella Maris 18 left were passed through the diagnostic path
without an experimental correction. The latter stays in the primary corpus as
an unresolved angle, rather than receiving an invented value.

## B. Control baseline

All twelve controls were freshly preprocessed from the exact local PDFs. The
eleven nonblank sides are the primary corpus. Every control selected production
slope `0.0`; the Relativity 10 right side was uncertain because of one
unassigned token. Full image hashes, TSV hashes, admitted token identities,
line bounds/order, tolerance, and gap limits are in `results.json`.

## C. Rotation result

`A/U` means ambiguous/unassigned token counts. Slope values are control →
rotated. Vertical tolerance and horizontal gap limit are shown control →
rotated in pixels. The unchanged geometry can produce a different page-local
gap limit when OCR boxes change width.

| Side | Raster px | Angle | Tokens control → rotated | Lines control → rotated | A/U control → rotated | Slope | Tolerance | Gap limit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Relativity 10 left | 545×813 → 555×819 | −0.6° | 191 → 191 | 26 → 23 | 0/0 → 0/0 | 0 → 0 | 4 → 4 | 72 → 72 |
| Relativity 10 right | 556×983 → 590×1001 | −1.9° | 263 → 263 | 62 → 40 | 0/1 → 0/0 | 0 → 0 | 4 → 4 | 78 → 76 |
| Relativity 17 left | 538×777 → 550×785 | +0.8° | 138 → 138 | 30 → 22 | 0/0 → 0/0 | 0 → 0 | 4 → 4 | 77 → 78 |
| Relativity 17 right | 538×974 → 538×974 | 0.0° | 305 → 305 | 32 → 32 | 0/0 → 0/0 | 0 → 0 | 4 → 4 | 66 → 66 |
| Relativity 23 left | 535×818 → 535×818 | 0.0° | 143 → 143 | 24 → 24 | 0/0 → 0/0 | 0 → 0 | 4 → 4 | 58 → 58 |
| Relativity 23 right | 540×977 → 540×977 | 0.0° | 226 → 226 | 32 → 32 | 0/0 → 0/0 | 0 → 0 | 4 → 4 | 68 → 68 |
| Stella Maris 03 left (blank) | 646×991 → 646×991 | unresolved | 385 → 385 | 101 → 101 | 4/6 → 4/6 | 0 → 0 | 6 → 6 | 108 → 108 |
| Stella Maris 03 right | 619×821 → 619×821 | 0.0° | 133 → 133 | 23 → 23 | 0/0 → 0/0 | 0 → 0 | 4 → 4 | 74 → 74 |
| Stella Maris 06 left | 638×1129 → 638×1129 | 0.0° | 255 → 255 | 42 → 42 | 0/0 → 0/0 | 0 → 0 | 4 → 4 | 72 → 72 |
| Stella Maris 06 right | 634×1128 → 634×1128 | 0.0° | 271 → 271 | 38 → 38 | 0/0 → 0/0 | 0 → 0 | 4 → 4 | 70 → 70 |
| Stella Maris 18 left | 625×818 → 625×818 | unresolved | 68 → 68 | 23 → 23 | 0/0 → 0/0 | 0 → 0 | 4 → 4 | 84 → 84 |
| Stella Maris 18 right | 626×1092 → 626×1092 | 0.0° | 132 → 132 | 33 → 33 | 0/0 → 0/0 | 0 → 0 | 4 → 4 | 81 → 81 |

The chosen nonzero rotations leave the production slope selector at `0.0` on
every side. The same production tolerance formula and horizontal gap rule were
used throughout.

## D. Known fragmentation cases

- **Relativity 10, “embankment” row:** control split the visible row around
  “as observed from the embankment, is uniform and in a” into two bands;
  −0.6° rotation joins it. The scan shows one continuous printed row.
- **Relativity 10, additional slanted body rows:** the left page has four
  changed repaired rows; the right page has twenty repaired rows. Their full
  word locators, boxes, grouping memberships, and bounds are enumerated in
  `adjudications.json`.
- **Relativity 10 right, “If K is a Galileian co-ordinate system, then every
  other”:** control grouped the visible row into two bands. Rotation creates
  three bands (`If … co-ordinate` / `system, every` / `then other`). The scan
  shows one printed row. This is a new false split caused by rotation.
- **Relativity 17 left:** five continuous visible body rows, including rows
  around “railway embankment” and “consequence,” go from two to four control
  bands to one rotated band apiece.
- **Relativity 17 right, “reference-body”:** this page is effectively
  horizontal. The row is one control band and one rotated band; rotation does
  not change it.

Historical contexts are crosswalked by word locator and pixel box in
`results.json`. The previous slope capture used a different implicit Tesseract
page segmentation setting, so historical OCR source-row numbers are not reused.

## E. Changed-event adjudication

All 30 line-membership changes among exactly aligned OCR identities are
enumerated in `adjudications.json`, with control and rotated boxes, all line
members (including unmatched locators), line bounds, rotation angle, and visible
interpretation.

| Classification | Count |
|---|---:|
| `repaired_false_split` | 29 |
| `destructive_merge` | 0 |
| `new_false_split` | 1 |
| `benign_difference` | 0 |
| `unresolved` changed events | 0 |

The prior display-math context was not forced: Relativity 23 left received no
rotation, and its crosswalk remains unresolved. Therefore it is not counted as
a changed event.

## F. Already-correct geometry and safety checks

No changed event joins two visibly distinct printed rows. Running headers, page
numbers, the Relativity 17 figure, display math, and short Stella Maris dialogue
lines remain separated in the control/rotated comparison. Pages with an
established angle near zero have identical input/output image hashes at the
chosen angle. The clear safety exception is the new false split on Relativity
10 right. The blank Stella Maris side remains OCR-noisy; blank-page suppression
was not part of this experiment.

## G. Comparison with slope-compensation research

The historical local-slope adjudications contain 37 `repaired_false_split`, 8
`new_false_split`, and 1 `unresolved` event records. By the pixel-box/text
locator crosswalk to fresh production PSM 6:

- 25 of the 37 prior repaired contexts become one geometry band after rotation;
- 9 remain multi-band, including the harmful Relativity 10 right row and
  horizontal-looking rows on Stella Maris pages;
- 2 are already one band in the fresh current control;
- 1 repaired context cannot be fully identity-crosswalked;
- all 8 prior false-split contexts remain one band in current control and after
  the rotation comparison;
- the prior display-math event remains unresolved.

This comparison is qualified: the old baseline capture called
`image_to_data` without `config=`, whereas production geometry uses
`--psm 6`. Fresh PSM 6 counts therefore differ even where the production crop
hash matches the historical crop hash. The stored crosswalk uses text locators
and pixel boxes and marks incomplete identity matches unresolved.

Upstream rotation makes downstream nonzero slope compensation unnecessary on
the rotated pages, in the sense that production selects `0.0` before and after
and the corrected rows group better. It does not make the abstraction
sufficient: the fresh crosswalk retains multi-band rows on near-horizontal
pages, and one rotated page row is newly fragmented.

## H. Angle sensitivity

Every side with an established angle was tested at chosen angle ±0.2°. The
delta corresponds to roughly 1.9–2.3 pixels of end-to-end vertical displacement
over these page widths. Across 20 perturbation runs, 11 retained the chosen
grouping partition over shared token identities and 9 retained the repaired
event identities.

Sensitivity is poor on some pages. Relativity 10 right at −1.7° admitted 98
tokens and produced 16 lines, versus 263 tokens and 40 lines at the chosen
−1.9° correction. Stella Maris 06 also changed grouping under both
perturbations. Other pages were stable on both sides of the delta. The synthetic
0.2° error control stayed at four distinct lines, but that does not override
the real-page instability.

## I. Blank-side diagnostics

Stella Maris 03 left was visually blank and excluded from the primary decision.
OCR admitted 385 boxes before and 385 after the identity-path diagnostic. Both
geometries are `uncertain`, with 4 ambiguous and 6 unassigned tokens. No
orientation could be established from printed rows.

## J. Decision

**Evidence remains unresolved.** Rigid rotation has a clear causal benefit on
many slanted Relativity body rows, but this corpus does not meet the stated
sufficiency gate: it creates one visible new false split, leaves multiple
historical contexts multi-band, one nonblank side has no established single
angle, and the ±0.2° real-page results are not stable. This supports retaining
page-side rotation as a separate future research question; it does not support
production authorization from this ablation.

## K. Verification

| Check | Result |
|---|---|
| `guh` head before work | `473e639b6fe335ffb527d2338234d38e311189ba` |
| Current full-suite baseline | 188 passed, 1 skipped |
| Focused rotation research tests | 9 passed |
| Relevant geometry/preprocessing tests | 109 passed, 1 skipped |
| Full repository suite after research changes | 188 passed, 1 skipped |
| Six fixture control preprocessing and OCR | 6 spreads, 12 sides; fresh captures |
| Rotated OCR/geometry and angle sensitivity | 10 established angles; 20 perturbations; 2 unresolved page-side angles |
| Production source hashes | `geometry.py`, `rendering.py`, and preprocessing config match `guh` |
| Tracked `.png` / `.pdf` files | None |
| Branch | `research/page-side-rigid-rotation` |
| `git diff --check` | Clean |
| Commit SHA and post-commit working-tree status | Reported in final handoff |
