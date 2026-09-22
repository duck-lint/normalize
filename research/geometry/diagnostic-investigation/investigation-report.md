# Sparse connectivity and vertical fragmentation investigation

This report records current behavior and counterexamples. It does not propose
that any observed behavior be corrected in production, and it does not treat
synthetic pixels as evidence about the scanned books.

## A. Baseline and provenance

The investigation started from the clean commit
`6453d2890fce5799640d7219effdd090ea6aed2d` on
`geometry-forensics-identity-oracle`. The prior residual-forensics manifest
contains 27 artifacts; all recorded hashes and sizes verified before this
investigation. The `.gitignore` file matches that commit.

The isolated branch is `diagnostic-investigation-sparse-vertical`. Production
geometry is imported from
`src/normalize/geometry.py`; the identity-complete oracle remains
`tests/geometry_oracle.py`. The execution environment and every new artifact
hash are in `manifest.json`. Existing scan-derived evidence is referenced from
`research/geometry/residual-forensics/`; it is not duplicated.

The new diagnostic command is:

```text
.venv/bin/python research/geometry/diagnostic-investigation/investigate.py
```

It emits `diagnostics.json` and seven small schematic pixel cases. The JSON
contains the complete identity-canonicalized outputs, raw greedy-band traces,
post-horizontal-split bands, all final candidate checks for every residual
token, and the observed Relativity 17 `lightning A` reference.

## B. Sparse horizontal connectivity

### Current predicates

For one page's admitted tokens, the current implementation computes:

1. `gap_limit = max(1, 2 * median(token_widths))`.
2. A token is oversized when `width > 1.5 * gap_limit`, equivalently more
   than three page-local median token widths.
3. Ordinary tokens form horizontal components when the next token's left edge
   is no more than `gap_limit` beyond the current covered right edge.
4. A wide token is a supported bridge only when ordinary components exist on
   both sides, the wide box covers the interval between them, and each side
   contains at least two ordinary tokens.
5. During region splitting, an unsupported wide token may start a region but
   its full right edge is deliberately not added to covered extent. The
   final candidate guard repeats the unsupported-bridge rejection.

This is a box-topology rule. It does not inspect ink pixels, OCR confidence,
token wording, or the semantic identity of a long word.

### Synthetic case results

The cases below are in `diagnostics.json`; the pixel sketches are in
`pixel-cases/`. Identity-complete canonicalization was run on every case and
all reversed-token inputs produced the same complete assignment state.

| Case | Box arrangement | Current output | Physical reading supported by the case | Finding |
| --- | --- | --- | --- | --- |
| One ordinary token each side | one ordinary box, one wide box, one ordinary box | 2 regions; wide box stays with left | A one-token-per-side bridge is insufficiently supported | Abstention can be justified, but a visibly continuous line is falsely split |
| One-sided left support | two ordinary boxes before the wide box | 1 region | No evidence exists beyond the wide box | No bridge claim is licensed; current result is local adjacency only |
| One-sided right support | wide box before two ordinary boxes | 2 regions; one right token is ambiguous | Same evidence as the left-sided case, reversed | Left-to-right construction is asymmetric for an unsupported wide starter |
| Two ordinary tokens each side | two ordinary components, wide box, two ordinary components | 1 region | Box predicate treats the wide box as supported | Correct for a continuous row; potentially a false merge for disconnected pixels |
| Genuine long printed word | ordinary, genuinely long word box, ordinary | 2 regions | The long word is one printed token in one row | False split: width alone cannot distinguish a long word from a bridge artifact |
| OCR rectangle over disconnected regions | same boxes as the two-sided case, but blank central pixels | 1 region | The only cross-gap evidence is the wide OCR rectangle | False merge: exact same boxes as the continuous-box case yield identical output |
| Sparse visibly continuous line | exact same boxes as the one-token-each-side case, with a visible central stroke | 2 regions | Pixel evidence supports one physical line | False split: exact same boxes as the blank-gap interpretation |

The two strongest indistinguishability results are:

- `one_ordinary_token_each_side` and `sparse_visibly_continuous_line` have
  identical boxes and identical assignments despite different pixel evidence;
- `two_ordinary_tokens_each_side` and
  `ocr_rectangle_over_disconnected_regions` have identical boxes and
  identical assignments despite different pixel evidence.

