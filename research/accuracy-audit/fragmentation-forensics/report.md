# Slice 2 fragmentation and page-edge causal forensics

## A. Executive result

Baseline: branch `research/accuracy-audit`, fetched origin tip and local `HEAD` both `f55ab640db98a48767c612464579c66d5b1a1c1f`; starting working tree was clean. Corpus: six fixtures, 11 nonblank page sides, 2,219 admitted tokens, 522 physical lines, seven residual tokens. Tesseract was run with the recorded English `--psm 6` TSV configuration. Geometry calls in the experiment delegate to the unchanged production functions.

| Mechanism | Result | Evidence |
|---|---|---|
| Vertical / skew fragmentation | **Partially causal.** | The slope search finds nonzero candidates with higher cohesion on nine pages, but its all-bands-must-have-two-tokens gate rejects every such candidate. Forcing the unconstrained best slope repairs the Relativity 10 right control, but damages one clean control and changes many other groups. |
| Oversized bridge guard | **Confirmed causal.** | The trace records 60 horizontal splits where the immediately preceding token is oversized and unsupported. This includes the Relativity 10 left three-fragment row and the Relativity 17 right `conclusion` split. A 4-median threshold repairs both without damaging the three selected clean controls; it still creates 42 many-to-one line merges across the corpus. |
| Page-edge / gutter OCR noise | **Partially causal.** | Pixel boundaries coincide with 73 OCR boxes on the four visually flagged pages; 70 production lines consist solely of those edge-aligned tokens. Removing the tokens changes page gap statistics and re-OCR changes geometry, but also changes body OCR and leaves more residuals overall. A general production crop is not established as safe. |

The three known human false-split controls are all repaired together only in the forced-slope plus disabled-guard factorial setting. That setting creates 83 merges of baseline line groups and damages one clean control. This is a bounded set of positive controls, not an accuracy percentage or a corpus-wide oracle.

## B. Human-observed failures and first separating predicate

| Observation | First evidenced separator | Finding |
|---|---|---|
| Relativity 10 left, `line-0017`–`line-0019` appear as right/middle/left fragments | `oversized_bridge_guard` | All six tokens are in one initial vertical band. `token-0068` (`and-direction,`, 122 px) and `token-0069` (115 px) exceed the 99 px threshold. Their actual next-token gaps are 7 px and 6 px; stale covered gaps are 129 px and 250 px, both above the 66 px limit. The guard, not vertical tolerance, creates the fragments. The line IDs are assigned by adjusted Y then X, so this fragmentation also produces the reported apparent reading-direction reversal. |
| Relativity 10 right, `line-0053`–`line-0055` plus residual `impossible` | `baseline_slope_model` | The best unconstrained slope is −0.043 with cohesion 1,093 versus 638 at zero. Forcing it at the current 4 px tolerance rejoins the reviewer-defined visible row and uniquely assigns `token-0246`. Production rejects the slope because its candidate has six singleton bands. Raising tolerance to 8 px also reunites the row, but reduces this page from 72 to 40 lines and contributes to corpus-wide merges. |
| Relativity 17 right, `line-0061`–`line-0062` | `oversized_bridge_guard` | All ten tokens have median Y 926.5 and are in one vertical band. `conclusion` is 95 px wide, over the 90 px threshold; the next token `that` starts 6 px after it. Since `conclusion` does not extend `covered_right`, the next token is 108 px from the stale extent, exceeding the 60 px limit. It is not a supported bridge because its box ends at x=336 and `that` starts at x=342. |
| Stella Maris 06 left, line visually between geometry lines 27 and 28 | `ocr_observation_missing` | Baseline raw Tesseract TSV emits no word rows for the visible row around y=868. It is absent before admission/grouping; geometry cannot reconstruct OCR tokens that were never emitted. Baseline also emits a 312×24 px `Something` box. The automatic edge-mask rerun emits the row’s 11 words, while uniform 2% crop does not; this is a treatment effect on Tesseract output, not evidence that highlighting caused the omission. |

For the Stella page, neighboring baseline OCR boxes are 37–43 px high versus the usual ~15–22 px boxes on the page. The omitted y≈868 row is absent from TSV; the oversized boxes on recognized neighboring rows are a separate OCR-box geometry problem.

## C. Vertical and skew analysis

Every current page selects slope 0. The estimator does evaluate nonzero slopes, then rejects them unless every resulting band has at least two tokens. Cohesion is a pair-count heuristic; a higher score is evidence the coordinate grouping changes, not proof that the slope matches physical baselines.

| Page side | Zero-slope cohesion | Best nonzero unconstrained (slope / score) | Singleton bands at that candidate | Decision |
|---|---:|---:|---:|---|
| relativity_pdf10_pp26-27 / left | 587 | -0.018 / 646 | 21 | rejected: fewer_than_two_bands_or_singleton_band |
| relativity_pdf10_pp26-27 / right | 638 | -0.043 / 1093 | 6 | rejected: fewer_than_two_bands_or_singleton_band |
| relativity_pdf17_pp40-41 / left | 415 | +0.009 / 504 | 10 | rejected: fewer_than_two_bands_or_singleton_band |
| relativity_pdf17_pp40-41 / right | 1201 | +0.000 / 1201 | 26 | no improving nonzero candidate |
| relativity_pdf23_pp52-53 / left | 512 | +0.014 / 513 | 19 | rejected: fewer_than_two_bands_or_singleton_band |
| relativity_pdf23_pp52-53 / right | 927 | -0.018 / 953 | 40 | rejected: fewer_than_two_bands_or_singleton_band |
| stella_maris_pdf03_session-I / right | 466 | -0.011 / 480 | 4 | rejected: fewer_than_two_bands_or_singleton_band |
| stella_maris_pdf06_dense-dialogue / left | 837 | -0.005 / 892 | 9 | rejected: fewer_than_two_bands_or_singleton_band |
| stella_maris_pdf06_dense-dialogue / right | 1224 | +0.000 / 1224 | 11 | no improving nonzero candidate |
| stella_maris_pdf18_session-II_p35 / left | 134 | -0.014 / 144 | 9 | rejected: fewer_than_two_bands_or_singleton_band |
| stella_maris_pdf18_session-II_p35 / right | 308 | +0.005 / 316 | 12 | rejected: fewer_than_two_bands_or_singleton_band |

