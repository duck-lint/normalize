# Spineless residual geometry forensics

## A. Reproduced baseline

Commit `53ece235af82ef37fc7fe49be027301a25a8d104` exists locally. The six
spineless observations reproduce exactly with the prior study's crop, recorded
angle, Pillow bicubic rotation/expansion/white fill, and LANCZOS resize. No
angle was re-estimated. The forensic run used Tesseract 5.3.4, `eng`,
`--psm 6`, six OCR calls total. Full source, raster, and raw TSV hashes are in
[`results.json`](results.json).

| Page | Source size | Correction | Final raster | Tokens | Lines | Ambiguous / unassigned |
|---:|---:|---:|---:|---:|---:|---:|
| 26 | 2550×3300 | +0.44° | 729×1129 | 202 | 36 | 0 / 0 |
| 27 | 2550×3300 | −0.94° | 739×1136 | 264 | 46 | 0 / 0 |
| 40 | 2550×3300 | +0.86° | 737×1135 | 139 | 23 | 0 / 0 |
| 41 | 2550×3300 | −0.80° | 736×1134 | 307 | 34 | 0 / 0 |
| 52 | 2550×3300 | +0.74° | 735×1133 | 148 | 26 | 0 / 0 |
| 53 | 2550×3300 | −0.38° | 728×1128 | 221 | 33 | 0 / 0 |

Each source hash, final RGB-pixel hash, TSV hash, and output count matches the
prior capture byte-for-byte. The full raw TSV is represented by its SHA-256;
the complete raw TSV records intersecting each target region are preserved in
[`stage-traces.json`](stage-traces.json).

## B. Four failure summaries

The pixel regions were inspected before using the OCR identities to locate
records. All three prose rows for which word boxes exist are visibly continuous
on the flat raster. Neighboring printed rows occupy separate ink bands.

### Page 26 — `changes … embankment yet`

Pixel rectangle `[75,590,615,630]` contains one straight printed row. There is
no second physical row in that band. Raw TSV provides all eight word boxes,
source rows 69–76; all pass `parse_tsv_rows`. The first seven tokens form
vertical band 11 and `yet` forms band 12. The relevant values are:

* `yet`, source row 76: box `[573,604,599,620]`, center-y `612.0`;
* running band median: `607.5`; difference `4.5`; tolerance `4`;
* `embankment` center-y `607.0`; horizontal gap to `yet` is `14`, below the
  `66` px gap limit, but center-y difference is `5`, above tolerance.

In `_line_bands`, both `median_support` and `_horizontally_adjacent` are false.
The latter requires vertical proximity as well as horizontal proximity, so
`yet` starts a new band. Horizontal region splitting sees no excessive gap
inside either resulting region. Candidate generation supplies one line to
each token, and assignment preserves the split. The preceding and following
control rows each remain in one band.

The nearby raw `;` record (source row 77, 2×2 box, confidence 0) is admitted,
but it is processed after `yet` at the same center-y; it did not trigger this
split.

### Page 27 — `If K … every other`

Pixel rectangle `[145,155,655,185]` shows one printed row, separated from the
preceding row by 6 px and the next row by 7 px. All nine row word records
(source rows 32–40) are present in raw TSV and admitted. The unchanged slope
estimator returns `0.0`, so adjusted centers equal original centers.

`system,`, source row 37, has box `[425,163,489,180]`, center-y `171.5`. The
current band median is `167.0`, difference `4.5` against tolerance `4`. Its
horizontal gap to `co-ordinate` is `7` px (gap limit `77`), but the vertical
center difference is `4.5`; thus the combined neighbor-support condition also
fails. `_line_bands` starts a new vertical band at `system,`; `every` joins it
at center-y `172.0`. The other seven target tokens stay in the first band.
Horizontal splitting does not create the first separation. Every token gets
one candidate and is assigned without ambiguity.

### Page 27 — visible `affords … physical` row

Pixel rectangle `[110,660,650,700]` contains the highlighted row between two
separate prose rows. Tesseract does not emit individual usable word boxes for
that row. It emits level-5 source row 190, text locator `See`, box
`[7,640,624,696]` (617×56), confidence `14.663147`, spanning the preceding
line and the visible target line. It also emits source row 191, `ae`, box
`[625,671,639,686]`, confidence `33.175888`. The level-4 line record is blank
with confidence −1.

Both level-5 records pass the current parser: text is nonblank, confidence is
inside `[0,100]`, dimensions are positive, coordinates are inside the
739×1136 raster, and payloads are unique. `parse_tsv_rows` has no minimum
confidence cutoff. The broad `See` and tiny `ae` records become separate
geometry lines (line-0031 and line-0032). Thus the first divergence is already
in the raw Tesseract observation. This is neither a parser rejection nor a
geometry assignment failure. The visible row's actual words are absent as
word-level observations, although the row's pixels intersect a badly merged
word box.

