# Spineless vertical-anchor representation study

## Question and boundary

This study asks whether an admitted Tesseract box's lower edge (`y1`) is a better vertical observable than its center (`center_y`) for physical-row membership on flat, deskewed pages. It holds each saved OCR observation fixed. It does not rerun OCR, alter production, or select a new tolerance.

The primary replay uses production's 4 px tolerance and saved page slope `0.0`. Its vertical order is `(anchor, x, source_row)`. The shadow implementation repeats the production running median, horizontal-neighbor test, cumulative horizontal region split, candidate generation, and assignment. Only the vertical anchor changes. The center replay reproduces the saved production token partitions for all six pages before any `y1` results are accepted.

## A. Frozen corpus and pixel oracle

The source JPG hashes, reconstructed final-raster pixel hashes, and saved TSV hashes match the prior spineless study on all six pages. OCR was not rerun. The fixed admitted token counts are 202, 264, 139, 307, 148, and 221. The primary pixel oracle contains 105 visually adjudicated prose rows and 1,055 admitted token boxes:

| Page | Adjudicated prose rows | Included token boxes | All admitted tokens |
|---:|---:|---:|---:|
| 26 | 19 | 189 | 202 |
| 27 | 20 | 188 | 264 |
| 40 | 13 | 123 | 139 |
| 41 | 30 | 299 | 307 |
| 52 | 10 | 116 | 148 |
| 53 | 13 | 140 | 221 |

The oracle rows come from horizontal ink bands in the verified rasters, then were checked visually against the page pixels. Existing Normalize line assignments and Tesseract line IDs did not establish the oracle. Titles, page furniture, page 40's diagram, display math, and the recorded malformed multi-row OCR regions are held out from the prose oracle. The exact pixel bands, exclusions, source rows, and token boxes are in [row-oracle.json](row-oracle.json) and [anchor-comparison.json](anchor-comparison.json).

## B. Within-row observables

The identity `y1 = center_y + height/2` holds exactly for the integer-coordinate boxes. Across 105 rows:

| Measure | `center_y` median / mean | `y1` median / mean | Rows where `y1` is lower / equal / higher |
|---|---:|---:|---:|
| Within-row range | 3.5 / 4.53 px | 6 / 7.53 px | 5 / 7 / 93 |
| Median absolute deviation | 0.5 / 0.55 px | 0 / 0.39 px | 49 / 37 / 19 |
| Maximum absolute deviation from row median | 3 / 3.65 px | 6 / 6.55 px | 5 / 3 / 97 |

`y1` often lowers the median absolute deviation, but it expands the full row range and the largest token deviation for most rows. The medians alone conceal outliers that control the running-band predicate.

## C. Adjacent-row separation

Across 95 adjacent prose-row pairs within the same text blocks, neither anchor's observed ranges overlap. The median-to-median separation is 28.5 px for both. `y1` has less margin: its median signed range separation is 22 px versus 25 px for centers, and its minimum is 2 px versus 14 px. Thus `y1` preserves ordering in these measured pairs but does not improve their separation. The 2 px minimum is inside the fixed 4 px band tolerance, leaving a threshold-sensitive boundary even without literal range overlap.

## D. Shadow grouping results

The principal comparison is immediately after vertical-band construction:

| Anchor | Correct single band | False split | Destructive merge with another oracle row | Unresolved |
|---|---:|---:|---:|---:|
| `center_y` | 93 | 12 | 0 | 0 |
| `y1` | 8 | 91 | 6 | 0 |

No center-based vertical false split was repaired by `y1`. Of the 93 rows that are correct with `center_y`, `y1` changes 82 to a false split and 3 to a vertical-band merge. Three more `y1` merges affect rows already false-split under the center representation.

The later horizontal-region, candidate, and assignment replay makes the difference worse:

| Anchor | Correct final row | False split | Destructive merge | Unassigned row |
|---|---:|---:|---:|---:|
| `center_y` | 87 | 18 | 0 | 0 |
| `y1` | 8 | 96 | 0 | 1 |

The production partition sizes also grow sharply. Baseline line counts by page are `36, 46, 23, 34, 26, 33`; the `y1` replay produces `85, 94, 55, 107, 55, 83` candidate partitions. The `y1` final replay has no ambiguous assignments, but leaves source row 66 on page 26 and source row 106 on page 27 unassigned. The page-26 unassigned identity belongs to an oracle prose row.

Per-page final physical-row classifications (`correct / false split / unresolved`) are:

| Page | `center_y` | `y1` |
|---:|---:|---:|
| 26 | 10 / 9 / 0 | 0 / 18 / 1 |
| 27 | 14 / 6 / 0 | 3 / 17 / 0 |
| 40 | 13 / 0 / 0 | 1 / 12 / 0 |
| 41 | 28 / 2 / 0 | 2 / 28 / 0 |
| 52 | 10 / 0 / 0 | 1 / 9 / 0 |
| 53 | 12 / 1 / 0 | 1 / 12 / 0 |

## E. Three known failures

The shadow reproduces the reported center values and first band decisions. `neighbor_support_sources` is empty in all six target traces. The trace also records every within-tolerance token considered by the neighbor predicate and its actual x gap.

### Page 26 — `yet`, source row 76

The target box is `[573,604,599,620]`, height 16. With centers, `612.0` differs from the running median `607.5` by `4.5 > 4`, and starts a new band. Nearby tokens are vertically within tolerance, but their x gaps are 420, 188, and 298 px, all greater than the unchanged 66 px gap limit, so horizontal-neighbor support is false.

With `y1`, the target is `620`, equal to the current band median `620`, and it joins a partial band. The final vertical band is `[69,71,76]`, not the full physical row. Horizontal splitting then produces `[69,71]` and `[76]`: source 71 ends at x=275, source 76 starts at x=573, so the evaluated gap is 298 px, above the 66 px limit. The visible row remains split. The printed row's complete center grouping was `[69–75]`, `[76]`, and the punctuation box `[77]`; the `y1` result fragments it into still more final lines: `[69,71]`, `[70]`, `[72–75]`, `[76]`, `[77]`.

### Page 27 — `system,`, source row 37

The box is `[425,163,489,180]`, height 17. The center `171.5` is `4.5 px` from median `167.0`. Under `y1`, the anchor is `180`, the running median is `175`, and the difference is `5 px > 4`. No current-band token is within 4 px, so neighbor support is not evaluated. It starts a new band. In both variants the physical row remains divided into `[32,33,34,35,36,38,40]` and `[37,39]`.

### Page 53 — `greater`, source row 111

The box is `[220,499,280,516]`, height 17. The center `507.5` differs from median `502.0` by `5.5 px`; the lower edge `516` differs from its running median `510` by `6 px`. Both fail median support and have no within-tolerance neighbor. Both produce the same target band `[111,114]` (`greater` and `square-root`), while the rest of the visible physical row remains in other bands. The display equation above is not participating: the closest pre-target equation box is at least 40 px away under `y1`, well outside tolerance.

## F. Complete new-harm inventory and matched controls

Identity-level transitions include source rows, pixel regions, boxes, and memberships in both vertical bands and final lines in `anchor-comparison.json`. The 82 center-correct rows that become `y1` vertical false splits are:

- Page 26: `p26-r002`, `r004`, `r005`, `r009`, `r012`–`r017`.
- Page 27: `p27-r004`–`r006`, `r011`–`r020`.
- Page 40: `p40-r001`–`r011`, `r013`.
- Page 41: `p41-r001`–`r006`, `r008`–`r016`, `r018`–`r025`, `r027`–`r030`.
- Page 52: `p52-r002`–`r010`.
- Page 53: `p53-r001`–`r006`, `r008`, `r010`–`r013`.

Three previously center-correct rows merge with their immediate neighbor at the `y1` vertical-band stage:

| Merged physical rows | Shared `y1` vertical-band source rows |
|---|---|
| Page 26 `p26-r007` (ink y 628–643) + `p26-r008` (y 656–675) | 80, 82, 87, 102 |
| Page 26 `p26-r010` (y 713–730) + `p26-r011` (y 742–761) | 115, 116, 123, 137 |
| Page 26 `p26-r018` (y 940–955) + `p26-r019` (y 969–988) | 210, 212, 213, 214, 215, 226 |

Later x-region splitting separates those particular rows again, so final destructive-merge count is zero. The intermediate merge is still a real failure of vertical band construction; it co-locates distinct printed rows and contributes to the observed fragmentation.

Matched pixel controls near the target rows:

| Target | Nearby physical controls | Center result | `y1` result | Observable difference |
|---|---|---|---|---|
| Page 26 target `p26-r006` | `r005`, `r007` | Both correct | `r005` unassigned; `r007` split/merged with `r008` | Control row 5 has center range 3 px but `y1` range 10 px; row 7's center range is 2.5 px and `y1` range 9 px. The bottom edge adds height-driven spread even in successful local controls. |
| Page 27 target `p27-r003` | `r002`, `r004` | Both correct | `r002` correct; `r004` false-split | Row 4's height range is 10 px; center range 5 px and `y1` range 5 px. Identical range does not imply identical running-median processing order. |
| Page 53 target `p53-r007` | `r005`, `r006` | Both correct | Both false-split | Their centers remain compact (3–4 px range) while lower-edge ranges are 6–9 px. Their OCR boxes are heights 7–21 px, so bottom movement tracks box height variation. |

There are no rows where `center_y` is false-split and `y1` yields a correct single band. The entire transition ledger is in the JSON artifact; no OCR wording was used as classifier input.

## G. Height relationship

The lower edge is not an independent baseline observation: it equals center plus half the observed box height. In the 79 rows that are final-correct under center but harmed under `y1`, median height is 16 px and median within-row height range is 11 px. Their median anchor ranges are 3.5 px (`center_y`) and 6 px (`y1`). In the eight rows correct under both final variants, median height range is 7.5 px and median anchor ranges are 3 px and 4.5 px.

The direct evidence supports height variation as a mechanism for the increased `y1` range. It does not establish that either box edge is a typographic baseline. The lower median absolute deviation of `y1` in many rows coexists with more extreme outliers and more grouping failures.

## H. Processing-order sensitivity

With physical x-order in place of production's anchor-sorted order, all 105 rows split at the vertical stage under both anchors. Final x-order results are 100 false splits plus 5 unassigned rows for center and 101 false splits plus 4 unassigned for `y1`. Relative to production order, final row classifications change for 88 center rows and 13 `y1` rows. This diagnostic shows that the last-band running algorithm depends on its sort order for either anchor; it does not rescue `y1`. Production order remains the primary comparison.

## I. Perturbation and synthetic controls

Uniformly shifting every box by `−1 px` or `+1 px` leaves both anchor partitions unchanged, as expected for translation-invariant distance predicates. More revealingly, a deterministic seed-7301 perturbation independently shifts each box by exactly `−1` or `+1 px`:

- Center: pairwise token co-memberships change by 260 across the corpus; 9 oracle-row labels change.
- `y1`: pairwise co-memberships change by 1,436; 30 oracle-row labels change.

No target failure is repaired by the perturbed `y1` runs. The page 27 target can join through neighbor support in one jittered center case, but the target physical row remains fragmented. The page 53 target can join a partial band under jitter, also without repairing the full row. This is a threshold/order cliff, not robust bottom-edge cohesion.

Synthetic boxes show both anchors' assumptions can fail under the unchanged 4 px rule:

| Control | `center_y` | `y1` |
|---|---|---|
| One row, equal bottoms, varied heights | Splits into 3 bands | One band |
| One row, equal centers, varied heights | One band | Splits into 3 bands |
| Two adjacent equal-height rows | Correctly distinct | Correctly distinct |
| Two rows with strongly varied heights | Correct under centers | Splits into 6 bands |
| One row with a tall descender-like box | One band | Outlier separates |
| Two close rows with nearly overlapping bottoms | Correctly distinct | Merges both rows |

These are falsification controls, not threshold or anchor tuning. Full memberships are recorded in the JSON.

## J. Decision

**`bottom_edge_is_not_supported`**

The lower edge reduces median absolute deviation for many rows, but the pixel-row corpus and exact production replay reject it as a better grouping observable at the unchanged tolerance. It repairs none of the three known failures, turns most previously correct rows into splits, merges six distinct-row pairs during vertical construction, and is substantially more sensitive to independent 1 px token-coordinate perturbations.

## K. Candidate future question

The smallest follow-up question supported by these measurements is whether any height-normalized vertical observable can retain the lower within-row median deviation of `y1` without reproducing its height-range splits and close-row merges. This study does not establish that such an observable exists.

## L. Verification

- Focused anchor tests: passed, including pixel/TSV/source hash checks, no-OCR guard, center-control replay, target traces, identity-complete transitions, synthetic controls, and binary checks.
- Prior spineless residual tests: passed.
- Relevant production geometry tests (`test_slice2`, vertical-stage ablation, horizontal-region regressions): passed.
- Full repository suite: passed.
- Production geometry/preprocessing/OCR source diff: none.
- Tracked `.jpg`, `.jpeg`, `.png`, or `.pdf` check: empty.
- The local `fixtures/einstein/spineless/` JPG directory remains untracked and unstaged.
- Branch and commit details are reported in the final task summary.