Nine pages have a nonzero candidate with improved cohesion, but its singleton bands fail the gate. The other two pages (Relativity 17 right and Stella Maris 06 right) have no improving nonzero candidate. The stored results include all 201 candidate slopes per page, with band counts and acceptance/rejection reasons.

The selected slope/tolerance alternatives produce these corpus totals:

| Tolerance | Lines | Residuals | Known split controls repaired | Selected clean controls damaged | Suspicious cross-region merges |
|---:|---:|---:|---:|---:|---:|
| 2 | 865 | 21 | 0 | 2 | 0 |
| 4 | 522 | 7 | 0 | 0 | 0 |
| 6 | 458 | 6 | 0 | 1 | 1 |
| 8 | 447 | 5 | 1 | 1 | 1 |
| 10 | 439 | 6 | 1 | 1 | 2 |

Tolerance 8 repairs the Relativity 10 right row, but the same page row is repaired at tolerance 4 by a forced slope. Relativity 10 left and Relativity 17 right do not repair by tolerance increases through 10. The clean control `relativity_pdf17_pp40-41/left line-0029` is damaged by forced-slope and tolerance 6–10 variants. The evidence points to a missed slope candidate plus a conservative support gate on Relativity 10 right, while the other two named false splits are horizontal-guard failures. Increasing global tolerance is not a sufficient or low-collateral explanation.

## D. Oversized-token and horizontal-gap analysis

The unchanged production predicate is `token.width > gap_limit + gap_limit / 2`; because the gap is twice median token width, this is a strict `width > 3 × median_width` test. Across the 11 pages, 85 tokens are classified oversized. The selected-band trace contains 60 split events attributed to an unsupported oversized predecessor and 38 other `token.x - covered_right > gap_limit` events. Those 38 may be legitimate column/region boundaries; the count is not a false-split count.

| Guard | Corpus lines | Residuals | Known false-split controls repaired | New baseline-line merges | Suspicious merges | Clean controls damaged |
|---|---:|---:|---:|---:|---:|---:|
| Current (>3× median) | 522 | 7 | 0 | 0 | 0 | 0 |
| Alternative (>4× median) | 476 | 5 | 2 | 42 | 0 | 0 |
| Guard disabled | 464 | 1 | 2 | 51 | 1 | 0 |

The 4× alternative still classifies 19 of the 85 current oversized boxes. It repairs Relativity 10 left `line-0017`–`line-0019` and Relativity 17 right `line-0061`–`line-0062`, with no selected clean control damaged. Disabling the guard yields one suspicious merge on Relativity 10 left: baseline `line-0035`/`line-0036` are joined across a 159 px adjacent-box gap with a 66 px page gap limit. The 4× treatment is promising evidence, not a selected production replacement.

For the `conclusion` trace: median token width is 30 px; gap limit 60 px; current threshold 90 px; width 95 px. Current behavior keeps covered-right at x=234 after `the`, ignores `conclusion` ending at x=336, then sees `that` at x=342 as 108 px away. Under the 4× threshold (120 px), `conclusion` extends covered-right and the next gap is 6 px.

### Complete oversized-token inventory

All 85 tokens are listed below. `ordinary visible prose (pixel checked)` is reserved for `conclusion` and `Something`, which were inspected in the page raster. `likely prose locator` is based on the OCR text shape and body position; it is not independent pixel confirmation. Garbled strings remain undetermined. No oversized item is labeled non-text/noise without direct pixel evidence. “Extent?” records whether the guard withheld its right edge; “split after” is an actual traced production boundary. Full coordinate, width, median, threshold, confidence, support, and alternative-threshold fields also appear in `results.json`.

