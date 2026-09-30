# Frozen-OCR page-coordinate rotation ablation

This experiment uses the original production-cropped side raster for OCR, then
holds those admitted OCR records fixed while transforming their boxes into the
prior study’s page-coordinate frame. Geometry means and rules are the current
production implementation. No production source, crop configuration, OCR
configuration, tolerance, gap rule, or slope estimator changed.

## A. Frozen OCR authority

Tesseract 5.3.4, language `eng`, config `--psm 6`: one `image_to_data` call per
source side, twelve total. Every fresh source TSV SHA-256 exactly matches the
prior raster study’s unrotated control TSV SHA-256. The full frozen token
records include source TSV row, text, confidence, all Tesseract IDs, original
`x/y/width/height/x1/y1`, and original sequence order in
[`results.json`](results.json).

Control, chosen-angle, and perturbation paths preserve those identities and
ordering byte-for-byte; only the coordinate fields in transformed token copies
change. The token-record hashes below cover the ordered full frozen token
records, including coordinates.

## B–C. Control baseline and transformed geometry

| Page side | Angle | Frozen tokens | Token-record SHA-256 | Lines control → transformed | Ambiguous control → transformed | Unassigned control → transformed | Selected slope control → transformed | Tolerance control → transformed | Gap limit control → transformed |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| Relativity 10 left | −0.6° | 191 | `0e3d67f52c0c162dec9f50ab7743ab1492cfd5e713190953175c9e102783757b` | 26 → 22 | 0 → 0 | 0 → 0 | 0.0 → 0.0 | 4 → 5 px | 72 → 74 px |
| Relativity 10 right | −1.9° | 263 | `15210eb8f8a732b22edf0e78a7f17037add9ab4b8300116b7a6560212c9373de` | 62 → 39 | 0 → 0 | 1 → 0 | 0.0 → 0.0 | 4 → 5 px | 78 → 80 px |
| Relativity 17 left | +0.8° | 138 | `31a138fcfb195d0d6ea929f7d0d85967106c887e8c72525a346fd35f4cc15cec` | 30 → 22 | 0 → 0 | 0 → 0 | 0.0 → 0.0 | 4 → 5 px | 77 → 79 px |
| Relativity 17 right | 0° | 305 | `84ef1378d5c71acb6045322bc6d87543f78aa414da9732205070056da0d50847` | 32 → 32 | 0 → 0 | 0 → 0 | 0.0 → 0.0 | 4 → 4 px | 66 → 66 px |
| Relativity 23 left | 0° | 143 | `8df712f42a0c01c0c9db5f4be2729319afd3da795a6beb97ca2d8bb90705031f` | 24 → 24 | 0 → 0 | 0 → 0 | 0.0 → 0.0 | 4 → 4 px | 58 → 58 px |
| Relativity 23 right | 0° | 226 | `8d4614a5f1ae7678b665cc572d5f1b588833894735a2a58f90db39f8ffcc66f4` | 32 → 32 | 0 → 0 | 0 → 0 | 0.0 → 0.0 | 4 → 4 px | 68 → 68 px |
| Stella Maris 03 left (blank) | unresolved | 385 | `0e33185b6a8e2822d9e5e5838de140dee0fe010887bb6addd3b5fc4c548e7510` | 101 → 101 | 4 → 4 | 6 → 6 | 0.0 → 0.0 | 6 → 6 px | 108 → 108 px |
| Stella Maris 03 right | 0° | 133 | `9360db1fe10ba58fb55b02b1b3861fe070ec2d8c1d85b1b50b7c37c68f796ad4` | 23 → 23 | 0 → 0 | 0 → 0 | 0.0 → 0.0 | 4 → 4 px | 74 → 74 px |
| Stella Maris 06 left | 0° | 255 | `87c2f12f2d02bd5dd4d75502d950acce36e27009ef2c9856ac9f4863bbe78369` | 42 → 42 | 0 → 0 | 0 → 0 | 0.0 → 0.0 | 4 → 4 px | 72 → 72 px |
| Stella Maris 06 right | 0° | 271 | `360bba582b07a5a62b0fb998dbcb58953d5050efec5cffd4ffb03b3606676b47` | 38 → 38 | 0 → 0 | 0 → 0 | 0.0 → 0.0 | 4 → 4 px | 70 → 70 px |
| Stella Maris 18 left | unresolved | 68 | `0c33640b9be6722afc0bf94c43874a353a80c95ea5f2257244bfbc4bd880c4e6` | 23 → 23 | 0 → 0 | 0 → 0 | 0.0 → 0.0 | 4 → 4 px | 84 → 84 px |
| Stella Maris 18 right | 0° | 132 | `f2daa6437179ff694b2fb1f2566c87de489061e4b3280729f5cd1083958d6437` | 33 → 33 | 0 → 0 | 0 → 0 | 0.0 → 0.0 | 4 → 4 px | 81 → 81 px |

