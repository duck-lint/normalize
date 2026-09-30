# Spineless acquisition A/B geometry study

## A. Inputs and authority

The bound controls were reproduced from the current `guh` production path using
the exact local fixture PDFs and current page-side crops. The spineless pages
were consumed directly from the six JPGs; they were not converted to PDF.
Each JPG is one printed page. All six JPGs are 2550×3300 RGB, matching an
8.5×11 inch scanner bed at 300-DPI dimensions. Their complete SHA-256 hashes,
per-page OCR TSV hashes, and all admitted geometry records are in
[`results.json`](results.json).

| Printed page | Bound fixture and side | Spineless input |
|---:|---|---|
| 26 | `relativity_pdf10_pp26-27.left` | `fixtures/einstein/spineless/pg.26.jpg` |
| 27 | `relativity_pdf10_pp26-27.right` | `fixtures/einstein/spineless/pg.27.jpg` |
| 40 | `relativity_pdf17_pp40-41.left` | `fixtures/einstein/spineless/pg.40.jpg` |
| 41 | `relativity_pdf17_pp40-41.right` | `fixtures/einstein/spineless/pg.41.jpg` |
| 52 | `relativity_pdf23_pp52-53.left` | `fixtures/einstein/spineless/pg.52.jpg` |
| 53 | `relativity_pdf23_pp52-53.right` | `fixtures/einstein/spineless/pg.53.jpg` |

The bound path calls production `preprocess_fixture` and `run_geometry`. A
temporary wrapper captures the TSV produced by that normal geometry call, so
each bound physical side is OCRed once. The spineless research adapter runs
the same `eng`, `--psm 6` Tesseract command and calls the unchanged production
`parse_tsv_rows` and `group_physical_lines` functions. Both paths use
Tesseract 5.3.4. No production file or fixture expectation was changed.

## B. Spineless crop and whole-page orientation

Pixel color statistics distinguish the yellowed paper from the white scanner
bed. Across the six images, the measured paper extent reaches x=1460–1478 and
y=2294–2297. The crop `[0, 0, 1500, 2340]` retains the fullest observed page
edge with 22 px right and 43 px bottom margins and removes the large remaining
scanner-bed area. The left and top sheet edges meet the source image boundary;
the crop retains the complete available image on those edges. This is a
pixel-established bounding crop, not an OCR crop.

One correction angle was estimated per page from three fixed vertical regions
using dark-pixel row projection. Regional estimates agree within 0.06–0.24°.
The page transform is one Pillow bicubic rotation with expansion and white
fill. The output is reduced to a 144-DPI-equivalent raster with LANCZOS and
nearest-pixel half-up dimension rounding. The crop, angle, expanded
dimensions, output dimensions, and output pixel hash are recorded per page.

| Page | Prior bound-page correction estimate | Spineless correction | Regional estimates | Range | Estimated uncertainty | Residual regions | Final size |
|---:|---:|---:|---|---:|---:|---|---:|
| 26 | −0.6° | +0.44° | +0.44°, +0.44°, +0.50° | 0.06° | ±0.05° | −0.10°, −0.08°, −0.08° | 729×1129 |
| 27 | −1.9° | −0.94° | −1.04°, −0.94°, −0.90° | 0.14° | ±0.09° | −0.08°, −0.08°, −0.08° | 739×1136 |
| 40 | +0.8° | +0.86° | +0.78°, +0.86°, +0.92° | 0.14° | ±0.09° | −0.10°, −0.08°, −0.08° | 737×1135 |
| 41 | 0.0° | −0.80° | −0.88°, −0.80°, −0.76° | 0.12° | ±0.08° | −0.08°, −0.08°, −0.08° | 736×1134 |
| 52 | 0.0° | +0.74° | +0.64°, +0.74°, +0.88° | 0.24° | ±0.14° | −0.08°, −0.08°, −0.08° | 735×1133 |
| 53 | 0.0° | −0.38° | −0.46°, −0.38°, −0.36° | 0.10° | ±0.07° | −0.08°, −0.08°, −0.08° | 728×1128 |

The listed uncertainty is half the regional range plus one 0.02° search
increment. The regional residual estimates agree within one search increment
after deskew, so one rigid orientation is supported for all six sheets.
The previous bound angles are prior study correction angles, not estimates
recomputed from the current bound rasters. They describe a different geometry:
the spineless values measure loose-sheet scanner placement. The three
independent regions support a single rigid orientation for each loose sheet.
The page-52 range is the largest at 0.24°; its residual regional estimates
still agree within one 0.02° search increment after deskew.