| Page / side | Token | bbox (x0,y0,x1,y1) | width / median / gap / threshold (px) | Extent? | Split after | Visual category |
|---|---|---|---|---|---|---|
| relativity_pdf10_pp26-27 / left | token-0014 `Principle` | `[247, 315, 362, 347]` | 115 / 33.0 / 66.0 / 99.0 | withheld | token-0015 (adjacent 11, covered 138) | likely prose locator not individually pixel confirmed |
| relativity_pdf10_pp26-27 / left | token-0016 `Relativity` | `[411, 314, 532, 344]` | 121 / 33.0 / 66.0 / 99.0 | withheld | — | likely prose locator not individually pixel confirmed |
| relativity_pdf10_pp26-27 / left | token-0021 `Restricted` | `[293, 350, 426, 376]` | 133 / 33.0 / 66.0 / 99.0 | withheld | token-0022 (adjacent 11, covered 156) | likely prose locator not individually pixel confirmed |
| relativity_pdf10_pp26-27 / left | token-0068 `and-direction,` | `[107, 579, 229, 597]` | 122 / 33.0 / 66.0 / 99.0 | withheld | token-0069 (adjacent 7, covered 129) | likely prose locator not individually pixel confirmed |
| relativity_pdf10_pp26-27 / left | token-0069 `“ttanislation’”` | `[236, 576, 351, 593]` | 115 / 33.0 / 66.0 / 99.0 | withheld | token-0070 (adjacent 6, covered 250) | not determinable from current pixel review |
| relativity_pdf10_pp26-27 / left | token-0081 `embankment` | `[466, 602, 582, 618]` | 116 / 33.0 / 66.0 / 99.0 | withheld | token-0082 (adjacent 16, covered 147) | likely prose locator not individually pixel confirmed |
| relativity_pdf10_pp26-27 / left | token-0085 `it-does*nor` | `[107, 636, 211, 653]` | 104 / 33.0 / 66.0 / 99.0 | withheld | token-0086 (adjacent 8, covered 112) | not determinable from current pixel review |
| relativity_pdf10_pp26-27 / left | token-0112 `embankment,` | `[276, 689, 435, 710]` | 159 / 33.0 / 66.0 / 99.0 | withheld | token-0113 (adjacent 10, covered 138) | likely prose locator not individually pixel confirmed |
| relativity_pdf10_pp26-27 / left | token-0119 `straightline.` | `[110, 721, 218, 742]` | 108 / 33.0 / 66.0 / 99.0 | withheld | token-0120 (adjacent 9, covered 117) | likely prose locator not individually pixel confirmed |
| relativity_pdf10_pp26-27 / left | token-0158 `still"be“uniform` | `[328, 801, 557, 819]` | 229 / 33.0 / 66.0 / 99.0 | withheld | — | not determinable from current pixel review |
| relativity_pdf10_pp26-27 / left | token-0191 `co-ordinate` | `[277, 889, 378, 906]` | 101 / 33.0 / 66.0 / 99.0 | withheld | token-0193 (adjacent 80, covered 181) | likely prose locator not individually pixel confirmed |
| relativity_pdf10_pp26-27 / left | token-0212 `co-ordinate` | `[185, 948, 286, 964]` | 101 / 33.0 / 66.0 / 99.0 | withheld | token-0213 (adjacent 11, covered 123) | likely prose locator not individually pixel confirmed |
| relativity_pdf10_pp26-27 / left | token-0215 `provided` | `[390, 943, 553, 966]` | 163 / 33.0 / 66.0 / 99.0 | withheld | token-0216 (adjacent -78, covered 91) | likely prose locator not individually pixel confirmed |
| relativity_pdf10_pp26-27 / left | token-0224 `translatory` | `[305, 968, 408, 1002]` | 103 / 33.0 / 66.0 / 99.0 | withheld | token-0225 (adjacent 6, covered 119) | likely prose locator not individually pixel confirmed |
| relativity_pdf10_pp26-27 / left | token-0225 `motion` | `[414, 972, 605, 992]` | 191 / 33.0 / 66.0 / 99.0 | withheld | token-0226 (adjacent -116, covered 194) | likely prose locator not individually pixel confirmed |
| relativity_pdf10_pp26-27 / right | token-0047 `when;in-telation` | `[372, 166, 520, 186]` | 148 / 38.0 / 76.0 / 114.0 | withheld | — | not determinable from current pixel review |
| relativity_pdf10_pp26-27 / right | token-0089 `generalisation` | `[403, 276, 525, 307]` | 122 / 38.0 / 76.0 / 114.0 | withheld | — | likely prose locator not individually pixel confirmed |
| relativity_pdf10_pp26-27 / right | token-0166 `representation` | `[281, 511, 405, 535]` | 124 / 38.0 / 76.0 / 114.0 | withheld | — | likely prose locator not individually pixel confirmed |
| relativity_pdf10_pp26-27 / right | token-0198 `electrodynamics` | `[292, 597, 433, 618]` | 141 / 38.0 / 76.0 / 114.0 | withheld | — | likely prose locator not individually pixel confirmed |
| relativity_pdf10_pp26-27 / right | token-0220 `description’of` | `[24, 690, 150, 713]` | 126 / 38.0 / 76.0 / 114.0 | withheld | — | likely prose locator not individually pixel confirmed |
| relativity_pdf10_pp26-27 / right | token-0221 `all’naturalphenomena.` | `[156, 686, 358, 707]` | 202 / 38.0 / 76.0 / 114.0 | withheld | — | likely prose locator not individually pixel confirmed |
| relativity_pdf10_pp26-27 / right | token-0261 `Nevertheless,` | `[65, 804, 183, 821]` | 118 / 38.0 / 76.0 / 114.0 | withheld | token-0262 (adjacent 9, covered 127) | likely prose locator not individually pixel confirmed |
| relativity_pdf17_pp40-41 / left | token-0006 `Relativity` | `[269, 340, 390, 373]` | 121 / 37.5 / 75.0 / 112.5 | withheld | token-0007 (adjacent 10, covered 143) | likely prose locator not individually pixel confirmed |
| relativity_pdf17_pp40-41 / left | token-0008 `Simultaneity` | `[438, 343, 606, 376]` | 168 / 37.5 / 75.0 / 112.5 | withheld | — | likely prose locator not individually pixel confirmed |
| relativity_pdf17_pp40-41 / left | token-0014 `considerations` | `[314, 452, 440, 468]` | 126 / 37.5 / 75.0 / 112.5 | withheld | token-0015 (adjacent 14, covered 153) | likely prose locator not individually pixel confirmed |
| relativity_pdf17_pp40-41 / left | token-0032 `embankment.”` | `[232, 507, 362, 524]` | 130 / 37.5 / 75.0 / 112.5 | withheld | token-0033 (adjacent 13, covered 156) | not determinable from current pixel review |
| relativity_pdf17_pp40-41 / left | token-0152 `embankment.` | `[204, 932, 323, 948]` | 119 / 37.5 / 75.0 / 112.5 | withheld | token-0153 (adjacent 11, covered 139) | likely prose locator not individually pixel confirmed |
| relativity_pdf17_pp40-41 / left | token-0156 `consequence,` | `[449, 941, 567, 957]` | 118 / 37.5 / 75.0 / 112.5 | withheld | token-0157 (adjacent 9, covered 127) | likely prose locator not individually pixel confirmed |
| relativity_pdf17_pp40-41 / right | token-0022 `lightning` | `[407, 122, 517, 142]` | 110 / 30.0 / 60.0 / 90.0 | withheld | token-0023 (adjacent -8, covered 105) | likely prose locator not individually pixel confirmed |
| relativity_pdf17_pp40-41 / right | token-0029 `simultaneous` | `[242, 151, 356, 166]` | 114 / 30.0 / 60.0 / 90.0 | withheld | token-0030 (adjacent 10, covered 134) | likely prose locator not individually pixel confirmed |
| relativity_pdf17_pp40-41 / right | token-0036 `embankment` | `[140, 179, 238, 195]` | 98 / 30.0 / 60.0 / 90.0 | withheld | token-0037 (adjacent 6, covered 112) | likely prose locator not individually pixel confirmed |
| relativity_pdf17_pp40-41 / right | token-0038 `simultaneous` | `[284, 179, 398, 194]` | 114 / 30.0 / 60.0 / 90.0 | withheld | token-0039 (adjacent 9, covered 130) | likely prose locator not individually pixel confirmed |
| relativity_pdf17_pp40-41 / right | token-0075 `simultaneous` | `[43, 322, 157, 337]` | 114 / 30.0 / 60.0 / 90.0 | withheld | token-0076 (adjacent 10, covered 124) | likely prose locator not individually pixel confirmed |
| relativity_pdf17_pp40-41 / right | token-0080 `embankment,` | `[341, 321, 461, 340]` | 120 / 30.0 / 60.0 / 90.0 | withheld | token-0081 (adjacent 9, covered 139) | likely prose locator not individually pixel confirmed |
| relativity_pdf17_pp40-41 / right | token-0118 `embankment.` | `[299, 406, 418, 422]` | 119 / 30.0 / 60.0 / 90.0 | withheld | token-0119 (adjacent 10, covered 137) | likely prose locator not individually pixel confirmed |
| relativity_pdf17_pp40-41 / right | token-0128 `correspond` | `[178, 435, 277, 456]` | 99 / 30.0 / 60.0 / 90.0 | withheld | token-0129 (adjacent 11, covered 122) | likely prose locator not individually pixel confirmed |
| relativity_pdf17_pp40-41 / right | token-0166 `embankment)` | `[131, 520, 252, 540]` | 121 / 30.0 / 60.0 / 90.0 | withheld | token-0167 (adjacent 10, covered 140) | likely prose locator not individually pixel confirmed |
| relativity_pdf17_pp40-41 / right | token-0221 `permanently` | `[447, 634, 556, 655]` | 109 / 30.0 / 60.0 / 90.0 | withheld | — | likely prose locator not individually pixel confirmed |
| relativity_pdf17_pp40-41 / right | token-0244 `simultaneously,` | `[286, 691, 420, 709]` | 134 / 30.0 / 60.0 / 90.0 | withheld | token-0245 (adjacent 9, covered 152) | likely prose locator not individually pixel confirmed |
| relativity_pdf17_pp40-41 / right | token-0259 `(considered` | `[456, 719, 555, 739]` | 99 / 30.0 / 60.0 / 90.0 | withheld | token-0260 (adjacent 90, covered 198) | not determinable from current pixel review |
| relativity_pdf17_pp40-41 / right | token-0267 `embankment)` | `[299, 748, 420, 768]` | 121 / 30.0 / 60.0 / 90.0 | withheld | token-0268 (adjacent 8, covered 136) | likely prose locator not individually pixel confirmed |
| relativity_pdf17_pp40-41 / right | token-0331 `reference-body` | `[372, 890, 504, 911]` | 132 / 30.0 / 60.0 / 90.0 | withheld | token-0332 (adjacent 10, covered 153) | likely prose locator not individually pixel confirmed |
| relativity_pdf17_pp40-41 / right | token-0339 `conclusion` | `[241, 919, 336, 934]` | 95 / 30.0 / 60.0 / 90.0 | withheld | token-0340 (adjacent 6, covered 108) | ordinary visible prose pixel confirmed |
| relativity_pdf23_pp52-53 / left | token-0006 `Behaviour` | `[251, 308, 386, 333]` | 135 / 27.0 / 54.0 / 81.0 | withheld | token-0007 (adjacent 10, covered 157) | likely prose locator not individually pixel confirmed |
| relativity_pdf23_pp52-53 / left | token-0008 `Measuring-Rods` | `[434, 311, 656, 343]` | 222 / 27.0 / 54.0 / 81.0 | withheld | — | likely prose locator not individually pixel confirmed |
| relativity_pdf23_pp52-53 / left | token-0011 `Clocks` | `[339, 345, 425, 370]` | 86 / 27.0 / 54.0 / 81.0 | withheld | token-0012 (adjacent 12, covered 110) | likely prose locator not individually pixel confirmed |
| relativity_pdf23_pp52-53 / left | token-0013 `Motion` | `[471, 347, 567, 371]` | 96 / 27.0 / 54.0 / 81.0 | withheld | — | likely prose locator not individually pixel confirmed |
| relativity_pdf23_pp52-53 / left | token-0017 `metre-rod` | `[233, 456, 320, 471]` | 87 / 27.0 / 54.0 / 81.0 | withheld | token-0018 (adjacent 6, covered 100) | likely prose locator not individually pixel confirmed |
| relativity_pdf23_pp52-53 / left | token-0031 `beginning)` | `[290, 484, 382, 506]` | 92 / 27.0 / 54.0 / 81.0 | withheld | token-0032 (adjacent 10, covered 111) | likely prose locator not individually pixel confirmed |
| relativity_pdf23_pp52-53 / left | token-0063 `metre-rod` | `[506, 543, 593, 559]` | 87 / 27.0 / 54.0 / 81.0 | withheld | token-0064 (adjacent 8, covered 102) | likely prose locator not individually pixel confirmed |
| relativity_pdf23_pp52-53 / left | token-0082 `beginning` | `[259, 597, 346, 619]` | 87 / 27.0 / 54.0 / 81.0 | withheld | token-0083 (adjacent 7, covered 101) | likely prose locator not individually pixel confirmed |
| relativity_pdf23_pp52-53 / left | token-0100 `particular` | `[359, 628, 442, 648]` | 83 / 27.0 / 54.0 / 81.0 | withheld | token-0101 (adjacent 7, covered 97) | likely prose locator not individually pixel confirmed |
| relativity_pdf23_pp52-53 / left | token-0117 `transformation` | `[546, 658, 677, 674]` | 131 / 27.0 / 54.0 / 81.0 | withheld | — | likely prose locator not individually pixel confirmed |
| relativity_pdf23_pp52-53 / left | token-0146 `(beginning` | `[273, 781, 398, 801]` | 125 / 27.0 / 54.0 / 81.0 | withheld | token-0147 (adjacent -39, covered 81) | not determinable from current pixel review |
| relativity_pdf23_pp52-53 / left | token-0158 `Xendofwd` | `[310, 870, 397, 912]` | 87 / 27.0 / 54.0 / 81.0 | withheld | token-0162 (adjacent 77, covered 164) | likely prose locator not individually pixel confirmed |
| relativity_pdf23_pp52-53 / right | token-0062 `l—v7/c?` | `[33, 293, 134, 321]` | 101 / 29.5 / 59.0 / 88.5 | withheld | token-0063 (adjacent 23, covered 124) | not determinable from current pixel review |
| relativity_pdf23_pp52-53 / right | token-0111 `J1-0?/c?` | `[209, 438, 319, 468]` | 110 / 29.5 / 59.0 / 88.5 | withheld | token-0112 (adjacent 18, covered 128) | not determinable from current pixel review |
| relativity_pdf23_pp52-53 / right | token-0123 `square-root` | `[358, 492, 456, 508]` | 98 / 29.5 / 59.0 / 88.5 | withheld | — | likely prose locator not individually pixel confirmed |
| relativity_pdf23_pp52-53 / right | token-0189 `transformation,` | `[112, 659, 248, 677]` | 136 / 29.5 / 59.0 / 88.5 | withheld | token-0190 (adjacent 9, covered 154) | likely prose locator not individually pixel confirmed |
| relativity_pdf23_pp52-53 / right | token-0192 `meaningless` | `[420, 657, 526, 678]` | 106 / 29.5 / 59.0 / 88.5 | withheld | token-0193 (adjacent 8, covered 122) | likely prose locator not individually pixel confirmed |
| relativity_pdf23_pp52-53 / right | token-0212 `considered` | `[318, 714, 412, 730]` | 94 / 29.5 / 59.0 / 88.5 | withheld | token-0213 (adjacent 8, covered 111) | likely prose locator not individually pixel confirmed |
| relativity_pdf23_pp52-53 / right | token-0263 `accordance` | `[235, 892, 333, 908]` | 98 / 29.5 / 59.0 / 88.5 | withheld | token-0264 (adjacent 14, covered 126) | likely prose locator not individually pixel confirmed |
| relativity_pdf23_pp52-53 / right | token-0277 `considerations.` | `[378, 920, 509, 935]` | 131 / 29.5 / 59.0 / 88.5 | withheld | — | likely prose locator not individually pixel confirmed |
| relativity_pdf23_pp52-53 / right | token-0294 `something` | `[36, 978, 128, 999]` | 92 / 29.5 / 59.0 / 88.5 | withheld | token-0295 (adjacent 11, covered 103) | likely prose locator not individually pixel confirmed |
| relativity_pdf23_pp52-53 / right | token-0300 `measuring-` | `[451, 982, 547, 997]` | 96 / 29.5 / 59.0 / 88.5 | withheld | — | likely prose locator not individually pixel confirmed |
| stella_maris_pdf06_dense-dialogue / left | token-0081 `mathematics.` | `[129, 366, 250, 383]` | 121 / 36.0 / 72.0 / 108.0 | withheld | — | likely prose locator not individually pixel confirmed |
| stella_maris_pdf06_dense-dialogue / left | token-0101 `mathematics?` | `[273, 464, 397, 480]` | 124 / 36.0 / 72.0 / 108.0 | withheld | — | likely prose locator not individually pixel confirmed |
| stella_maris_pdf06_dense-dialogue / left | token-0109 `disappointed` | `[144, 529, 260, 550]` | 116 / 36.0 / 72.0 / 108.0 | withheld | token-0110 (adjacent 7, covered 129) | likely prose locator not individually pixel confirmed |
| stella_maris_pdf06_dense-dialogue / left | token-0138 `disappointed` | `[159, 626, 276, 648]` | 117 / 36.0 / 72.0 / 108.0 | withheld | token-0139 (adjacent 7, covered 130) | likely prose locator not individually pixel confirmed |
| stella_maris_pdf06_dense-dialogue / left | token-0167 `aigroup/oftevillandsaberratitand` | `[352, 723, 650, 746]` | 298 / 36.0 / 72.0 / 108.0 | withheld | — | not determinable from current pixel review |
| stella_maris_pdf06_dense-dialogue / left | token-0195 `Something` | `[42, 884, 354, 908]` | 312 / 36.0 / 72.0 / 108.0 | included/supported | — | ordinary visible prose pixel confirmed |
| stella_maris_pdf06_dense-dialogue / left | token-0227 `mathematician?` | `[233, 983, 376, 1000]` | 143 / 36.0 / 72.0 / 108.0 | withheld | token-0228 (adjacent 7, covered 157) | likely prose locator not individually pixel confirmed |
| stella_maris_pdf06_dense-dialogue / left | token-0232 `Grothendieck.` | `[66, 1016, 195, 1032]` | 129 / 36.0 / 72.0 / 108.0 | withheld | token-0233 (adjacent 9, covered 138) | likely prose locator not individually pixel confirmed |
| stella_maris_pdf06_dense-dialogue / right | token-0031 `Grothendieck.` | `[108, 171, 236, 188]` | 128 / 35.0 / 70.0 / 105.0 | withheld | — | likely prose locator not individually pixel confirmed |
| stella_maris_pdf06_dense-dialogue / right | token-0089 `conversations` | `[86, 368, 208, 384]` | 122 / 35.0 / 70.0 / 105.0 | withheld | token-0090 (adjacent 6, covered 128) | likely prose locator not individually pixel confirmed |
| stella_maris_pdf06_dense-dialogue / right | token-0118 `mathematician` | `[251, 431, 386, 448]` | 135 / 35.0 / 70.0 / 105.0 | withheld | token-0119 (adjacent 9, covered 153) | likely prose locator not individually pixel confirmed |
| stella_maris_pdf06_dense-dialogue / right | token-0127 `Motchane—if` | `[233, 463, 360, 480]` | 127 / 35.0 / 70.0 / 105.0 | withheld | token-0128 (adjacent 5, covered 140) | not determinable from current pixel review |
| stella_maris_pdf06_dense-dialogue / right | token-0134 `nome—who` | `[583, 461, 692, 478]` | 109 / 35.0 / 70.0 / 105.0 | withheld | — | not determinable from current pixel review |
| stella_maris_pdf06_dense-dialogue / right | token-0150 `Oppenheimer` | `[87, 529, 211, 551]` | 124 / 35.0 / 70.0 / 105.0 | withheld | token-0151 (adjacent 6, covered 130) | likely prose locator not individually pixel confirmed |
| stella_maris_pdf06_dense-dialogue / right | token-0229 `Grothendieck` | `[212, 724, 336, 741]` | 124 / 35.0 / 70.0 / 105.0 | withheld | token-0230 (adjacent 11, covered 146) | likely prose locator not individually pixel confirmed |
| stella_maris_pdf06_dense-dialogue / right | token-0292 `mathematics.` | `[382, 983, 502, 1000]` | 120 / 35.0 / 70.0 / 105.0 | withheld | — | likely prose locator not individually pixel confirmed |
| stella_maris_pdf18_session-II_p35 / right | token-0065 `Oppenheimer` | `[220, 381, 346, 403]` | 126 / 40.0 / 80.0 / 120.0 | withheld | token-0066 (adjacent 5, covered 138) | likely prose locator not individually pixel confirmed |
| stella_maris_pdf18_session-II_p35 / right | token-0110 `Oppenheimer.` | `[108, 543, 237, 565]` | 129 / 40.0 / 80.0 / 120.0 | withheld | — | likely prose locator not individually pixel confirmed |
| stella_maris_pdf18_session-II_p35 / right | token-0139 `Oppenheimer.` | `[137, 706, 265, 727]` | 128 / 40.0 / 80.0 / 120.0 | withheld | — | likely prose locator not individually pixel confirmed |
| stella_maris_pdf18_session-II_p35 / right | token-0175 `Oppenheimer’s` | `[273, 933, 411, 955]` | 138 / 40.0 / 80.0 / 120.0 | withheld | token-0176 (adjacent 12, covered 163) | likely prose locator not individually pixel confirmed |