The adjacent control rows are admitted and each remains one geometry line.
The next highlighted continuation is also emitted as ordinary tokens. The
target and continuation have similar measured highlight coverage (about 32.5%
and 30.6% under the diagnostic RGB mask described in section G).

### Page 53 — `and for still greater velocities … becomes`

Pixel rectangle `[85,485,620,520]` contains one straight prose row. Display
math ends above it at y=476; this prose begins at y=494. The next prose row
begins at y=518–523. All eight target word boxes (source rows 108–115) are
present and admitted.

The first wrong separation is source row 111, `greater`, box
`[220,499,280,516]`, center-y `507.5`. The current vertical-band median is
`502.0`; difference `5.5` exceeds tolerance `4`. Its x-gaps to `still` and
`velocities` are `12` and `11` px, but their center differences (5.5 and 4.5)
exceed tolerance, so neither supplies neighbor support. `_line_bands` starts a
new vertical band for `greater`. `square-root` joins that band by median
support.

The split then creates further horizontal fragments: in the first band the
true gaps are `83` and `124` px; in the second, `143` px. All exceed the
unchanged `66` px limit. The result is five geometry lines for the one printed
row. Each token has one candidate and assignment faithfully retains those
regions; assignment is not the first divergence.

## C. Stage trace and exact implementation

Current production flow is `run_geometry` → `_page_geometry` →
`pytesseract.image_to_data` → `parse_tsv_rows` → `group_physical_lines`.
Within `group_physical_lines`, median token height gives tolerance
`max(1, floor(median_height/4 + 0.5))`; the slope estimator runs before
`_line_bands`. On all three target pages the selected slope is `0.0`, so
`_adjusted_center_y(token, slope)` leaves each center unchanged.

`_line_bands` sorts tokens by adjusted center-y, x, and TSV source row. For
each token it tests the current band's median support and then neighbor
support. Neighbor support requires both center difference ≤ tolerance and
`_horizontally_adjacent`; the latter also requires the observed x-gap to fit
the page limit. `_line_bands` then calls `_split_horizontal_regions`, which
uses cumulative observed right edges. `group_physical_lines` generates line
candidates from those regions, evaluates vertical support/containment, assigns
each token to exactly one candidate or records it unresolved, and constructs
line bounds. `_page_geometry` serializes these records through `_token_record`.

| Page/context | Raw TSV | Admission | Vertical stage | Horizontal stage | Candidate / assignment | First divergence |
|---|---|---|---|---|---|---|
| 26 changes…yet | Complete usable boxes | All target words admitted | `yet` starts separate band at 4.5 px > 4 | No first split; adjacent gaps ≤66 | One candidate per token; separate assignments | **vertical_band_construction** |
| 27 If K…other | Complete usable boxes | All nine admitted | `system,` starts second band at 4.5 px > 4 | Both bands retained | One candidate per token | **vertical_band_construction** |
| 27 affords…physical | No usable per-word boxes; jumbo `See` plus `ae` | Both emitted records admitted | Operates only on abnormal boxes | Separate output regions | Both records assigned; no missing-row token identity exists | **raw_tesseract_observation** |
| 53 greater…becomes | Complete usable boxes | All eight admitted | `greater` starts second band at 5.5 px > 4 | Three further gap splits | One candidate per token; five lines | **vertical_band_construction** |

The control inputs and complete row identities are in
[`stage-traces.json`](stage-traces.json). `adjudications.json` records each
event's exact predicate and source rows. No row first diverges at horizontal
splitting, candidate generation, assignment, or serialization.

## D. Matched controls

Controls below are nearby, visibly distinct physical rows traced through the
same parser and geometry functions. Their complete token boxes and assignments
are in the trace artifact.

| Failure | Nearby correct control | Center-y range | Box-height range | Result |
|---|---|---:|---:|---|
| Page 26 | preceding row, 6 tokens | 579–582 | 16–32 | one band / line-0012 |
| Page 26 | following row, 11 tokens | 636–638.5 | 11–29 | one band / line-0016 |
| Page 27 If K | preceding row, 5 tokens | 139–142 | 16–22 | one band / line-0005 |
| Page 27 If K | following row, 7 tokens | 195.5–200.5 | 10–20 | one band / line-0008 |
| Page 27 missing row | preceding row, 9 tokens | 650–653 | 10–31 | one band / line-0030 |
| Page 27 missing row | following row, 9 tokens | 707–711.5 | 16–33 | one band / line-0033 |
| Page 53 | next prose row, 10 tokens | 531–533.5 | 11–31 | one band / line-0018 |
| Page 53 | following prose row, 10 tokens | 590.5–592 | 21–38 | one band / line-0019 |

The distinguishing property is the token's position relative to the *running*
band median when considered, plus whether a token satisfies both parts of
neighbor support. Maximum center range alone does not predict a split: the
page-27 following control spans 5 px but its center values arrive close enough
to the moving median to remain together. Large box heights alone also do not
predict a split; the page-53 controls contain taller boxes but tighter centers.

## E. Center and height evidence