Therefore bounding boxes alone are not sufficient to determine continuity in
either direction. The current two-sided bridge rule is a defensible
conservative guard against sparse OCR spans, but it is not a physical
continuity test. Loosening it to admit one ordinary token per side would
recover the sparse continuous synthetic case while also admitting the
one-token disconnected counterexample and the genuine-long-word ambiguity.

### Relativity 17 observed example

The preserved crop
`research/geometry/residual-forensics/relativity_pdf17_pp40-41/crops/right-row-0023-a.png`
shows the end of `lightning` and the residual token `A`. Its stable identity
is `(relativity_pdf17_pp40-41, right, 23)`, and its current state is
`ambiguous_line_assignment` with candidates `line-0003` and `line-0004`.
This is an observed example of the uncertainty boundary, not a special-case
specification. The investigation does not authorize changing the bridge rule
to make it resolve.

## C. Vertical-band fragmentation

### Current path

The current vertical path is:

1. The page median token height determines
   `tolerance = max(1, floor(median_height / 4 + 0.5))`.
2. Adjusted center is `center_y - slope * x`; the bounded slope search is run
   before grouping.
3. Tokens sorted by adjusted center are added greedily to the current raw
   band when the token is within the current band median or has a horizontally
   adjacent token within tolerance.
4. Raw bands are split horizontally using covered extent and the oversized
   bridge guard.
5. Final reconciliation considers every post-split band. A token is a
   candidate when either it is in that band and has vertical/neighbor support,
   or it is vertically within tolerance, its x lies inside the band's x
   interval, and the horizontal candidate guard passes.
6. One candidate resolves; multiple candidates remain ambiguous; no
   candidates become unassigned.

The trace records preserve both the raw greedy band and the later split bands.
That distinction matters: a raw band can grow through local neighbor support,
then its final median can move beyond the token's tolerance after other tokens
are admitted.

### Relativity 10 per-token traces

The page median height is 16 px, so tolerance is 4 px and slope is 0. The
source-independent trace details are in `diagnostics.json`; the causal summary
is:

| Token | Adjusted center | Raw/provisional evidence | Neighboring-band result | Final state |
| --- | ---: | --- | --- | --- |
| `system` row 213, left | 959.0 | Raw greedy band median 954.5; after horizontal splitting it is in `line-0047`, whose median is 954.5; delta is 4.5, just outside tolerance | `line-0048` is vertically near at median 956.5, but the token's x=297 lies beyond that band's right extent 286; horizontal guard otherwise passes | Unassigned |
| `that` row 216, left | 954.5 | Provisional `line-0046`, median 953.25, delta 1.25 | `line-0047`, median 954.5, passes the second candidate clause; both candidate bands have interval and horizontal support | Ambiguous: `line-0046`, `line-0047` |
| `the` row 217, left | 954.5 | Same raw/provisional and final checks as `that` | Same | Ambiguous: `line-0046`, `line-0047` |
| `with` row 226, left | 985.0 | Provisional `line-0050`, median 982.0, delta 3.0 | `line-0049`, also median 982.0, passes the second candidate clause | Ambiguous: `line-0049`, `line-0050` |
| `respect` row 227, left | 982.0 | Provisional `line-0050`, delta 0 | `line-0049` also passes the second candidate clause | Ambiguous: `line-0049`, `line-0050` |
| `impossible` row 246, right | 746.5 | Raw/provisional `line-0054` median 752.25, delta 5.75 | Nearby `line-0053` median 742.0, delta 4.5; neither supplies a valid vertical-and-horizontal candidate | Unassigned |

The `system` trace is the clearest interaction: the pre-split greedy band
contains rows `[219, 218, 214, 215, 216, 217, 212, 211, 213]`. Local
horizontal-neighbor support admits `system`, but horizontal splitting later
creates a region whose final median moves 0.5 px beyond tolerance. This is
evidence for an interaction between greedy band growth and later horizontal
fragmentation, not evidence that a global tolerance increase is safe.

### Relativity 17 `A`

The page median height is 16 px, tolerance is 4 px, and slope is 0. `A` has
adjusted center 132.0. It forms a one-token provisional band `line-0004` at
132.0. The preceding text band `line-0003` has median 131.5 and includes
`lightning`; `A` lies within its x extent and passes the horizontal candidate
guard. Both candidates are therefore retained. The visible crop supports a
same-line reading, but the box geometry also supports the neighboring
one-token band, so the current uncertainty is internally consistent with its
declared evidence.