## E. Page-edge and gutter evidence

All four human-identified noisy rasters show observable page-boundary pixels at the OCR-box sequence. On Relativity 17 right and Relativity 23 right, page paper ends around x=638–641 and the OCR boxes lie in the dark gutter outside the sheet. On Relativity 10 left, a slanted/dark boundary streak occupies x=676–722 while text ends well to its left. On Relativity 23 left, the left frame spans x=0–27 and a right-edge streak spans x=723–755; the recurring `|` tokens lie on that streak. These pixel features are direct observations; “noise” is the interpretation supported by their location and isolated mark-like OCR labels.

| Page side | Admitted tokens | Pixel-aligned edge boxes | Lines consisting only of those boxes | Gap limit before → excluding edge boxes | Lines before → excluding edge boxes |
|---|---:|---:|---:|---:|---:|
| relativity_pdf10_pp26-27/left | 203 | 11 | 11 | 66 → 71 px | 54 → 40 |
| relativity_pdf17_pp40-41/right | 331 | 26 | 24 | 60 → 64 px | 69 → 44 |
| relativity_pdf23_pp52-53/left | 155 | 9 | 9 | 54 → 54 px | 43 → 34 |
| relativity_pdf23_pp52-53/right | 264 | 27 | 26 | 59 → 66 px | 72 → 41 |