| Target | Center-y values/range | Heights | Observation |
|---|---|---|---|
| Page 26 | 607–612; median before `yet` 607.5 | 11–21 | `yet` center is 4.5 px from median; its bottom is 620 vs `embankment` bottom 615 |
| Page 27 If K | 167–172 | 10–17 | `system,` and `every` bottoms are 180 vs the main row's common 175 |
| Page 53 | 502–507.5 | 16–17 | `greater` and `square-root` bottoms are 516 vs 510–511 for most row tokens; height itself varies only 1 px |
| Page 27 missing | No target word boxes | emitted `See` height 56 | The broad box spans multiple physical lines and cannot represent target word geometry |

Center-based vertical spread directly contributes to all three admitted-row
splits. On page 53, height variation is not needed to explain the threshold
crossing: boxes of nearly equal height have centers separated by 5.5 px.
These measurements diagnose the current representation; no alternate anchor
was tested.

## F. Highlighting

Highlighting is unsupported as the cause of these four events. The page-26
false split and page-27 If K split occur without highlight overlap, while
highlighted neighboring controls remain one line. The page-27 missing row is
highlighted, but the following highlighted row is recognized and grouped. The
page-53 split occurs on an unhighlighted row while highlighted prose controls
remain grouped.

As a reproducible supporting diagnostic only, highlight coverage was counted
with the simple RGB condition `G > R+15`, `B > R+8`, `G > 90`, `B > 90` over
the listed row rectangles. Approximate target/control fractions were: page 26
0% vs 23%/12%; page-27 If K 0% vs 0%/8%; page-27 missing 32% vs 31% on the
following line; page 53 0% vs 12%/30%. This threshold is not a physical
highlight classifier. The pixel comparisons do not show a matched change
that uniquely tracks the failures.

## G. Page 27 missing-row finding

The primary full-page `--psm 6` TSV contains one level-4 blank hierarchy row
(source 189, confidence −1), one level-5 `See` word box (source 190), and one
level-5 `ae` word box (source 191) intersecting the visible passage. It does
not contain usable per-word boxes for `affords`, `an`, `insufficient`,
`foundation`, `for`, `the`, or `physical`. The parser skips the blank
hierarchy row for its `confidence == -1` sentinel and admits the two word
records under its stated conditions. Therefore:

* Tesseract did emit geometry over the target pixels, but in a merged,
  geometrically abnormal word record;
* production admission did not reject that record;
* the parser did not discard word-level records covering the row;
* downstream grouping operates on `See` and `ae`, not on the visible words.

No alternate crop or OCR configuration was run. The production invocation's
raw TSV establishes the first divergence.

## H. Bound versus spineless mechanisms

Archived bound token tables are available, but the prior study did not archive
full bound raw TSV. The comparison below therefore starts at the archived
admitted boxes; it cannot diagnose bound-side raw observation or admission.

For page 27, bound geometry also first splits the row in `_line_bands`, but
the center pattern differs. In the bound raster the left-side tokens have
centers around 126–133 while `then`, `every`, and `other` are at 119–123.
The first second-band token is `co-ordinate`, center 126, 5.5 px from the
current median 120.5. In the flat scan the separation begins at `system,`
center 171.5, 4.5 px from median 167. The production stage and median
predicate are the same; the location and direction of the displaced boxes
differ. Flattening the page reduces the broad row drift but does not eliminate
the center-based split.

For page 53, `greater` is the isolated word in both archived bound geometry
and the spineless result. Bound center-y is 432 vs current median 427 (5 px >
tolerance 4); spineless is 507.5 vs 502 (5.5 px > 4). Both first diverge at
vertical-band construction. The spineless result adds horizontal fragments
because moving `greater` and `square-root` to their own band leaves gaps 83,
124, and 143 px in the other regions; the bound result retained three row
groups. The display equation is not part of either first-divergence event.

## I. Causal inventory

Of the four residual contexts, three first diverge in vertical band
construction and one first diverges in the raw Tesseract observation. None
first diverges in production admission, horizontal-region splitting,
candidate generation/assignment, or serialization/reconciliation. All four
pixel interpretations are clear; none is unresolved because of ambiguous
physical evidence.

## J. Candidate future questions

1. For the three vertical-band cases, do glyph-baseline or box-bottom
   measurements align more consistently with the visible physical row than
   box centers on these same target/control rows?
2. For the page-27 merged raw record, is the `--psm 6` segmentation sensitive
   to full-page context versus a local context crop? That would be a separate
   diagnostic, not evidence about the current full-page invocation.

## K. Verification

The baseline full repository suite passed on the new branch before analysis
(one existing skip). The focused forensic tests, relevant geometry and
preprocessing tests, prior spineless-study test, and final full suite are
reported in the task completion summary. `run_forensics.py` reproduces all six
source/raster/TSV hashes and counts and uses exactly six primary OCR calls.

Only research text/code/JSON files are changed by this study. Production
`src/normalize`, preprocessing config, tests, source images, and fixture
expectations are unchanged. No raster or PDF is included in Git.
