# Human OCR-content crop ablation report

## Scope and authority

Starting commit: `2d7918efa63e89357fa4bc6239da1aadbe2ac367` (residual-forensics baseline). The experiment branch is `research/human-content-crop-ablation`. The four required historical commits were present locally. No production source was changed.

The human-cropped JPEG files are the input authority. Registration against the original spineless scans is descriptive provenance; it does not revise the crops. Human crop means a selected meaningful-content region, distinct from the earlier physical-sheet isolation crop.

## A. Provenance

All source scans are 2550×3300 RGB JPEGs with 300-DPI metadata. Human crops are RGB JPEGs, also marked 300 DPI. Quantization-table fingerprints differ, and pixel registration finds a same-resolution rectangular source correspondence with scale approximately 1 and no meaningful crop rotation. The decoded arrays are not exact subsets: mean absolute RGB differences range from 2.586 to 3.099 and only 2.68–5.23% of pixels match exactly. This is consistent with lossy JPEG recompression. Thus the comparison changes both page context and JPEG encoding; it is not a pure pixel-subset crop ablation.

| Page | Source SHA-256 | Human crop dimensions | Human crop SHA-256 | Matched source rectangle `[x0,y0,x1,y1]` | RGB MAE |
|---:|---|---:|---|---|---:|
| 26 | `b4b2d113fcbc7dab2413d2be59dd36ac421c93d6117a6c37376b1ab591f5bd4c` | 1109×1692 | `e73c0c32e8241fc820636e703a6572622cdf791a64e8a8e8ec98ee17a132ff5a` | `[146,468,1255,2160]` | 3.006 |
| 27 | `d2ca32d3924df8f2e41db6f0d12bf387bb127aed405b9aead7759a297018b490` | 1150×2029 | `7df38dcb7c8c8e094c8782072c0cf7c9a25db4dc4c63038a7df70ee3f0e466a8` | `[204,86,1354,2115]` | 3.099 |
| 40 | `0d25da3c0b35e5c0574d23248318481dec55ea6e7e721db7b194a67b04a769f1` | 1111×1612 | `a543675cc669196cc9069d205854436a911caf4288342aa03deb353305653e37` | `[134,557,1245,2169]` | 2.698 |
| 41 | `e80da7cc823ef53e6cb720a3d8d3c6d440dbcdf018dedb9c0e052de6d29d5176` | 1124×2045 | `9fb3430f0b2b0902bcafbcc5e5d390d519611f49e1b1ead3978f1a91797f4a75` | `[213,145,1337,2190]` | 2.836 |
| 52 | `f3af85dce13de9101466ddb914900b51c9b142397b0c608192dbebb4c223f914` | 1106×1693 | `5937862cd723013f11d49bbe3c581e40ccf9dba110f9df7916eedf228ece3b76` | `[173,473,1279,2166]` | 2.586 |
| 53 | `7847e79c14f6497eb50ab70af241543a97b00af11176e99cbb431e82141dc565` | 1108×2028 | `81330978798cbb7d5cf664bb65d6e35ff29cee839f7508f05a6fc3520ba35b47` | `[177,159,1285,2187]` | 2.743 |

The full EXIF/JPEG metadata and registration measurements are in `results.json`. No crop was further trimmed. Visual review found all target rows retained, plus p40's figure/labels, p52's displayed math, surrounding prose, headings, and visible page furniture. No requested target row was clipped.

## B. Crop sanity and C. orientation

Corrections below were independently measured from the manual crop pixels with the prior dark-pixel horizontal-projection method, using three regions. Prior physical-sheet angles are shown for comparison only. Pillow bicubic rotation with `expand=True` and white fill was followed by LANCZOS resize at 144/300, dimensions rounded half-up. No contrast or color operation was applied.

| Page | Regional correction estimates | Applied | Prior angle | Range | Final raster |
|---:|---|---:|---:|---:|---:|
| 26 | +0.46°, +0.48°, +0.50° | +0.48° | +0.44° | 0.04° | 540×817 |
| 27 | −1.02°, −0.92°, −0.90° | −0.92° | −0.94° | 0.12° | 568×984 |
| 40 | +0.82°, +1.44°, +0.90° | +0.90° | +0.86° | 0.62° | 546×782 |
| 41 | −0.86°, −0.80°, −0.74° | −0.80° | −0.80° | 0.12° | 554×989 |
| 52 | +0.74°, +0.74°, +0.88° | +0.74° | +0.74° | 0.14° | 541×820 |
| 53 | −0.44°, −0.38°, −0.34° | −0.38° | −0.38° | 0.10° | 539×977 |

Page 40 has one regional outlier at +1.44°; the two other regions agree at +0.82° and +0.90°, and their median is close to the earlier +0.86° estimate. The three estimates support using one page-level correction for this diagnostic, with greater regional disagreement than on the other pages.

## D. OCR comparison