The selected slope remains `0.0` everywhere. The transformed AABBs change the
production measurements naturally on the three nonzero sides: tolerance moves
from 4 to 5 px and gap limit rises by 2 px. Their formulas and implementation
are unchanged. A 0° transform is exact identity and all 0° geometry outputs
compare equal to control. The two unresolved-angle sides also remain unchanged.

## D. Physical-page orientation and affine transform

Angles below are the prior independent pixel measurements; this experiment did
not select or optimize angles using grouping. The prior implementation passed
the same signed angle directly to Pillow `Image.rotate(angle,
 BICUBIC, expand=True)`. Pillow’s positive angle is counterclockwise. The
forward pixel-coordinate matrix is `[[cos θ, sin θ], [−sin θ, cos θ]]` around
the source center, followed by centering translation `(destination − source)/2`.
Its output canvas is determined by floor/ceil bounds of all four page-edge
corners. The complete matrices, centers, translations, and destination sizes
for all sides are in `results.json`.

| Page side | Correction | Pixel evidence from prior study | Uncertainty / single orientation |
|---|---:|---|---|
| Relativity 10 left | −0.6° | Three body regions: −0.23°, −0.59°, −0.84°; long horizontal ink-edge segments | ±0.3°; all regions agree |
| Relativity 10 right | −1.9° | −2.02°, −1.79°, −1.88° | ±0.2°; regions agree |
| Relativity 17 left | +0.8° | +0.43°, +0.58°, +1.17° | ±0.35°; all regions agree on positive orientation |
| Relativity 17 right | 0° | 0°, 0°, 0° | ±0.2°; horizontal |
| Relativity 23 left | 0° | 0°, +0.12° in supported body regions; sparse lower display-math region excluded | ±0.2°; body evidence supports horizontal |
| Relativity 23 right | 0° | −0.16°, 0°, 0° | ±0.2°; horizontal |
| Stella Maris 03 left (blank) | unresolved | No printed body rows | No orientation established; excluded from primary correctness decision |
| Stella Maris 03 right | 0° | 0°, 0°, 0° | ±0.2°; horizontal |
| Stella Maris 06 left | 0° | 0°, 0°, 0° | ±0.2°; horizontal |
| Stella Maris 06 right | 0° | 0°, −0.30°, 0° | ±0.2°; regional variation within measurement uncertainty |
| Stella Maris 18 left | unresolved | 0°, 0°, +0.37° | ±0.25°; regional disagreement; no rigid angle assigned |
| Stella Maris 18 right | 0° | 0°, +0.29°, 0° | ±0.25°; majority supports horizontal |

The three nonzero affine summaries are:

| Side | Source → destination px | Expansion translation px | Forward affine matrix |
|---|---:|---:|---|
| Relativity 10 left, −0.6° | 545×813 → 555×819 | (5, 3) | `[[0.999945169365512, −0.010471784116246, 9.271721591151945], [0.010471784116246, 0.999945169365512, 0.1687274812423425], [0, 0, 1]]` |
| Relativity 10 right, −1.9° | 556×983 → 590×1001 | (17, 9) | `[[0.999450215941757, −0.033155178388526, 33.44861014615212], [0.033155178388526, 0.999450215941757, 0.05307927261617351], [0, 0, 1]]` |
| Relativity 17 left, +0.8° | 538×777 → 550×785 | (6, 4) | `[[0.999902524009304, 0.013962180339145, 0.6019139797393622], [−0.013962180339145, 0.999902524009304, 7.793695933615368], [0, 0, 1]]` |

All transformed token boxes enclose the affine images of their four original
half-open rectangle corners. The global rounding rule is floor minima and ceil
maxima. Mean token area changes from 1053.4 to 1159.3 px² on Relativity 10 left,
1050.2 to 1248.4 px² on Relativity 10 right, and 814.2 to 919.3 px² on
Relativity 17 left. This is roughly 10%, 19%, and 13% mean area growth
respectively. Mean width and height growth and per-token maxima are recorded in
the result JSON.

## E. Changed-event adjudication

All 34 changed components are identity-completely enumerated in
[`adjudications.json`](adjudications.json), with original/transformed boxes,
source rows and text locators, both memberships, angle, slopes, tolerance, gap
limit, and a prior raster-event crosswalk where available.

| Classification | Count |
|---|---:|
| `repaired_false_split` | 30 |
| `destructive_merge` | 0 |
| `new_false_split` | 2 |
| `benign_difference` | 1 |
| `unresolved` | 1 |

The repairs include the Relativity 10 left row ending “executing a uniform
translatory motion with respect to,” Relativity 17 left rows containing
“embankment” and “consequence,” and several slanted Relativity 10 right rows.
The two new splits are on Relativity 10 right: one isolates the leading OCR box
of the visible “to K, it is in a condition of uniform motion of translation”
row; the other splits the visible “affords an insufficient foundation for the
physical” row at a malformed OCR box boundary. One small isolated “7” token
remains unresolved because the pixels do not establish whether it is a mark or
belongs to the phrase. The only benign event combines spatially separate
diagram labels on Relativity 17 left; it does not join body rows.

## F. Relativity 10 right false-split discriminator

The prior raster rerun split “If K is a Galileian co-ordinate system, then
every other” into three bands. With frozen OCR, original control has two bands
(`30–35` and `36–38`); coordinate-transformed boxes put all nine identities
(`30–38`) in one band. The page pixels show one continuous printed row. The
prior raster-run false split therefore does **not** survive the frozen
coordinate transform. Its damage came from the raster/OCR path or its
interaction, not from this coordinate transform alone.

## G. Prior repair and slope-research crosswalks

All 29 prior raster `repaired_false_split` contexts map by exact source-row
identity. Every one has multiple control bands and one frozen-transform band:
**29/29 reproduce under pure coordinate transformation**. The prior raster
study’s one `new_false_split` context (the “If K…” row) instead becomes one
continuous band here.

For the historical local-slope study’s 37 repaired contexts, the current
crosswalk gives 26 frozen-transform one-band groupings, 8 still multi-band, and
3 other/already-one-band outcomes. The historical 8 slope-created false-split
contexts each remain one band after coordinate transformation; the harmful
splits are not reproduced. The Relativity 23 left display-math context remains
unresolved in its historical identity crosswalk and receives 0° here, so this
experiment does not force a decision about it. The full 46-context crosswalk
and source-row mappings are in `results.json`.

## H. Angle sensitivity without OCR rerun

Each variant reuses the same frozen token count and token-record hash:

| Side | Angle | Tokens | Lines | Ambiguous | Unassigned | Prior raster-repaired contexts still one band |
|---|---:|---:|---:|---:|---:|---:|
| Relativity 10 left | −0.8° | 191 | 22 | 0 | 0 | 4/4 |
|  | −0.6° | 191 | 22 | 0 | 0 | 4/4 |
|  | −0.4° | 191 | 22 | 0 | 0 | 4/4 |
| Relativity 10 right | −2.1° | 263 | 40 | 0 | 0 | 20/20 |
|  | −1.9° | 263 | 39 | 0 | 0 | 20/20 |
|  | −1.7° | 263 | 38 | 0 | 1 | 20/20 |
| Relativity 17 left | +0.6° | 138 | 22 | 0 | 0 | 5/5 |
|  | +0.8° | 138 | 22 | 0 | 0 | 5/5 |
|  | +1.0° | 138 | 22 | 0 | 0 | 5/5 |