There are 73 affected token boxes across the four pages, 70 of which form lines consisting only of edge-aligned tokens. Removing those baseline tokens counterfactually leaves tolerance at 4 px on all four pages; gap limits change 66→71, 60→64, 54→54, and 59→66 px. Thus page-edge tokens influence median width/gap thresholds on three of four pages. No page switches from slope 0 in the token-exclusion comparison.

### Crop/mask ablations

A uniform 2% trim was tested on every page. It does not reach the internal Relativity 10/17/23 boundary streaks. It also changes Tesseract segmentation: for example, on Relativity 10 left it changes 203 admitted tokens to 199 and re-recognizes multiple words; it does not restore the Stella Maris row.

The automatic treatment is source-independent: crop a frame-connected dark surround to the bright page field, or mask a narrow dark stripe detected in the outer 20% by column coverage. It detects edge features without fixture coordinates.

| Page side | Treatment | Baseline → OCR tokens | Edge boxes touched | Body positions not text/position matched | Lines after | Residuals after | Gap limit after |
|---|---|---:|---:|---:|---:|---:|---:|
| relativity_pdf10_pp26-27/left | `[{'kind': 'thin_interior_edge_streak', 'x0': 676, 'x1': 722}]` | 203 → 189 | 11 | 4 | 40 | 7 | 74 px |
| relativity_pdf10_pp26-27/right | `[{'kind': 'frame_connected_dark_right', 'x0': 604, 'x1': 792}]` | 280 → 261 | 0 | 37 | 65 | 1 | 76 px |
| relativity_pdf17_pp40-41/left | `[{'kind': 'frame_connected_dark_left', 'x0': 0, 'x1': 25}, {'kind': 'thin_interior_edge_streak', 'x0': 708, 'x1': 750}]` | 142 → 140 | 1 | 4 | 34 | 1 | 75 px |
| relativity_pdf17_pp40-41/right | `[{'kind': 'frame_connected_dark_right', 'x0': 638, 'x1': 792}]` | 331 → 308 | 26 | 2 | 44 | 0 | 66 px |
| relativity_pdf23_pp52-53/left | `[{'kind': 'frame_connected_dark_left', 'x0': 0, 'x1': 27}, {'kind': 'thin_interior_edge_streak', 'x0': 723, 'x1': 755}]` | 155 → 146 | 9 | 10 | 34 | 0 | 54 px |
| relativity_pdf23_pp52-53/right | `[{'kind': 'frame_connected_dark_right', 'x0': 641, 'x1': 792}]` | 264 → 238 | 27 | 15 | 37 | 5 | 66 px |
| stella_maris_pdf06_dense-dialogue/left | `[{'kind': 'thin_interior_edge_streak', 'x0': 739, 'x1': 763}]` | 233 → 257 | 0 | 0 | 51 | 0 | 72 px |
| stella_maris_pdf18_session-II_p35/left | `[{'kind': 'thin_interior_edge_streak', 'x0': 748, 'x1': 775}]` | 70 → 71 | 0 | 2 | 23 | 0 | 84 px |