Primary OCR was Tesseract 5.3.4, `eng`, `--psm 6`. Raw TSV was captured before the production parser. Every raw nonempty word row on these pages was admitted; there were no ambiguous or unassigned geometry tokens. The following compares the exact-hash reproduced physical-sheet capture against the human crop. Confidence is median admitted word confidence. `A/U` means ambiguous/unassigned.

| Page | Physical-sheet tokens | Human-crop tokens | Median confidence, sheet → human | Lines, sheet → human | A/U, sheet → human | Human slope / tol / gap |
|---:|---:|---:|---:|---:|---:|---|
| 26 | 202 | 191 | 96.461 → 96.546 | 36 → 23 | 0/0 → 0/0 | 0 / 4 / 74 |
| 27 | 264 | 262 | 96.420 → 96.461 | 46 → 40 | 0/0 → 0/0 | 0 / 4 / 78 |
| 40 | 139 | 138 | 96.628 → 96.711 | 23 → 22 | 0/0 → 0/0 | 0 / 4 / 77 |
| 41 | 307 | 305 | 96.491 → 96.461 | 34 → 32 | 0/0 → 0/0 | 0 / 4 / 68 |
| 52 | 148 | 144 | 96.344 → 96.544 | 26 → 21 | 0/0 → 0/0 | 0 / 4 / 58 |
| 53 | 221 | 231 | 96.372 → 96.471 | 33 → 32 | 0/0 → 0/0 | 0 / 4 / 68 |

The smaller line count is not treated as proof of improvement. The physical-row oracle supports the prose comparison below. Token counts changed in both directions (p53 gains ten admitted observations), and median confidence changes are small. Human-crop raw TSV hashes and final-raster hashes are recorded in `results.json`; the reproduced sheet TSV hashes match the archived study exactly.

## E. Page-27 context failure

The physical-sheet full-page raster emitted the malformed giant word record `See`, approximately `[7,640,624,696]` with confidence 14.663, spanning several visible physical rows, plus a small `ae` record. In the human-content crop's raw TSV there is no giant `See` observation. The target row instead has seven level-5 word records, all admitted:

| Locator | Box `[x0,y0,x1,y1]` | Confidence |
|---|---|---:|
| affords | `[15,624,90,654]` | 87.001 |
| an | `[102,624,125,654]` | 63.216 |
| insufficient | `[211,628,214,630]` | 63.216 |
| foundation | `[332,628,335,630]` | 94.245 |
| for | `[375,624,408,654]` | 95.778 |
| the | `[420,624,453,654]` | 79.022 |
| physical | `[525,628,539,643]` | 79.022 |

The observation is **partial usable geometry**, not normal geometry: `insufficient` and `foundation` have 3×2 px boxes; `physical` is only 14×15 px. All seven records pass the unchanged admission parser because they are nonempty with positive in-bounds boxes. Downstream they occupy four physical-line outputs: `affords/an`, `insufficient`, `foundation`, and `for/the/physical`. The human crop removes the known multirow merge but does not recover complete usable word geometry. Prior same-pixels context study found a tighter crop could recover ordinary boxes, but this experiment did not tighten the human crop. JPEG recompression also differs, so the remaining tiny boxes cannot be attributed solely to excluded context.

**Page-27 OCR-context conclusion: `human_content_crop_reduces_but_does_not_eliminate_context_failure`.**

## F. Three vertical residuals

The same unchanged geometry uses slope 0 and tolerance 4 px on each page.

### Page 26: `changes … embankment yet`

The human crop produces one line containing source rows 65–72 (`changes`, `its`, `position`, `relative`, `to`, `the`, `embankment`, `yet`). Before `yet`, the running center median is 382.5; `yet.center_y=386.5`, exactly 4 px away, so the inclusive `<=4` predicate succeeds. The preceding horizontal gap is 14 px, within the 74 px gap limit. This repairs the physical-sheet split, where `yet` was at 612.0 versus median 607.5 (4.5 px > 4). Here the crop/resampling changes observed boxes enough to cross the existing boundary; no geometry rule changed.

### Page 27: `If K … every other`

The same false split remains. `system,` has center y=129.0 versus the running median 124.0, a 5 px difference greater than tolerance 4, with no qualifying neighbor support. It starts a separate vertical band; later horizontal grouping places `If K is a Galileian co-ordinate then other` and `system, every` in separate candidates. The physical-sheet trace was 171.5 versus 167.0 (4.5 > 4), so the same first-divergence mechanism persists and the human crop's relevant center offset is slightly larger.

### Page 53: `and for still greater velocities the square-root becomes`

The same first divergence remains: `greater.center_y=430.5`, running median 425.5, difference 5.0 > 4 with no neighbor support. The vertical separation then interacts with the existing 68 px horizontal gap bound. The final five groups are `and for still`, `greater`, `velocities the`, `square-root`, `becomes`. The physical-sheet trace was 507.5 versus 502.0 (5.5 > 4). Thus this crop retains the vertical-band failure and has more downstream bands than the earlier three-group bound result. Nearby display math is preserved; this study supplies no evidence that math boxes caused the target row's initial vertical split.