## C. Bound versus spineless geometry

The line-count difference includes different retained physical regions and
the different raster scale/crop; it is not itself a correctness score. The
primary evidence is the physical row membership adjudication below.

| Page | Bound size | Spineless size | Tokens B→S | Lines B→S | Ambiguous/unassigned B→S | Slope B→S | Tolerance B→S | Gap limit B→S | Median confidence B→S |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 26 | 545×813 | 729×1129 | 191→202 | 26→36 | 0/0→0/0 | 0→0 | 4→4 | 72→66 | 96.37→96.46 |
| 27 | 556×983 | 739×1136 | 263→264 | 62→46 | 0/1→0/0 | 0→0 | 4→4 | 78→77 | 96.19→96.42 |
| 40 | 538×777 | 737×1135 | 138→139 | 30→23 | 0/0→0/0 | 0→0 | 4→4 | 77→76 | 96.41→96.63 |
| 41 | 538×974 | 736×1134 | 305→307 | 32→34 | 0/0→0/0 | 0→0 | 4→4 | 66→66 | 96.53→96.49 |
| 52 | 535×818 | 735×1133 | 143→148 | 24→26 | 0/0→0/0 | 0→0 | 4→4 | 58→54 | 96.20→96.34 |
| 53 | 540×977 | 728×1128 | 226→221 | 32→33 | 0/0→0/0 | 0→0 | 4→4 | 68→66 | 96.28→96.37 |

For every side the unchanged production slope estimator selected `0.0`. It
selected zero on both bound and spineless controls. The estimator's output
therefore does not independently distinguish the acquisition geometries in
this corpus. Vertical tolerance remained 4 px; the horizontal gap limit
changed only with the observed token-width distribution.

## D. Known physical-row cases

On page 26, four of the known visibly straight rows become one spineless
geometry line:

* `as observed from the embankment, is uniform and in a` — bound split after
  `the`; spineless is one line.
* `the moving railway carriage, we should find that the` — bound split into
  two bands; spineless is one line.
* `with respect to a co-ordinate system K, then it will also` — bound split
  into two bands; spineless is one line.
* `executing a uniform translatory motion with respect to` — bound leaves
  `to` in a separate band; spineless is one line.

One already-correct bound row becomes fragmented in the spineless geometry:
`changes its position relative to the embankment yet` is one bound line, but
the spineless geometry puts `yet` in a separate line. The source pixels show
one printed row. This is a real acquisition/OCR geometry regression in the
spineless result, not a repaired row.

On page 27, the row beginning `If K is a Galileian co-ordinate system` is
split in both acquisitions. The bound geometry has one unassigned token and
therefore serializes all line bounds as null. The spineless run has no
unassigned token, but divides the visible row between `...co-ordinate then
other` and `system, every`. This is a shared residual geometry failure.

The page-27 row `to K, it is in a condition of uniform motion of translation`
is one line in both outputs. Spineless OCR misreads the opening as `40K`; the
geometry is still one row. The row `affords an insufficient foundation for
the physical` is visible in the JPG but none of its words were admitted by
spineless OCR, so it cannot be adjudicated from geometry.

On page 40, five previously fragmented rows are each unified in the
spineless geometry, including `railway embankment. We suppose a very long
train`, `train will with a vantage view the train as a rigid reference-`, and
`to the embankment. As a natural consequence, however`. The figure labels
(`Train`, `A`, `B`, `Embankment`, and `Fig. 1`) remain in distinct spatial
lines from body text.

Page 41's text rows and page number remain separated. The spineless crop also
produces two narrow OCR marks along the left scan edge; they do not join any
printed row. On page 52, equation components remain distinct from the prose
before and after the display math. The prior ambiguous display-math
interpretation remains unresolved. Page 53's formula/prose separation is
preserved, but the visible line `and for still greater velocities the
square-root becomes` remains fragmented in both acquisitions and is split
into more bands in the spineless geometry.

Complete group members, source TSV rows, token boxes, line bounds, and line
ordering are preserved in `results.json`. The focused context ledger and
prior event references are in [`adjudications.json`](adjudications.json).

## E. Changed-event adjudication

