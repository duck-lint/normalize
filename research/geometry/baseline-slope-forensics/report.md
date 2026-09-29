# Baseline slope estimator forensics

## Decision

**Candidate failure topology requires further research.** Independent scan-pixel
measurements contradict production slope `0.0` on eight of the eleven
nonblank sides. The current singleton admissibility rule explains why those
pages still select zero. The tested replacements repair many real row
fragmentations, but introduce eight new false splits and leave one material
display-math change unresolved. A token-cohesion alternative also fails
synthetic counterexamples. The acceptance criteria are not met; this study
does not authorize a production implementation experiment.

This supersedes the source-inspection-only conclusion committed first on this
branch. Production geometry remains unchanged.

## A. Current estimator mechanics

Inspection and instrumentation of the unchanged
[`geometry.py`](/home/duck-lint/projects/normalize/src/normalize/geometry.py)
establish:

- Candidate slopes are `-0.100` through `+0.100` px/px, in `0.001` steps:
  201 candidates, evaluated in ascending order.
- A token's adjusted vertical coordinate is `center_y - slope * x`.
- `_line_bands` sorts by adjusted center, x, and source row. It adds a token to
  the latest band if it is within the current median tolerance **or** within
  tolerance of a horizontally adjacent token in that band. It then applies
  the unchanged horizontal split predicate.
- The horizontal gap limit is `max(1, 2 * median(positive token widths))`.
- Cohesion is `sum(n * (n - 1) / 2)` across post-split regions. It counts
  within-region token pairs; it is not a physical-row likelihood.
- A nonzero candidate is rejected if it produces fewer than two regions, if
  any region is a singleton, or if its score is not strictly above zero's.
  Surviving candidates rank by score; ties prefer smaller absolute slope.

For each candidate, the instrumentation independently copied only the
pre-split grouping loop and asserted its post-split result equals the
production `_line_bands(...)` result. The complete 201-row landscape records
raw-band and split-region membership identities, counts, scores, rejection
reasons, and rank in [`results.json`](results.json).

## B. Why all current production sides select zero

The 11 nonblank production sides all select `0.0`. **Every one of the 2,200
nonzero evaluations has at least one singleton region.** The singleton gate
is causal on eight sides: the listed number of slopes has a higher score than
zero and is rejected only for singleton presence. On the other three, no
nonzero candidate beats zero's score, and singleton presence also rejects
every nonzero candidate.

| Fixture side | Tokens | Zero score | Top raw nonzero slope / score | Singleton-only higher-score candidates | Why zero survives |
|---|---:|---:|---:|---:|---|
| Relativity 10 left | 180 | 701 | `−0.008` / 747 | 22 | Better scores rejected for singleton |
| Relativity 10 right | 245 | 548 | `−0.027` / 937 | 72 | Better scores rejected for singleton |
| Relativity 17 left | 140 | 485 | `+0.027` / 560 | 35 | Better scores rejected for singleton |
| Relativity 17 right | 305 | 1410 | `−0.001` / 1410 | 0 | No strict score improvement; singleton also present |
| Relativity 23 left | 147 | 675 | `+0.011` / 678 | 5 | Better scores rejected for singleton |
| Relativity 23 right | 228 | 967 | `−0.001` / 967 | 0 | No strict score improvement; singleton also present |
| Stella Maris 3 right | 132 | 466 | `−0.011` / 480 | 5 | Better scores rejected for singleton |
| Stella Maris 6 left | 256 | 1019 | `−0.005` / 1074 | 15 | Better scores rejected for singleton |
| Stella Maris 6 right | 270 | 1312 | `+0.001` / 1309 | 0 | Lower score; singleton also present |
| Stella Maris 18 left | 68 | 134 | `+0.030` / 147 | 19 | Better scores rejected for singleton |
| Stella Maris 18 right | 128 | 329 | `+0.005` / 337 | 15 | Better scores rejected for singleton |