The 73 edge-aligned boxes are removed or resegmented by the treatment, but body OCR is also perturbed. The `body positions not text/position matched` column is an alignment diagnostic, not a count of proven lost visible words; OCR substitutions and merged/split tokens make some unmatched words ambiguous. On the four noisy pages the treatment changes admitted counts by −14, −23, −9, and −26; it changes the total corpus count by −68 net. The three clean control lines remain intact under crop-only, but the treatment also changes unrelated pages: on Stella Maris 06 left it adds 24 OCR tokens and restores the omitted line; on Relativity 10 right it changes many body locator tokens despite touching no baseline token box.

It also changes the Relativity 17 right median-width statistic: `gap_limit` rises 60→66 px, moving the oversized threshold 90→99 px. `conclusion` then ceases to be oversized and the known split repairs. This is an interaction between edge-token population and the geometry threshold, not a direct crop of the word. Page-edge removal is causal for noise and page statistics, but the current general treatment is not shown to preserve OCR observations robustly.

## F. Missing-line stage

Baseline raw TSV for Stella Maris 06 left has no admitted word row centered near y=868; the visible text “to fly their colors as an independent nation unaccountable to God” is absent. The surrounding `creator’s...` and `or man alike. Something like that` rows are emitted. Therefore the disappearance is at Tesseract observation, not TSV admission or geometry grouping. `Something` has a 312×24 px box that overlaps the ordinary words to its right; this is a separate malformed OCR box.