Line partitions are stable across ±0.2° on Relativity 10 left and Relativity
17 left. Relativity 10 right is not fully stable: its line count moves 40 → 39
→ 38 while all 263 OCR records remain fixed. A finer ±0.3° / 0.05° trace locates
two geometry cliffs: at −2.00° through −2.20°, rows 193/194/196 split away
from the chosen-angle grouping; at −1.80° through −1.60°, row 49 becomes
unassigned. The 29 prior repairs remain grouped throughout, but the two new
false-split contexts trade behavior over this interval. The previous raster
experiment’s 263-versus-98 token change between −1.9° and −1.7° was OCR/raster
sensitivity. The remaining line-count variation here is geometry-only and
still material.

## I. Already-correct controls and representation limits

The six 0° sides are output-identical to control. The unresolved Stella Maris
18 left side and blank Stella Maris 03 left side are untransformed. Relativity
17 right’s “reference-body” line, Relativity 23 display math, headers, page
numbers, and Stella Maris dialogue/control pages receive no coordinate change
because their selected angle is 0°. The changed figure labels remain diagram
labels rather than body rows.

The intervention transforms axis-aligned OCR rectangles, not oriented glyph
outlines. Taking a second axis-aligned envelope increases mean area by 10–19%
on the three nonzero pages. The two new false splits occur in this transformed
box geometry, and one is sensitive to small angular changes. This is evidence
that these observed OCR envelopes plus current grouping are not a fully
adequate representation of corrected page geometry. No oriented-box or local
correction was added.

## J. Three-path causal comparison and decision

| Path | OCR identities | Geometry result |
|---|---|---|
| A. Production control: crop → OCR → original boxes | Fixed control set | 29 prior raster-repaired contexts are fragmented; selected production slope is 0.0 |
| B. Prior raster rotation: rotate pixels → OCR again → geometry | Can change with angle/interpolation; Relativity 10 right perturbation changed 263 to 98 tokens | 29 repairs, 0 destructive merges, 1 raster-run new false split |
| C. Frozen coordinate transform: OCR once → transform complete boxes → geometry | Exactly the same 12 control TSVs and token identities for all variants | All 29 repairs reproduce; prior raster false split disappears; 2 different AABB-induced false splits appear |

**Decision: transformed OCR-envelope representation is insufficient.** Physical
page-coordinate correction is strongly supported as a cause of the original
fragmentation, and the raster-run “If K…” regression does not recur. But the
fixed observation set still has two visibly wrong splits and one unresolved
changed event, with a sensitivity cliff on Relativity 10 right. The acceptance
conditions for a clean geometry-only result are not met. No production change
is authorized by this result; any next experiment should isolate whether
oriented token geometry or raster/OCR segmentation accounts for these specific
residuals rather than changing production tolerances.

## K. Verification

| Check | Result |
|---|---|
| Focused affine/frozen-identity tests | 13 passed |
| Relevant production geometry tests | 110 passed (`test_slice2`, horizontal-region guard, vertical-clustering investigation) |
| Prior raster-rotation research tests | 9 passed |
| Full repository suite | 188 passed, 1 skipped; exit 0 |
| Fixture preprocessing | Six fixtures, twelve sides, production path |
| Experiment OCR calls | 12 total; one per source side; no OCR in coordinate/angle variants |
| Production source/config diff | None; source hashes match prior production hashes |
| Tracked `.png` / `.pdf` | None |
| Commit / branch / worktree | Dedicated branch `research/frozen-ocr-page-transform`; bounded commit; clean worktree after commit; no merge or push |