The `candidate_landscape` records the exact memberships and all reasons for
each evaluation, including candidates rejected for multiple reasons. There
were no nonzero admissible survivors on any primary side. Thus eight pages
show “a better raw cohesion score, vetoed by the singleton gate”; three show
“no better raw score, with the singleton veto also active.”

The singleton identities are recorded per candidate and classified by
spatial role where supported. They include page numbers, centered headings,
diagram labels, formula components, short dialogue/prose rows, punctuation,
tiny OCR fragments, and ordinary prose tokens. This confirms the page-global
gate is affected by spatially unrelated elements. OCR wording in that
inventory is a locator only. The exact source-row IDs and boxes are in the
JSON artifacts.

## C. Independent physical slope evidence

The twelve current 144-DPI page sides were rendered from the six exact local
fixture PDFs using production preprocessing. Tesseract TSV was captured once
per side. The same admitted-token records feed baseline instrumentation and
both candidate substitutions. Per-side source PDF, cropped-image, TSV, and
admitted-token SHA-256 hashes, dimensions, token counts, tolerances, and gap
limits are in `results.json`; admitted records are in
[`admitted_tokens.json`](admitted_tokens.json). Rasters and TSV files stayed
under `/tmp`.

The independent pixel channel uses no OCR text or Tesseract line IDs as row
truth. For each nonblank side it maximizes the squared row-profile
concentration of dark scan pixels under horizontal shear, over slopes
`[-0.06, +0.06]` in `0.00025` steps. Thresholds 90, 120, 150, and 180 are
reported as sensitivity checks. Separately, three visually inspected printed
body rows per side were fit from lower ink envelopes: OCR source rows only
located a narrow region; after visual confirmation of a single printed row,
the method took the 95th-percentile dark-pixel y in 25-pixel x bins and fit a
line. Each fit records x-span, RMSE, slope standard error, threshold, and
source-row locator IDs. Three page headings were measured separately as a
furniture check.

| Fixture side | Three local row slopes (px/px) | Median | Range | Approx. median vertical trend across page width |
|---|---|---:|---:|---:|
| Relativity 10 left | `−.01603, −.01642, −.01703` | `−.01642` | `.00100` | `−8.9 px` |
| Relativity 10 right | `−.03595, −.03315, −.03371` | `−.03371` | `.00280` | `−18.8 px` |
| Relativity 17 left | `+.01520, +.01485, +.01618` | `+.01520` | `.00133` | `+8.2 px` |
| Relativity 17 right | `+.00060, −.00245, −.00051` | `−.00051` | `.00305` | `−0.3 px` |
| Relativity 23 left | `+.00943, +.00950, +.01031` | `+.00950` | `.00088` | `+5.1 px` |
| Relativity 23 right | `−.00413, −.00259, −.00491` | `−.00413` | `.00232` | `−2.2 px` |
| Stella Maris 3 right | `−.00047, −.00122, −.00077` | `−.00077` | `.00075` | `−0.5 px` |
| Stella Maris 6 left | `+.00108, +.00066, −.00049` | `+.00066` | `.00157` | `+0.4 px` |
| Stella Maris 6 right | `−.00682, −.00846, −.00878` | `−.00846` | `.00196` | `−5.4 px` |
| Stella Maris 18 left | `+.01114, +.00747, +.00789` | `+.00789` | `.00367` | `+4.9 px` |
| Stella Maris 18 right | `+.00611, +.00389, +.00450` | `+.00450` | `.00222` | `+2.8 px` |

The sampled rows establish measurable nonzero slope on eight sides. The three
near-zero sides show less than about one pixel of median trend across a page;
Relativity 17 right has one local row fit that expands the sampled spread to
about 1.6 pixels, so an exact common zero versus a very small local trend is
not distinguishable as cleanly there. Relativity 10, 17, and 23 chapter
headings measured separately agree in direction and magnitude with their
body-row fits. Row slopes vary within each page, but the sampled prose supports
an approximate common linear trend; these measurements do not establish that
page numbers, diagram labels, or display math share it. One formula event is
left unresolved below.

## D. Is one page-global slope a valid model?

