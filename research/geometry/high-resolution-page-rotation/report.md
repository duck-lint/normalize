# High-resolution page-side rotation ablation

## A. Implementation

Production changes are limited to `src/normalize/rendering.py` and `fixtures/preprocessing.json`. The v3 path renders the PDF at 300 DPI, applies existing orientation/spread operations, splits the spread, applies the exact side-local 300-DPI crop, optionally rotates that side, then downsamples to 144 DPI and publishes the usual side image. Tesseract and geometry were unchanged. `harness/project-spec/mvp-implementation-plan.md` documents the path. Focused production tests are in `tests/test_page_rotation_preprocessing.py`; the existing Slice 1 and crop tests were updated for the new working coordinate stage.

Nonzero rotation uses Pillow positive counter-clockwise semantics, bicubic, `expand=True`, white RGB fill. The prior raster study confirmed the same-signed Pillow angle levels the measured raster orientation. Zero and omitted angles do not call the page rotation operation. LANCZOS downsamples with nearest-half-up output dimensions (`floor(rotated_dimension * 144/300 + 0.5)`).

## B. Configuration

`preprocessing-config-v3` has root `dpi: 144` and `render_dpi: 300`. Each spread profile has exact 300-DPI side-local `page_crops` and a `page_rotations` object. A side absent from this object has no authorized transform; a configured `0.0` is a measured no-op.

Configured values: Relativity 10 left −0.6°, right −1.9°; Relativity 17 left +0.8°, right 0.0°; Relativity 23 left/right 0.0°; Stella Maris 03 right 0.0°; Stella Maris 06 left/right 0.0°; Stella Maris 18 right 0.0°. Stella Maris 03 left and Stella Maris 18 left are omitted and untransformed.

## C. Crop reuse

The rendering config uses the `recovered_300dpi_bounds_exclusive` rectangles from `fixtures/page-crop-bounds.json` for all twelve sides. That evidence records the exact canonical rerender and crop match as 12/12. No crop was remeasured or back-calculated from the rounded former 144-DPI values.

## D. Provenance

For Relativity 10 left, metadata records: PDF page indices 1/10; 300-DPI source side 1650×2550; crop `[201,483,1334,2175]` (1133×1692); correction −0.6° CCW; bicubic; expanded canvas; white fill; post-rotation 1151×1704; LANCZOS; final 552×818 at 144 DPI.

For Relativity 10 right: source side 1650×2550; crop `[0,59,1158,2106]` (1158×2047); correction −1.9° CCW; bicubic; expanded canvas; white fill; post-rotation 1226×2085; LANCZOS; final 588×1001 at 144 DPI. Page metadata also preserves the fixture/source PDF page mapping and exact source-side rectangle. The top-level preprocessing metadata remains v1 with its established strict root contract so unchanged geometry accepts it; the new render/rotation/downsample provenance is carried in each page record and transform ledger.

## E. Baseline vs new pipeline

The control was freshly captured on unmodified `guh` (12 OCR calls, Tesseract 5.3.4); no old OCR capture was reused. Counts are ambiguous/unassigned. A/U are counts, not success statuses.