Uniform 2% crop leaves that row absent. The automatic edge-mask raster emits 11 words centered at y=868 and another neighboring row around y=800. Since the treatment changes a far-right detected boundary while keeping the print area and Tesseract config fixed, it establishes that page-border raster content can alter PSM 6 OCR output here. It does not establish highlighting as the cause. The experiment also omits two previously emitted OCR tokens (`wholly`, `equations`) and yields other OCR changes, so the row reappearance alone is not a safe preprocessing result.

## G. Factorial ablations

Counts use the 11 nonblank page sides. “New merges” counts output lines that combine tokens from multiple current baseline lines after token identity mapping; “suspicious” flags an adjacent-box gap over the page limit or center-Y span over 1.5 median token heights. These flags are conservative screens, not a human oracle. “Edge boxes” counts baseline boxes targeted by the automatic treatment.

| Configuration | Admitted / resolved / residual / lines | Known false splits repaired (of 3) | New merges | Suspicious | Clean controls damaged | Edge boxes | Stella row still absent |
|---|---:|---:|---:|---:|---:|---:|---|
| baseline | 2219 / 2212 / 7 / 522 | 0 | 0 | 0 | 0 | yes |
| vertical only: best unconstrained slope | 2219 / 2210 / 9 / 469 | 1 | 43 | 0 | 1 | yes |
| oversized guard disabled | 2219 / 2218 / 1 / 464 | 2 | 51 | 1 | 0 | yes |
| auto crop/mask only | 2151 / 2137 / 14 / 434 | 1 | 20 | 0 | 74 | no |
| vertical + oversized disabled | 2219 / 2215 / 4 / 406 | 3 | 90 | 1 | 0 | yes |
| vertical + crop/mask | 2151 / 2137 / 14 / 396 | 2 | 49 | 0 | 74 | no |
| oversized disabled + crop/mask | 2151 / 2149 / 2 / 379 | 2 | 60 | 0 | 74 | no |
| all three | 2151 / 2148 / 3 / 343 | 3 | 83 | 0 | 74 | no |