### Source-independent vertical cases

The diagnostic cases include:

- a continuous row: three close, horizontally supported tokens resolve to one
  line;
- nearby distinct rows: two separated horizontal rows remain two lines;
- legitimately ambiguous same-column geometry: centers `(20, 25, 26, 29)`
  yield an ambiguous middle token rather than an invented resolution.

The identity-complete oracle passes under reversed token input for all three.
The ambiguous case demonstrates why simply considering more nearby bands or
raising tolerance can create false merges: same-column boxes have no
horizontal adjacency evidence to choose between nearby rows.

## D. Hypothesis matrix

| Mechanism | Established behavior | Contradictory evidence / counterexample | Falsification experiment |
| --- | --- | --- | --- |
| Wide-box bridge guard | Requires coverage plus at least two ordinary tokens on each side | Genuine long words and sparse continuous lines are split; disconnected regions can merge when two-sided support exists | Supply real scan pixels with identical OCR boxes and measure whether pixel-connectedness separates the cases without increasing column merges |
| Bounding-box continuity as physical continuity | Deterministic and permutation-stable | Exact same boxes produce different physical interpretations under different pixels | Add connected-component or ink-gap evidence and test continuous/disconnected pairs across fixtures |
| Greedy raw vertical band growth | Local median/neighbor support can admit tokens before the eventual median is known | `system` is admitted into a raw band, then fails the post-split final tolerance | Compare frozen raw-band membership with component-level clustering on adversarial center chains; require no new false merges |
| Fixed median-height tolerance | Explains the 0.5 px and 1.75 px boundary misses | Increasing tolerance would also admit nearby distinct same-column rows | Sweep tolerance on synthetic close rows and real residuals; evaluate complete assignment and uncertainty, not counts alone |
| Final second candidate clause | Correctly exposes `that/the`, `with/respect`, and `A` as ambiguous | It cannot resolve a token when x interval or vertical tolerance fails, as with `system` and `impossible` | Perturb only x extent or center by one pixel and verify candidate transitions are monotonic and physically justified |
| Slope estimation | Slope is 0 for all residual pages examined | No residual here distinguishes slope failure from other mechanisms | Re-run the trace on controlled sloped rows with multiple horizontal bands and compare zero/nonzero slope decisions |

No hypothesis is licensed as a production correction by this evidence alone.

## E. Generalization requirements

A source-independent geometry change would need evidence that it:

- preserves the identity-complete oracle and complete candidate/uncertainty
  state under token permutation;
- distinguishes ordinary long words, OCR-spanning rectangles, sparse continuous
  lines, and disconnected regions without using source wording as geometry
  authority;
- treats one-sided support as insufficient for bridge admission unless an
  independently justified pixel or structural signal exists;
- prevents raw-band median drift from changing final membership after
  horizontal fragmentation, or explicitly preserves the resulting uncertainty;
- keeps same-column nearby rows ambiguous when horizontal evidence cannot
  discriminate them;
- is evaluated on both false merges and false splits, not merely successful
  fixture counts;
- records scaling behavior as exploratory unless the project contract is
  explicitly extended with a scale guarantee.

The minimum regression matrix is the seven horizontal cases, the three
vertical synthetic cases, all seven preserved residual identities, the sparse
oversized-rectangle test already in Slice 2, and the six existing fixtures.

## F. Proposed next implementation boundary

Further evidence is needed before a production correction. The smallest
justified next boundary is a separately evaluated prototype with two isolated
questions:

1. Can scan-pixel connectedness or a similarly authorized layout measurement
   distinguish the identical-box continuous/disconnected pairs without
   treating OCR text as authority?
2. Can a non-greedy or component-level vertical model prevent post-split
   median drift while retaining uncertainty for same-column near rows?

The risks are asymmetric: loosening horizontal bridges increases false merges,
while broadening vertical tolerance increases false merges between nearby
rows; aggressively splitting reduces merges but increases false splits in
sparse or noisy OCR. Acceptance should require complete assignment-state
comparisons, counterexamples for each failure mode, and no production change
until the pixel and vertical hypotheses are independently falsified or
supported.

## Scope

This branch adds only `research/geometry/diagnostic-investigation/` and does
not modify production geometry, the identity-complete oracle, fixture
expectations, source PDFs, acceptance criteria, Slice 1, downstream
reconstruction, or SYMPHONY. No dependencies were installed.