| Classification | Count | Adjudication |
|---|---:|---|
| `spineless_repairs_bound_false_split` | 29 | All 29 prior raster-rotation repair contexts map to one line in the spineless geometry. |
| `spineless_creates_false_split` | 1 | Page 26 `...embankment yet`; the bound line is split before `yet`. |
| `spineless_creates_destructive_merge` | 0 | No distinct physical rows were joined. |
| `both_correct` | 4 | Page 27 `to K...`; page 40 figure/body separation; page 41 body/page-number separation; page 53 equation/prose separation. |
| `both_wrong` | 2 | Page 27 `If K...` row; page 53 `and for still greater velocities...` row. |
| `different_but_benign` | 1 | Page 41's two scanner-edge OCR marks. |
| `unresolved` | 2 | Page 27 highlighted row with no admitted words; page 52 display-math grouping. |

These categories describe materially relevant contexts, not every token whose
coordinates changed between acquisitions. The count of false splits is based
on visible printed rows, not on a reduction in line count.

## F. Prior-study crosswalk

The prior raster study's 29 repaired contexts reproduce as one line in all
29/29 spineless cases. Its separate page-27 `If K...` new-split event remains
a split in both the current bound and spineless controls, so the flat scan
does not create that residual.

The frozen-coordinate study's 30 repair contexts reproduce as one spineless
line in 29/30 cases. The remaining `If K...` row is still split. Of the two
false splits caused by transforming axis-aligned boxes, the `to K...` event
is one line in the spineless scan; the `affords...foundation...physical` row
is not OCRed, so that case is unresolved rather than counted as repaired.

The local-slope study had 37 repaired contexts, 8 harmful contexts, and one
unresolved display-math context across its broader corpus. This experiment
overlaps 30 repaired, 4 harmful, and one unresolved Relativity context. The
spineless result puts 29 of the 30 repair contexts into one geometry line;
the residual is `If K...`. Of the four prior harmful contexts, two map to one
spineless line, while the page-26 `...embankment yet` and page-53
`velocities...square-root becomes` contexts remain fragmented. The page-52
display-math case remains unresolved. The remaining events in those prior
studies belong to Stella Maris pages and have no spineless counterpart in
this input corpus.

The crosswalk supports the upstream acquisition explanation for many
Relativity rows, while the persistent page-27 and page-53 cases show that
binding is not the only source of grouping failure.

## G. OCR and lexical workflow

Admitted token counts change little between acquisitions: page-by-page
differences range from −5 to +11 tokens. Median confidence remains between
96.19 and 96.63 in both paths. The visibly useful evidence is geometric; the
spineless OCR still has spelling, punctuation, and segmentation errors. It
also misses the highlighted page-27 `affords...physical` row and yields
several tiny edge/figure marks.

As a rough lexical diagnostic, normalized word-sequence comparison of each
two-page JPG pair against the matching `.raw.md` gives:

| Printed pages | Canonical raw words | Spineless OCR words | In-order exact matches / raw words | Sequence similarity |
|---|---:|---:|---:|---:|
| 26–27 | 480 | 456 | 423 / 480 (88.1%) | 90.4% |
| 40–41 | 438 | 441 | 427 / 438 (97.5%) | 97.2% |
| 52–53 | 359 | 354 | 311 / 359 (86.6%) | 87.2% |

These figures are approximate and include headings, page numbers, and math.
They show that direct OCR could provide a useful lexical candidate, especially
on pages 40–41. It remains noisy and non-authoritative. Manual PDF
copy/paste is one acquisition method for the lexical channel, not an
architectural requirement; the independent canonical wording channel remains
materially valuable and retains its current authority.

## H. Source-model implication

The six direct JPG runs establish that an ordered collection of physical page
images is viable as a research input form. They do not establish that a
production source abstraction should replace the current fixture/PDF contract
or define how arbitrary image sequences obtain lexical authority. The next
architecture decision can treat an ordered page-image source adapter as a
supported candidate, with PDF as another possible source adapter.

## I. Decision

`spineless_acquisition_substantially_improves_geometry_but_residual_failures_remain`

Flat acquisition removes many previously reviewed false splits without any
downstream change. It does not remove every failure: the page-27 `If K...`
row remains split, the page-26 `...embankment yet` row newly splits, and the
page-53 prose row remains fragmented. There are no destructive merges. Thus
the evidence supports binding as a material contributor, not as a sufficient
explanation for every Normalize grouping failure.