## G. 105-row corpus result

The 105-row oracle is the visible-pixel row inventory from the accepted vertical-anchor study, not production membership. Pixel registration maps each page oracle into the rotated human raster. Results:

| Page | Oracle prose rows | Correct single line | False split | Destructive merge | Unresolved |
|---:|---:|---:|---:|---:|---:|
| 26 | 19 | 19 | 0 | 0 | 0 |
| 27 | 20 | 19 | 1 | 0 | 0 |
| 40 | 13 | 13 | 0 | 0 | 0 |
| 41 | 30 | 30 | 0 | 0 | 0 |
| 52 | 10 | 10 | 0 | 0 | 0 |
| 53 | 13 | 12 | 1 | 0 | 0 |
| **Total** | **105** | **103** | **2** | **0** | **0** |

Physical-sheet production classified 87 correct and 18 false splits on the same oracle. Crosswalk: 87 rows were correct in both, 16 physical-sheet false splits became correct, and two remained split (p27 `If K…`, p53 `greater…`). No new prose false split or destructive merge appeared in the mapped 105 rows. Mapping uses pixel registration and source provenance, not OCR strings as the identity authority.

## H. Bound → physical-sheet → human-crop crosswalk

- **Page 26 `…embankment yet`:** bound output was one physical row; physical-sheet scan split before `yet`; human crop returns one line. The residual is introduced in the physical-sheet OCR geometry and does not survive this crop surface.
- **Page 27 `If K…`:** fragmented in bound and physical-sheet captures; still fragmented in the human crop, with the same vertical-band first divergence. This is a residual geometry failure after content cropping.
- **Page 27 `affords…physical`:** bound OCR had usable geometry; physical-sheet full-page OCR emitted the giant `See` multirow box and `ae`; human crop removes the giant box but yields several tiny target boxes and four groups. The contextual raw-OCR failure changes, but usable target geometry is still incomplete.
- **Page 53 `…greater…becomes`:** fragmented in bound, more fragmented in physical-sheet, and remains five groups under human crop. The same vertical-band-first split remains, with downstream gaps adding fragmentation.

These observations distinguish an acquisition/context-sensitive failure (p26 and the giant p27 box) from residual grouping/box cases (p27 `If K`, p53). They do not isolate crop-boundary effects from JPEG recompression or changed resampling completely.

## I. Structural controls

Visual review confirms page 40's diagram, labels, and caption remain inside the crop. OCR retains spatially distinct figure-region records (including `M`, `v`, `Train`, `Embankment`, `A`, `B`, and the caption), separate from body rows. Page 52 retains the displayed equations and surrounding prose; OCR represents math as localized fragments, and the row oracle intentionally excludes equation bands. Headings and visible page furniture on all pages remain in the manual images. The mapped prose corpus has zero destructive merges. This is evidence of retention/separation for these controls, not a general guarantee for arbitrary crops.

## J–L. Conclusions and workflow implication

**OCR context conclusion: `human_content_crop_reduces_but_does_not_eliminate_context_failure`.**

**Overall acquisition conclusion: `human_content_crop_is_supported_as_benchmark_oracle`.**

The human crop surface materially improves the mapped prose corpus (103/105 correct versus 87/105 for physical-sheet inputs), removes the p27 giant multirow `See`, and repairs p26's crop-associated split. Two known vertical residuals persist and p27's target `affords…` boxes remain partly malformed, so the crop is not itself a general repair. It is supported as a benchmark/calibration authority for the intended content boundary in this corpus. The evidence does not establish an automatic detector or authorize production crop behavior.

The defensible workflow implication is that human-calibrated content regions can serve as reference data between physical-page isolation and OCR when evaluating a future detector. The relation is empirically supported for these six pages; generalization beyond them remains untested.

## Protocol note

The first complete human-crop harness execution performed six OCR calls but failed after capture when serializing JPEG metadata containing `bytes`; no first-attempt TSV was saved. After fixing JSON-safe metadata serialization, the same six page/config pairs were run again and captured successfully. Therefore this task actually invoked Tesseract 12 times on the human crops, although the saved primary dataset contains one successful capture per page. The input pixels, OCR arguments, and settings did not change between attempts. This departs from the requested one-primary-invocation protocol and is disclosed rather than hidden. A separate six-call physical-sheet reproduction matched all six archived TSV hashes exactly.

## M. Verification

The harness uses current production OCR parsing and geometry imports without patching them. Research tests, relevant geometry/preprocessing tests, the prior residual-forensics tests, and the full suite are recorded in the final task report. Production source diff is empty. No image/PDF artifacts are committed; local source and manual JPGs remain untracked fixture inputs.