| side | angle | tokens before → after | lines before → after | ambiguous/unassigned before → after | slope before → after | tolerance before → after | gap before → after |
|---|---:|---:|---:|---:|---:|---:|---:|
| `relativity_pdf10_pp26-27.left` | -0.6 | 191 → 193 | 26 → 25 | 0/0 → 0/0 | 0.000 → 0.000 | 4 → 4 | 72.0 → 74.0 |
| `relativity_pdf10_pp26-27.right` | -1.9 | 263 → 255 | 62 → 36 | 0/1 → 0/0 | 0.000 → 0.000 | 4 → 4 | 78.0 → 76.0 |
| `relativity_pdf17_pp40-41.left` | 0.8 | 138 → 138 | 30 → 22 | 0/0 → 0/0 | 0.000 → 0.000 | 4 → 4 | 77.0 → 78.0 |
| `relativity_pdf17_pp40-41.right` | 0.0 | 305 → 304 | 32 → 32 | 0/0 → 0/0 | 0.000 → 0.000 | 4 → 4 | 66.0 → 68.0 |
| `relativity_pdf23_pp52-53.left` | 0.0 | 143 → 151 | 24 → 24 | 0/0 → 0/1 | 0.000 → 0.000 | 4 → 4 | 58.0 → 54.0 |
| `relativity_pdf23_pp52-53.right` | 0.0 | 226 → 228 | 32 → 30 | 0/0 → 0/0 | 0.000 → 0.000 | 4 → 4 | 68.0 → 68.0 |
| `stella_maris_pdf03_session-I.left` | unresolved / omitted | 385 → 307 | 101 → 85 | 4/6 → 0/4 | 0.000 → 0.000 | 6 → 5 | 108.0 → 118.0 |
| `stella_maris_pdf03_session-I.right` | 0.0 | 133 → 132 | 23 → 24 | 0/0 → 0/0 | 0.000 → 0.000 | 4 → 4 | 74.0 → 74.0 |
| `stella_maris_pdf06_dense-dialogue.left` | 0.0 | 255 → 255 | 42 → 41 | 0/0 → 0/0 | 0.000 → 0.000 | 4 → 4 | 72.0 → 72.0 |
| `stella_maris_pdf06_dense-dialogue.right` | 0.0 | 271 → 271 | 38 → 39 | 0/0 → 0/0 | 0.000 → 0.000 | 4 → 4 | 70.0 → 70.0 |
| `stella_maris_pdf18_session-II_p35.left` | unresolved / omitted | 68 → 67 | 23 → 22 | 0/0 → 0/0 | 0.000 → 0.000 | 4 → 4 | 84.0 → 84.0 |
| `stella_maris_pdf18_session-II_p35.right` | 0.0 | 132 → 132 | 33 → 33 | 0/0 → 0/0 | 0.000 → 0.000 | 4 → 4 | 81.0 → 81.0 |

Token-record and OCR TSV hashes are stored in `baseline.json` and `results.json`. The experimental run used fresh OCR for every emitted side and every angle variant; the runner records 15 calls.

## F. Known failures and safety controls

The visible Relativity 10 left row beginning “as observed from the embankment” unifies. The row beginning “the moving railway carriage, we should find that the” remains fragmented and is split into three candidate bands; this is an additional split relative to its already-fragmented control.

On Relativity 10 right, the prior 29-event crosswalk mostly reproduces, including the row around “to K, it is in a condition of uniform motion of translation.” The “If K is a Galileian co-ordinate system … then every other” physical row is not unified: high-resolution output separates it into three groups (`then other`, `If K … co-ordinate`, `system, every`). This reproduces the prior raster study’s `If K...` false-split context. The “affords an insufficient foundation for the physical” row is one group in the new run.

Relativity 17 left visibly unifies the reviewed embankment/consequence contexts. Headers and page numbers remain separate. The figure on that page remains spatially distinct from body rows. On Relativity 23, display math remains visually separated; however Relativity 23 left gains one unassigned token (`with`, box `[10,399,49,415]`) near the body text, so the grouping status is unresolved there.

Explicit 0° controls also show structural changes from the 300→144 render path. A Stella Maris 03 right short dialogue sentence (“I suppose. At the time I thought you were somebody else.”) is one visible printed row but becomes two geometry groups. Stella Maris 06 right splits the visible dialogue row “you hadn’t asked yourself.” Stella Maris 06 left repairs one row but further splits another continuous line beginning “century. Which you should…”. Stella Maris 18 left is unresolved-angle and left unchanged geometrically; its current new render path unifies “I missed you last week.” The blank Stella Maris 03 left remains excluded from correctness decisions.

## G. Complete changed-event ledger

`adjudications.json` contains 42 events based on exact OCR-text sequence alignment, with control/new source rows, boxes, group memberships, measurements, angle, and prior event crosswalk IDs. Classification counts:

- Repaired false splits: **30**
- Destructive merges: **0**
- New false splits: **5**
- Benign differences: **6** (including blank-side diagnostic changes and assignment-only changes)
- Unresolved: **1** (Relativity 23 left unassigned `with`)

The five new false-split events include the further-fragmented Relativity 10 left row, the Relativity 10 right `If K...` row, and three visible Stella Maris dialogue/body-row splits. OCR strings in the ledger are locators; visible scan structure is the adjudication authority.

## H. Prior-study crosswalk

The exact-text sequence crosswalk finds **28/29** raster-study repaired contexts unified. One Relativity 10 left row (the “the moving railway carriage…” context) is not retained. The frozen-coordinate study’s 30 repaired contexts yield **28/30** unified; the same Relativity 10 left context and the Relativity 10 right `If K...` context are not retained.

Both frozen-AABB false-split events disappear with OCR boxes freshly detected on the upright pixels: the “to K … uniform motion of translation” row and the “affords an insufficient foundation … physical” row are each grouped as one line. The old raster `If K...` regression does reappear, now as a three-group fragmentation. Seven of the eight historical slope-created false-split contexts remain correctly grouped: the `changes its position...`, heading, `velocities...`, and dialogue contexts listed in the prior study retain their visible row partitions except the Stella Maris 06 right “you hadn’t asked yourself” row, which is split. Production slope remains 0.0 on all sides.

## I. Relativity 10 right sensitivity

The same 300-DPI source render and exact crop were used for each variant; Tesseract was run once per final variant. All retain the same 20/20 R10-right repaired contexts and the `If K...` fragmentation. OCR count no longer collapses near −1.7°:

| correction | admitted tokens | physical lines | ambiguous/unassigned | TSV SHA-256 |
|---:|---:|---:|---:|---|
| -1.7° | 258 | 37 | 0/0 | baf8bcaf2bff71685ce9eddd0e072bdc3eb7216312db86c3824e33111d87cb34 |
| -1.9° | 255 | 36 | 0/0 | 76914019693438e653e0130e31af86952e62dad6123b2702d379cbcb062f4839 |
| -2.1° | 259 | 39 | 0/0 | 54d2a06f075b4f295a1d228d0cb1a7798cf02e0c747f20e0ed3ed8002a1827c5 |

The prior 144-DPI raster study had 98 tokens at −1.7° and 263 at −1.9°. Here the counts are 258, 255, and 259. Geometry changes modestly (37/36/39 bands), while OCR count remains stable. This removes the catastrophic token-count sensitivity, not the structural failures above.

## J. Controls

Measured-zero sides receive no page rotation resampling and have explicit `0.0` provenance. Unresolved sides have no configured value. Headers/page numbers and visible figures/display math are not destructively joined in the reviewed pages. Three new false splits on unrotated dialogue/body rows and the Relativity 23 left unassigned token mean the zero-angle render/downsample control is not fully structurally preserved.

Blank side diagnostics: Stella Maris 03 left admitted token count changes from 385 to 307; line count 101 to 85; ambiguous/unassigned changes 4/6 to 0/4. It remains excluded from the primary correctness decision and is still uncertain due unassigned observations.

## K. Verification

- Full suite baseline on `guh`: 188 passed, 1 skipped.
- Focused rotation tests: 13 passed. Focused crop and Slice 1 tests passed; focused Slice 2 geometry tests passed with `PYTHONPATH=.`.
- Full post-change suite: 201 passed, 1 skipped.
- Fixture preprocessing and fresh OCR: all six fixture runs; 12 page sides; 15 OCR calls including Relativity 10 right variants.
- Production geometry/OCR source diff: none.
- Tracked PNG/PDF check: empty; no tracked raster/PDF files.

## L. Decision

**high_resolution_rotation_still_causes_structural_regressions**

The coordinate correction improves many known rows and eliminates the earlier OCR-count cliff, but it fails the explicit no-new-false-splits and no-new-unresolved gates. The measured-zero render/downsample controls also introduce visible row fragmentation. This branch therefore does not support merge readiness.

## M. Commit

Commit SHA and worktree status are recorded in the final report after commit.