For the inspected continuous text rows, one approximate linear slope is
supported on the eight sloped sides and near-zero orientation is supported
on the three near-horizontal sides. Local row-slope ranges are explicit in
Section C; the largest sampled range corresponds to roughly 2.1 pixels across
the page width (Stella Maris 18 left). That is modest variation but real enough
to retain as a limit on precision.

This is not evidence that every printed region shares that slope. Relativity
17 left contains a diagram; Relativity 23 left contains display math. The
pixel measurements intentionally do not promote those regions to prose-row
authority. The evidence supports a global approximation for sampled text,
not a universal page transform. Global linear slope is **not falsified** on
these samples; neither is it licensed as a safe grouping rule by itself.

## E. Synthetic oracle and counterexamples

Two source-independent matrices were run. The pixel matrix draws geometric
ink rows and singleton outliers; the expected physical rows/slopes are
explicit test oracle data.

| Case | Pixel estimator outcome | Oracle result |
|---|---|---|
| A Horizontal rows | `−0.001`; two supported rows | Effectively zero; separate rows preserved |
| B Shared skew `+0.040` | `+0.039` | Direction and magnitude recovered; identities preserved |
| C Shared skew plus singleton | `+0.039`; three supported runs | Singleton does not veto the slope or merge with body |
| D Header plus body | `+0.031`; three rows | Header remains separate |
| E Competing nearby rows | Abstains: one corrected ink run | No destructive merge; reports insufficient safe support |
| F Different-slope regions `+.045 / −.045` | Abstains; regional fits disagree | Conflict is exposed rather than averaged into certainty |
| G Single sloped row | Abstains: one corrected ink run | Page-global support is insufficient |
| H Sloped rows plus small outliers | `+.0345` for `+.035` | Outliers do not drag the estimate |

The other prototype, which merely removes the singleton veto from the token
cohesion search, is not robust: it returns `+.043` for synthetic `+.080`, zero
for known `+.030` and `+.035` cases, `+.086` for a single `+.050` row instead
of abstaining, and merges the competing nearby rows in E. Its F result is zero
with fragmented rows rather than an explicit disagreement state.

## F. Candidate estimator comparison

Two candidates were compared while holding the OCR capture, horizontal gap
predicate, tolerance, `_line_bands`, horizontal splitting, grouping, and
assignment/reconciliation implementation fixed:

1. **Cohesion without singleton veto:** retains the two-multi-token-region
   and strict-score-improvement requirements, but permits singleton regions.
2. **Pixel row median:** median of three independent, human-adjudicated
   scan-pixel row fits. It abstains to zero when measured trend is under two
   pixels across the page width. This is an evaluation oracle requiring row
   selection; it is not an automatic production estimator.

`group_physical_lines` itself was called unchanged. Only its slope selector
was temporarily replaced inside a research wrapper; the original function is
restored in `finally`. Candidate line output, ambiguity, unassigned tokens,
bounds, and line counts are preserved in `results.json`.

The pixel-row candidate changes groupings on six sides: Relativity 10 left
and right, Relativity 17 left, both Relativity 23 sides, and Stella Maris 6
right. The no-singleton-veto candidate changes several
additional near-horizontal pages despite pixel evidence for zero. Across both
candidates, identity-complete changed transitions are adjudicated in
[`adjudications.json`](adjudications.json):

- `repaired_false_split`: 37
- `destructive_merge`: 0
- `new_false_split`: 8
- `benign_difference`: 0
- `unresolved`: 1

The eight new false splits include the final “yet” in a visually continuous
Relativity 10 left row; the Relativity 17 heading; a continuous sentence on
Relativity 23 right; and continuous dialogue/prose rows on Stella Maris 3 and
6. The unresolved event is a Relativity 23 left display-math expression whose
raised components do not establish one physical baseline. Every event record
contains the complete source-row identities, token boxes, production and
candidate groups, both slopes, physical pixel evidence, visual adjudication,
and classification. OCR wording remains locator evidence only.

## G. Real changed-event adjudication