The “vertical” setting forces each page’s best-scoring unconstrained slope; it is deliberately not a proposed estimator. Crop/mask uses the auto treatment, not the 2% trim. New line merges for crop scenarios are mapped by source text and center location and should be read with that re-tokenization limit. The row-absence column reports Tesseract observation status, not geometry correctness.

## H. Seven residuals as downstream observations

| Residual | Baseline | Forced slope only | Guard disabled only | Crop/mask only | All three |
|---|---|---|---|---|---|
| `token-0213` `system` (relativity_pdf10_pp26-27/left) | unassigned | uniquely_assigned | uniquely_assigned | uniquely_assigned | uniquely_assigned |
| `token-0216` `that` (relativity_pdf10_pp26-27/left) | ambiguous | ambiguous | uniquely_assigned (target row) | ambiguous | uniquely_assigned (target row) |
| `token-0217` `the` (relativity_pdf10_pp26-27/left) | ambiguous | ambiguous | uniquely_assigned (target row) | ambiguous | uniquely_assigned (target row) |
| `token-0226` `with` (relativity_pdf10_pp26-27/left) | ambiguous | uniquely_assigned (other row) | uniquely_assigned (target row) | ambiguous | uniquely_assigned (target row) |
| `token-0227` `respect` (relativity_pdf10_pp26-27/left) | ambiguous | ambiguous | uniquely_assigned (target row) | ambiguous | uniquely_assigned (target row) |
| `token-0246` `impossible` (relativity_pdf10_pp26-27/right) | unassigned | uniquely_assigned (target row) | unassigned | unassigned | uniquely_assigned (target row) |
| `token-0023` `A` (relativity_pdf17_pp40-41/right) | ambiguous | ambiguous | uniquely_assigned (target row) | uniquely_assigned | uniquely_assigned |

Unique assignment by itself is not a correctness result. `system` has no reviewer-specified target row and is reported only by assignment state. The other target-row checks use the human notes; crop cases remap token identities by text/center and are less certain after OCR resegmentation. Guard removal uniquely assigns the four Relativity 10 left row tokens `that`, `the`, `with`, `respect` to the reviewer-identified row, and assigns the Relativity 17 right `A` to its identified line. Forced slope uniquely assigns `impossible` to its target row.

## I. Recommendation boundary

The oversized guard has enough direct predicate evidence to justify a separate production design/implementation task. The 4× threshold is a bounded candidate because it repairs two named false splits while preserving the selected clean controls; its 42 corpus line merges still require review before selecting semantics.

The slope gate has enough evidence to justify a separate estimator-design task, but not to relax the support predicate directly: the forced best slope repairs one named split and damages a clean control. Any implementation must distinguish real shared baselines from page-wide cohesion gains and singleton noise.

Page-edge noise is established, including its effect on median-width-derived thresholds. The tested general crop/mask changes Tesseract outputs on clean as well as flagged pages and changes the missing Stella row. A production preprocessing task needs a stronger page-surface detector and explicit content-preservation controls; no treatment tested here is recommended as-is. No production fix was implemented.

## J. Verification and artifacts

- Research files: `investigate.py`, `run_ablations.py`, `results.json`, `test_forensics.py`, and this report, all under `research/accuracy-audit/fragmentation-forensics/`.
- No files under `src/normalize/`, fixture data/configuration, committed geometry/PNG review artifacts, `human-review.json`, or `human-review-thoughts.md` were modified.
- Focused forensic tests and full repository test suite results are recorded in the final commit report.
- `git diff --check` and final working-tree status are recorded after verification.