There are 46 unique identity-complete transitions after deduplicating identical
group changes made by the two candidates. The 37 repaired transitions are
horizontal pieces that the current zero grouping left in separate regions
but the scan shows on one continuous printed row. The 8 false splits show
tokens on one printed row separated or left unassigned by substituted slope.
No changed event joins visibly distinct printed rows. The math event remains
unresolved rather than being decided by token count or line count.

Historical residual locators on Relativity 10 left (`system`, `that`, `the`,
`with`, `respect`), Relativity 10 right (`impossible`), and Relativity 17
right (`A`) are not used as a success measure. Their deterministic assignment
state is not treated as correctness; this study adjudicates changed group
events against pixels instead.

## H. Stability and scale

- **Permutation:** all 11 primary pages retained the same production slope,
  relaxed-cohesion slope, pixel-row measurements/median, and pixel-candidate
  grouping after a seeded input shuffle (`20260928`).
- **One-pixel perturbation:** one locator token per page was shifted `y + 1`
  while the raster stayed fixed. Production and relaxed-cohesion slopes did
  not change on any side. Pixel row fits changed on 8/11 sides and the median
  pixel measurement changed on 5/11, but the pixel grouping/assignment state
  did not change on any side. This separates measurement sensitivity from
  changed identity assignments.
- **Resolution boundary:** the research pixel candidate abstains below two
  pixels of estimated baseline displacement across page width. Synthetic
  cases immediately around that boundary changed the reported selected value
  from zero to `0.00375`; grouping and assignment remained unchanged in these
  cases. The policy and raw measurements are explicit, but a binary boundary
  remains a model choice, not a discovered physical constant.
- **Scale:** nearest-neighbor synthetic scales `0.5×`, `1×`, `2×`, `3×`
  estimated `0.04025`, `0.03900`, `0.03875`, `0.03900` for a known `0.040`
  slope. This is exploratory, not a DPI contract.

## I. Blank-side diagnostics

`stella_maris_pdf03_session-I.left` was processed and OCR was called once. It
is `545 × 813` px, has zero admitted tokens, selected slope `0.0`, no candidate
search, no bands, and no pixel orientation support. It is excluded from all
primary counts. Blank-page suppression remains separate.

## J. Historical residual locators

The previously named Relativity 10 and 17 residual tokens remain secondary
locators only. No candidate is credited for assigning them. A changed token
counts as repaired only where its physical row is independently visible and
adjudicated; all other cases retain uncertainty in the event ledger.

## K. Final decision

**Candidate failure topology requires further research.** Current zero is
physically wrong for the measured row trends on eight sides, and its
selection mechanism is causally identified. Neither tested substitute meets
the unchanged acceptance bar: there are eight new false splits and one
material unresolved event, while the geometry-only candidate also fails
synthetic merge/abstention counterexamples. The pixel-row prototype depends on
human-selected row locators and is not yet an automatic estimator.

Do not implement this decision in production. A next experiment would need an
automatic, source-independent row-support estimator that carries explicit
abstention through the grouping interface and does not create those splits.
That is a future proposal, not a result of this task.

## L. Verification and provenance

- Baseline authority: `guh` at `473e639b6fe335ffb527d2338234d38e311189ba`;
  research branch descended directly from that commit.
- Environment: `.venv/bin/python` 3.12.3, pytest 9.1.1, project imports
  passed, Tesseract 5.3.4. All six exact local PDFs were present.
- Full repository suite: **188 passed, 1 skipped**.
- Focused slope research tests: **14 passed**.
- All six fixtures preprocessed at 144 DPI; all 12 sides captured once by
  OCR; baseline geometry and both candidate comparisons used those same
  admitted records.
- Protected source/config/expectation SHA-256 values and source PDF/image/TSV/
  token hashes are in `results.json`; protected production files match `guh`.
- Production geometry, preprocessing, OCR behavior, horizontal gap logic,
  reconciliation, and structural expectations were not modified.
- `git diff --check` and `git ls-files '*.png' '*.pdf'` are required before
  commit; no raster or PDF is committed.
- The first source-inspection-only commit remains in branch history. The final
  completed research commit is reported separately after verification.
