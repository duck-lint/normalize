# Local slope support failure-topology study

## Decision

**Local support improves safety but sacrifices some repairs; further validation required.** The local gate abstains on the unresolved display-math event and blocks four of the seven distinct harmful physical contexts represented by the eight prior `new_false_split` transition records. But it still produces three prior harms and creates three new false splits in rows the earlier study had adjudicated as repairs. There are six distinct false-split physical contexts in the local result. The one-pixel test also changes the gate and grouping for one event, and leave-one-token deletion changes the support decision in nine event records.

The key result is that the harm is not simply a lack of local slope evidence. Several harmful changes have stable, same-row pixel slope support. In those cases, the physical slope is supported while applying it to OCR box centers still fragments one printed row. A local support test alone does not make the downstream center-and-tolerance rule safe.

No production experiment is authorized. Production geometry is unchanged.

## A. Prior-event corpus and provenance

The input is exactly the 46 preserved event IDs from commit
`29428360e4b31853a36058c39795e072718fdc91`:

- `repaired_false_split`: 37 records;
- `new_false_split`: 8 records;
- `unresolved`: 1 record.

Event boxes were checked against the once-captured admitted-token geometry;
all 46 event records match the prior event ledger and its pixel adjudications.
The prior labels were not changed. Every source-row identity maps to one
physical token context. There are **45 distinct physical token contexts**:
the two Relativity 17 left heading outcomes, events 031 and 032, have the same
four source rows but different candidate estimator outputs. Both event IDs
remain in the record and share one physical evidence context.

Each event carries its fixture/side, source rows, token boxes, production and
prior pixel-candidate partitions, prior global candidate slope, image/PDF/
token hashes, local pixel measurements, and local full-page grouping result.
The exact per-event evidence is in [`adjudications.json`](adjudications.json).

## B. Measurement model and failure topology

The local measurement uses current 144-DPI production-cropped pixels. Token
rectangles locate the pixel samples; OCR text, confidence, Tesseract line
labels, and fixture identity do not enter the measurement or decision. For
each token, the method takes the 90th-percentile dark-pixel y within its box
plus a two-pixel locator margin, then estimates slope with Theil–Sen over
those pixel landmarks. It separately records box-center slope, per-20-pixel
lower-envelope slope, per-bin ink-median slope, residuals, three horizontal
segment fits, leave-one-token and leave-one-subregion ranges, local curvature
proxies, and nearby-row context.

No formal confidence interval is claimed. Token landmarks are not independent
random samples: letter shapes within words, box clipping, and rasterization
make a conventional statistical interval unjustified. Leave-one-support
ranges and residuals are descriptive stability evidence, not confidence
probabilities.

The class feature distributions overlap. Medians below are across transition
records (so the duplicate heading context appears twice):

| Prior class | Tokens, median (range) | X span, median (range) | Page-width fraction, median (range) | Pixel-fit median absolute residual, median (range) | Leave-one-token slope spread over span, median (range) |
|---|---:|---:|---:|---:|---:|
| Repaired false split (37) | 9 (4–13) | 514 px (184–606) | 0.926 (0.294–0.954) | 0.227 px (0–0.647) | 0.765 px (0–4.089) |
| New false split (8) | 4 (1–8) | 315 px (5–516) | 0.541 (0.008–0.947) | 0.219 px (0.049–0.407) | 0.918 px (0.828–2.253) |
| Unresolved (1) | 3 | 129 px | 0.241 | 0 px under this proxy | 35.019 px |

The distributions do not provide a separating support property. Repair cases
are generally longer and denser, but harmful cases include an eight-token
row spanning 516 px and a four-token heading spanning 398 px with low residual
and stable leave-one-out fits. Residual distributions are nearly the same.
Local slope magnitude also overlaps: strong, coherent sloped rows occur among
both repaired and harmful outcomes. A minimum token count or span can abstain
on the one-token case, but cannot block the well-supported harmful cases.

Box and pixel slopes disagree on some events and agree on others; no forced
agreement is imposed. The event records retain the exact trend disagreement
in pixels. The nearest separately sampled text-row slopes are often over
100 px away and are not treated as same-row authority. Neighbor expansion
increases the amount of ink but often drives the measured median slope toward
zero or changes it materially; those pixels cannot be attributed to the event
row. Event-only and candidate-band scopes coincide for this corpus. Broader
local-x and neighboring-row scopes are diagnostics only.

## C. Local support rule

The evaluated rule is a geometry-only gate, frozen before reading its final
class outcomes:

1. At least three independent token-local pixel lower-edge landmarks must be
   measurable.
2. A robust line fit must have median absolute residual at most 2 px.
3. Re-fitting after deletion of any one landmark must keep total predicted
   slope spread across the event x-span at or below 4 px.
4. If the stable trend is under 2 px across the event span, reject applying a
   slope and use zero. If these support conditions are insufficient or
   unstable, abstain. Otherwise apply the local Theil–Sen slope.

The two- and four-pixel budgets are raster-scale allowances at the captured
144-DPI resolution. No page-specific or lexical branch exists. The rule does
not use class labels, fixture names, heading/dialogue/equation categories, or
whole-page slope consensus.

An earlier equal-third rule was discarded after synthetic controls: the
horizontal third fits abstained on a known variable-height row even though
per-token pixel lower edges recovered its baseline. V2 instead treats each
located token region as a support landmark. Its remaining failure on real
pages is consequential: stable baseline evidence can coexist with harmful
grouping when box centers, rather than ink baselines, are sheared and compared
to the unchanged vertical tolerance.

## D. Prior eight false splits, individually

The eight transition records contain seven physical row contexts because the
Relativity 17 heading appears under two candidate slopes. Pixel crops show one
continuous printed row in every case. The exact source rows, boxes, before/
after groups, support values, and row-level causal notes are in the event
ledger.

| Event | Local evidence and change | Causal finding |
|---|---|---|
| Relativity 10 left `.event-003` | 8 tokens, 516 px span; local pixel slope `−0.01736`; residual 0.05 px; leave-one-token trend spread 1.01 px. Local grouping isolates source row 77 from rows 70–76. | The scan supports the applied slope and the line remains visually continuous. The candidate shear moves box-center coordinates so the last token falls outside the effective band tolerance. Slope evidence is not missing or wrong in direction; the center/tolerance representation is insufficient. |
| Relativity 17 left `.event-031` | 4 heading tokens, 398 px; local slope `+0.01475`; residual 0.22 px; leave-one-token spread 0.85 px. Cohesion slope was `+0.027`; it omitted source row 11. | The `+0.027` cohesion slope is too steep. Yet the pixel-supported `+0.01475` local slope also partitions one printed heading into three groups. Box-center slope is `+0.02167`; varying box heights distort center comparisons. |
| Relativity 17 left `.event-032` | Same four tokens and same pixel measurements as `.event-031`; prior pixel candidate was `+0.01520`. Local groups are `[9]`, `[10,12]`, `[11]`. | This is the second estimator outcome for the same heading, not independent evidence. The physical slope agrees with independently measured page text direction, but the unchanged center/tolerance grouping still fragments the title. |
| Relativity 23 right `.event-035` | 4 tokens, 318 px; local slope `−0.00771`; residual 0.12 px; leave-one-token spread 0.83 px. Local groups are `[114,115]`, `[116]`, `[117]`. | The local fit is internally coherent, but support from four word boxes does not establish that this exact magnitude is the glyph baseline. Shearing also joins source rows 110–113 with 114–115; scan pixels show 110–117 are one continuous row, so this is a partial repair of the same row plus a remaining split, not a merge of distinct rows. |
| Stella Maris 3 right `.event-037` | 6 tokens, 299 px; cohesion candidate `−0.011`; local pixel lower-edge fit `+0.00552`, while the pixel-bin fit is zero. | Candidate direction conflicts with the event-local pixel trend. The local trend is only 1.65 px over the event span, below the 2 px floor; rejecting slope blocks this false split. |
| Stella Maris 3 right `.event-038` | One token, 5 px x-span; no local slope fit is available. The broad candidate leaves it unassigned. | A single token cannot establish line orientation. Event-only support must abstain. Borrowing adjacent text would risk letting another row supply the slope. |
| Stella Maris 6 right `.event-041` | 4 tokens, 230 px; candidate slope `+0.001`; local pixel slope `−0.00631`, only 1.45 px across the event. Box-center slope is `−0.01578`. | The candidate trend is negligible; the pixel fit does not clear the minimum resolvable displacement. Box-height variation makes box centers a poor baseline proxy here. Rejecting slope preserves the production grouping. |
| Stella Maris 6 right `.event-042` | 7 tokens, 312 px; prior page slope `−0.00846`; local pixel slope `−0.00428`, 1.34 px across the event; box-center slope is `+0.01056`. | Local pixel support does not justify the steeper page slope for this region. The candidate isolates source row 267; rejecting it preserves the visible row. |

The split mechanism is not uniform across these cases. Some applied slopes are
strongly supported but still fragment a row; some broad candidate slopes are
unsupported locally and can be blocked; one token has no measurable local
orientation. A single threshold on x-span, token count, residual, or neighbor
agreement cannot cover all three topologies.

The per-case causal questions resolve as follows. “Neighbor” numbers below are
the nearest separately adjudicated page-row sample; where its vertical
distance is over 100 px it is contextual, not immediate-neighbor support.

| Event | Production grouping → prior changed grouping; affected IDs | Was local slope wrong? Support size / height variation | Neighbor, fit shape, honest local decision |
|---|---|---|---|
| Relativity 10 left `.event-003` | `[70–77]` → `[70–76]`, `[77]`; source 77 crossed the band boundary. | No: local `−0.01736` agrees with prior page evidence `−0.01642`. 8 tokens, 516 px; heights 11–22 px. | Nearest sample `−0.01642`, 57 px away. 0.05 px residual; no curvature signal. Gate applies and reproduces the harm: support cannot prevent box-center/tolerance split. |
| Relativity 17 left `.event-031` | `[9–12]` → `[9,10,12]`; source 11 is lost. | Cohesion `+0.027` is too steep versus local `+0.01475`. Four tokens span 398 px; heights 25–33 px. | Nearest sample `+0.01520`, 106 px away; low 0.22 px residual. Gate applies because pixel baseline is supported; the candidate still splits. |
| Relativity 17 left `.event-032` | `[9–12]` → `[10,12]`, `[11]`, `[9]`; same physical heading as `.event-031`. | Prior pixel slope `+0.01520` and local `+0.01475` agree. Same 4-token, 398 px, 25–33 px support. | Same nearest sample and residual. Gate applies; box-center variation creates three groups. |
| Relativity 23 right `.event-035` | `[114–117]` → `[114,115]`, `[116]`, `[117]`; 116 and 117 remain apart. | Local `−0.00771` is internally stable, but four token landmarks do not prove the exact baseline magnitude. Span 318 px; heights 15–17 px. | Nearest sample `−0.00259`, 115.5 px away; 0.12 px residual and no strong curvature signal. Gate applies. Full-page run also joins 110–113; pixels show those are the same continued printed row, so the merge is not destructive. |
| Stella Maris 3 right `.event-037` | `[70–75]` → `[70–74]`, `[75]`; source 75 separates. | Candidate `−0.011` has opposite sign to local pixel `+0.00552`; local trend is only 1.65 px over 299 px. Six tokens, heights 16–20 px. | Nearest sampled slope `−0.00047`, 228 px away; no immediate-row corroboration. Residual 0.34 px; gate rejects the candidate trend below its 2 px floor. |
| Stella Maris 3 right `.event-038` | `[111]` → unassigned; only source 111 is involved. | No slope is identifiable from one 5 px-wide token. Height 16 px. | Nearest sampled row is 130.5 px away and cannot establish this token's baseline. No line fit or curvature estimate exists; gate abstains. |
| Stella Maris 6 right `.event-041` | `[246–249]` → `[246]`, `[247–249]`; source 246 separates. | Candidate `+0.001` gives only 0.23 px trend. Local `−0.00631` gives 1.45 px; four tokens span 230 px, heights 11–22 px. | Nearest sample `−0.00846`, 228.75 px away; local fit residual 0.09 px, but box-center slope `−0.01578` disagrees. Gate rejects the unresolved sub-2 px trend. |
| Stella Maris 6 right `.event-042` | `[261–267]` → `[261–266]`, `[267]`; source 267 separates. | Page candidate `−0.00846` is steeper than local `−0.00428` (1.34 px over 312 px). Seven tokens, heights 10–17 px; box-center slope is opposite at `+0.01056`. | Nearest sample `−0.00878`, 226.75 px away, not an immediate neighbor. Local residual 0.41 px; support does not clear the 2 px trend floor, so gate rejects the page slope. |

For the three strong-support harms (Relativity 10 left, both outcomes of the
Relativity 17 heading, and Relativity 23 right), neither sparse support nor
nonlinearity is the explanation. Their pixel rows are coherent and the fitted
directions are plausible. The false split enters when the grouping mechanism
shears token **box centers** and checks them against a fixed tolerance; box
centers include glyph-height variation and are not themselves baseline
observations. A local slope gate sees the right physical orientation but does
not repair that representation mismatch.

## E. Unresolved display-math event

Relativity 23 left `.event-034` remains `unresolved`. It has three source
identities spanning 129 px. The event-local lower-edge proxy returns
`+0.03444`, but its leave-one-landmark slope range implies about 35 px of
trend disagreement over the support, and box-center versus pixel trend differs
by about 10 px. The crop contains a radical, fraction bar, superscript, and
multiple vertical levels. A single ordinary text baseline is not established;
the proxy slope is not a justified line orientation. The gate abstains.

Resolution would require a physical interpretation of the printed formula's
components (which marks share baselines and which belong to numerator,
denominator, or superscript structure). More regression on the same three
token boxes cannot supply that relation.

## F. Local-scope comparison and real-event results

The local shear is applied only to the event's token identities. All other
tokens stay in the zero-slope frame. The actual full-page production
`group_physical_lines` path runs unchanged, including horizontal gap handling,
candidate assignment, and reconciliation. Monkey patches are restored in a
`finally` block. The event ledger records event partitions, assignment state,
and every outside-event identity whose group changed.

| Prior class | Records | Apply | Reject | Abstain | Correct repair retained | Harmful split in local result | Original false split preserved | No repair attempted / unresolved |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Repaired false split | 37 | 34 | 2 | 1 | 29 | 3 new false splits | 4 | 1 abstention |
| New false split | 8 | 4 | 3 | 1 | — | 4 event records / 3 physical contexts | — | 4 blocked |
| Unresolved | 1 | 0 | 0 | 1 | — | — | — | 1 preserved |

Across unique physical contexts, the local result is 29 retained repairs,
6 false-split contexts, 4 blocked prior harmful contexts, 4 prior production
false splits preserved, 1 repair not attempted, and 1 unresolved context
(45 contexts total). The 6 false-split contexts comprise three prior harmful
contexts that still pass the gate and three new harms among the former repair
cases. The eight prior harmful transition records include the duplicate
heading outcome, hence the record/context count difference.

The three additional false splits are:

- Relativity 10 right `.event-024`: stable local slope `−0.03469`; one visible
  row becomes groups `[32–36]`, `[37,39]`, `[38,40]`.
- Relativity 17 left `.event-027`: stable local slope `+0.01862`; one visible
  row leaves source rows 167 and 168 separate.
- Stella Maris 3 right `.event-036`: stable local slope `−0.00561`; one visible
  row leaves source rows 112 and 118 separate. The sampled comparison row is
  129 px away, so its different orientation cannot by itself invalidate this
  local measurement.

These cases answer the central question directly: local baseline support can
be strong and still not justify the *grouping result* produced by applying
that slope to OCR box centers. For event `.event-035`, a supported shear also
changes source rows 110–113, but pixels show those tokens continue the same
printed row as 114–117. No destructive merge of visibly distinct rows was
observed; the side effect is a partial same-row repair alongside a remaining
split.

## G. Synthetic falsification and holdouts

The frozen v2 rule was tested on generated pixel geometry without page text:

| Case | Outcome | Result |
|---|---|---|
| A. Long clean sloped row (`+0.035`) | Apply `+0.03467` | Direction/magnitude recovered. |
| B. Short clean row (`+0.050`) | Apply `+0.04444` | Three independent token landmarks suffice in this generated case; shortness alone does not force abstention. |
| C. Sparse broad row (`−0.030`) | Apply `−0.03000` | Wide support preserves identifiability with three sparse landmarks. |
| D. Curved row | Abstain | Leave-one-token instability exposes nonlinearity. |
| E. Two nearby rows, same slope | Abstain | Combined lower-edge residual exposes multiple baselines; rows remain separate. |
| F. Two nearby rows, different slopes | Abstain | Residual and deletion instability expose disagreement. |
| G. One token / two tokens | Abstain | Orientation support is insufficient. |
| H. Variable-height boxes, one physical baseline | Apply `+0.03333` | Pixel lower edges recover the row despite center-height variation. |
| I. One displaced box | Apply `−0.02929` | Robust fit tolerates this generated outlier. |
| J. Display-like multiple baselines | Abstain | Large residual preserves uncertainty. |
| K. Supported horizontal row | Reject slope, use zero | No nonzero trend is demonstrated. |

All synthetic oracle cases pass their declared decision expectation. This is a
small designed matrix, not evidence of broad generalization. Leave-one-event
out (46 runs) and leave-one-page-side-out (10 sides) were run without fitting
parameters: the fixed rule's decisions remain unchanged by construction. These
checks show no label-trained threshold, but they are not predictive validation
on unseen documents.

## H. Stability and scope

- **Permutation:** 46/46 event measurements, decisions, local groupings, and
  assignments are invariant to seeded token shuffling.
- **One-pixel locator perturbation:** shifting event boxes `y + 1` changes the
  selected slope estimate on 4/46 records. One additional record,
  Relativity 10 right `.event-025`, crosses the leave-one-token stability gate;
  support decision and grouping change, while assignment state does not.
  The full boundary values before/after are recorded in `results.json`. This
  is a real threshold sensitivity, not silently called stable.
- **Support deletion:** 9/46 event records change support decision when at
  least one support token is removed (357 token deletions total). The affected
  IDs and each deletion are listed in the results artifact. This instability
  includes the duplicate heading context.
- **Threshold boundaries:** every event records its distance to the 3-landmark,
  2 px residual, 4 px leave-one-out spread, and 2 px trend boundaries.
- **Scale:** a generated `+0.035` row estimates `+0.03487`, `+0.03467`,
  `+0.03467`, and `+0.03467` at `0.5×`, `1×`, `2×`, and `3×`. Fixed pixel
  budgets mean this is exploratory, not a DPI invariance claim.
- **Scope:** event-only and candidate-band measurements are identical here.
  Expanding to local-x neighborhoods and neighboring rows increases token
  support but changes the estimated slope toward zero or reverses it. Those
  scopes can mix physical rows and do not authorize event slope.

## I. Cost of abstention

The gate retains 29/37 prior repairs. Eight do not remain repaired: four
return to the production partition, one is explicitly not attempted, and three
become new false splits under the applied local shear. On the prior harmful
set, three physical contexts remain harmful, while four are blocked by reject
or abstain. This is a safety gain over broad application, but it does not meet
the zero-new-false-split requirement.

## J. Model comparison

| Model | Repairs | New false splits | Destructive merges | Unresolved / abstained |
|---|---:|---:|---:|---:|
| A. Current production zero slope | 0 of these candidate changes | 0 candidate-induced | 0 observed | Existing production grouping retained; formula interpretation remains unresolved. |
| B. Prior broad pixel-row slope | 37 | 8 transition records | 0 | 1 |
| C. Local support gate v2 | 29 retained | 7 local-result event records / 6 physical contexts | 0 observed | 1 formula abstention; 1 repair not attempted |

Model A preserves the existing false splits that the broad candidate had
repaired; it does not assert that the measured physical rows are horizontal.
Model B contains a duplicate heading transition context as described above.
Model C's extra harms arise even where local pixel fits are linear and stable.
No model is ranked by token assignment count.

## K. Decision

**Local support improves safety but sacrifices some repairs; further validation required.** The rule blocks four distinct prior harmful contexts and abstains on
the formula, but it also permits three harmful contexts and creates three new
false splits. The best-supported failure topology is a mismatch between
physical ink baselines and OCR bounding-box centers under a fixed vertical
tolerance. Local evidence can license a physical orientation estimate; it
does not guarantee that applying that orientation to the current token-center
representation preserves printed-row membership.

Do not implement production changes from this study.

## L. Verification and provenance

- Prior commit verified locally; branch created from
  `29428360e4b31853a36058c39795e072718fdc91`.
- All local raster hashes match prior production captures. OCR was not rerun;
  the same admitted token capture is reused. No PNG/PDF was added.
- Focused local-support plus relevant geometry tests: **77 passed**.
- Prior slope-forensics tests: **14 passed**.
- Full repository suite: **188 passed, 1 skipped**.
- Production geometry, preprocessing, OCR, crop configuration, horizontal
  grouping, reconciliation, and fixture expectations are unchanged.
- The complete event-by-event action, output partition, support values,
  boundary margins, holdouts, and stability records are in `results.json` and
  `adjudications.json`.
- `git diff --check`, `git ls-files '*.png' '*.pdf'`, branch, commit, and final
  working-tree state are verified before commit.

### Complete 46-event transition ledger

The rows below preserve all event identities. Local partitions list source-row
IDs only; OCR strings remain locators in the JSON evidence.

| Event ID | Prior class | Gate | Local slope | Local result | Source rows / resulting event groups |
|---|---|---:|---:|---|---|
| `relativity_pdf10_pp26-27.left.event-001` | `repaired_false_split` | `apply_slope` | `-0.01660` | `repaired_false_split` | `176, 177, 178, 179, 180, 181, 182, 183, 184, 185, 186 → [176, 177, 178, 179, 180, 181, 182, 183, 184, 185, 186] |
| `relativity_pdf10_pp26-27.left.event-002` | `repaired_false_split` | `apply_slope` | `-0.01821` | `repaired_false_split` | `123, 124, 125, 126, 127, 128, 129, 130, 131 → [123, 124, 125, 126, 127, 128, 129, 130, 131] |
| `relativity_pdf10_pp26-27.left.event-003` | `new_false_split` | `apply_slope` | `-0.01736` | `new_false_split` | `70, 71, 72, 73, 74, 75, 76, 77 → [70, 71, 72, 73, 74, 75, 76]; [77] |
| `relativity_pdf10_pp26-27.right.event-004` | `repaired_false_split` | `apply_slope` | `-0.03404` | `repaired_false_split` | `278, 279, 280, 281, 282, 283, 284, 285, 286, 287 → [278, 279, 280, 281, 282, 283, 284, 285, 286, 287] |
| `relativity_pdf10_pp26-27.right.event-005` | `repaired_false_split` | `apply_slope` | `-0.03226` | `repaired_false_split` | `270, 271, 272, 273, 274, 275, 276 → [270, 271, 272, 273, 274, 275, 276] |
| `relativity_pdf10_pp26-27.right.event-006` | `repaired_false_split` | `apply_slope` | `-0.03320` | `repaired_false_split` | `258, 259, 260, 261, 262, 263, 264, 265, 266, 267, 268 → [258, 259, 260, 261, 262, 263, 264, 265, 266, 267, 268] |
| `relativity_pdf10_pp26-27.right.event-007` | `repaired_false_split` | `apply_slope` | `-0.03210` | `repaired_false_split` | `250, 251, 252, 253, 254, 255, 256 → [250, 251, 252, 253, 254, 255, 256] |
| `relativity_pdf10_pp26-27.right.event-008` | `repaired_false_split` | `apply_slope` | `-0.03333` | `repaired_false_split` | `238, 239, 240, 241, 242, 243, 244, 245, 246, 247, 248 → [238, 239, 240, 241, 242, 243, 244, 245, 246, 247, 248] |
| `relativity_pdf10_pp26-27.right.event-009` | `repaired_false_split` | `apply_slope` | `-0.03452` | `repaired_false_split` | `228, 229, 230, 231, 232, 233, 234, 235, 236 → [228, 229, 230, 231, 232, 233, 234, 235, 236] |
| `relativity_pdf10_pp26-27.right.event-010` | `repaired_false_split` | `apply_slope` | `-0.03119` | `repaired_false_split` | `216, 217, 218, 219, 220, 221, 222, 223, 224, 225 → [216, 217, 218, 219, 220, 221, 222, 223, 224, 225] |
| `relativity_pdf10_pp26-27.right.event-011` | `repaired_false_split` | `apply_slope` | `-0.03252` | `repaired_false_split` | `205, 206, 207, 208, 209, 210, 211, 212, 213, 214 → [205, 206, 207, 208, 209, 210, 211, 212, 213, 214] |
| `relativity_pdf10_pp26-27.right.event-012` | `repaired_false_split` | `apply_slope` | `-0.03200` | `repaired_false_split` | `193, 194, 195, 196, 197, 198, 199, 200, 201, 202 → [193, 194, 195, 196, 197, 198, 199, 200, 201, 202] |
| `relativity_pdf10_pp26-27.right.event-013` | `repaired_false_split` | `apply_slope` | `-0.03303` | `repaired_false_split` | `186, 187, 188, 189, 190 → [186, 187, 188, 189, 190] |
| `relativity_pdf10_pp26-27.right.event-014` | `repaired_false_split` | `apply_slope` | `-0.03333` | `repaired_false_split` | `161, 162, 163, 164, 165, 166, 167 → [161, 162, 163, 164, 165, 166, 167] |
| `relativity_pdf10_pp26-27.right.event-015` | `repaired_false_split` | `apply_slope` | `-0.03364` | `repaired_false_split` | `149, 150, 151, 152, 153, 154, 155, 156, 157, 158, 159 → [149, 150, 151, 152, 153, 154, 155, 156, 157, 158, 159] |
| `relativity_pdf10_pp26-27.right.event-016` | `repaired_false_split` | `apply_slope` | `-0.03543` | `repaired_false_split` | `129, 130, 131, 132, 133, 134, 135, 136 → [129, 130, 131, 132, 133, 134, 135, 136] |
| `relativity_pdf10_pp26-27.right.event-017` | `repaired_false_split` | `apply_slope` | `-0.03487` | `repaired_false_split` | `119, 120, 121, 122, 123, 124, 125, 126, 127 → [119, 120, 121, 122, 123, 124, 125, 126, 127] |
| `relativity_pdf10_pp26-27.right.event-018` | `repaired_false_split` | `apply_slope` | `-0.03390` | `repaired_false_split` | `104, 105, 106, 107 → [104, 105, 106, 107] |
| `relativity_pdf10_pp26-27.right.event-019` | `repaired_false_split` | `apply_slope` | `-0.03371` | `repaired_false_split` | `90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102 → [90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102] |
| `relativity_pdf10_pp26-27.right.event-020` | `repaired_false_split` | `apply_slope` | `-0.03256` | `repaired_false_split` | `81, 82, 83, 84, 85, 86, 87, 88 → [81, 82, 83, 84, 85, 86, 87, 88] |
| `relativity_pdf10_pp26-27.right.event-021` | `repaired_false_split` | `apply_slope` | `-0.03527` | `repaired_false_split` | `60, 61, 62, 63, 64, 65, 66, 67, 68 → [60, 61, 62, 63, 64, 65, 66, 67, 68] |
| `relativity_pdf10_pp26-27.right.event-022` | `repaired_false_split` | `apply_slope` | `-0.03485` | `repaired_false_split` | `50, 51, 52, 53, 54, 55, 56, 57 → [50, 51, 52, 53, 54, 55, 56, 57] |
| `relativity_pdf10_pp26-27.right.event-023` | `repaired_false_split` | `apply_slope` | `-0.03125` | `repaired_false_split` | `42, 43, 44, 45, 46, 47, 48 → [42, 43, 44, 45, 46, 47, 48] |
| `relativity_pdf10_pp26-27.right.event-024` | `repaired_false_split` | `apply_slope` | `-0.03469` | `new_false_split` | `32, 33, 34, 35, 36, 37, 38, 39, 40 → [32, 33, 34, 35, 36]; [37, 39]; [38, 40] |
| `relativity_pdf10_pp26-27.right.event-025` | `repaired_false_split` | `apply_slope` | `-0.04298` | `repaired_false_split` | `25, 26, 27, 28, 29 → [25, 26, 27, 28, 29] |
| `relativity_pdf10_pp26-27.right.event-026` | `repaired_false_split` | `apply_slope` | `-0.03512` | `repaired_false_split` | `15, 16, 17, 18, 19, 20, 21, 22, 23 → [15, 16, 17, 18, 19, 20, 21, 22, 23] |
| `relativity_pdf17_pp40-41.left.event-027` | `repaired_false_split` | `apply_slope` | `+0.01862` | `new_false_split` | `161, 162, 163, 164, 165, 166, 167, 168 → [161, 162, 163, 164, 165, 166]; [167]; [168] |
| `relativity_pdf17_pp40-41.left.event-028` | `repaired_false_split` | `apply_slope` | `+0.01840` | `repaired_false_split` | `138, 139, 140, 141, 142, 143, 144, 145, 146 → [138, 139, 140, 141, 142, 143, 144, 145, 146] |
| `relativity_pdf17_pp40-41.left.event-029` | `repaired_false_split` | `apply_slope` | `+0.01598` | `repaired_false_split` | `57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67 → [57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67] |
| `relativity_pdf17_pp40-41.left.event-030` | `repaired_false_split` | `apply_slope` | `+0.01806` | `repaired_false_split` | `37, 38, 39, 40, 41, 42, 43, 44 → [37, 38, 39, 40, 41, 42, 43, 44] |
| `relativity_pdf17_pp40-41.left.event-031` | `new_false_split` | `apply_slope` | `+0.01475` | `new_false_split` | `9, 10, 11, 12 → [9]; [10, 12]; [11] |
| `relativity_pdf17_pp40-41.left.event-032` | `new_false_split` | `apply_slope` | `+0.01475` | `new_false_split` | `9, 10, 11, 12 → [9]; [10, 12]; [11] |
| `relativity_pdf23_pp52-53.left.event-033` | `repaired_false_split` | `apply_slope` | `+0.01156` | `repaired_false_split` | `9, 10, 11, 12 → [9, 10, 11, 12] |
| `relativity_pdf23_pp52-53.left.event-034` | `unresolved` | `abstain` | `—` | `unresolved` | `163, 164, 171 → [163, 164, 171] |
| `relativity_pdf23_pp52-53.right.event-035` | `new_false_split` | `apply_slope` | `-0.00771` | `new_false_split` | `114, 115, 116, 117 → [114, 115]; [116]; [117] |
| `stella_maris_pdf03_session-I.right.event-036` | `repaired_false_split` | `apply_slope` | `-0.00561` | `new_false_split` | `112, 113, 114, 115, 116, 117, 118, 119, 120, 121 → [112]; [113, 114, 115, 116, 117, 119, 120, 121]; [118] |
| `stella_maris_pdf03_session-I.right.event-037` | `new_false_split` | `reject_slope` | `+0.00000` | `harmful_candidate_blocked` | `70, 71, 72, 73, 74, 75 → [70, 71, 72, 73, 74, 75] |
| `stella_maris_pdf03_session-I.right.event-038` | `new_false_split` | `abstain` | `—` | `harmful_candidate_blocked` | `111 → [111] |
| `stella_maris_pdf06_dense-dialogue.left.event-039` | `repaired_false_split` | `reject_slope` | `+0.00000` | `prior_false_split_preserved` | `311, 312, 313, 314, 315, 316, 317, 318, 319, 320, 321, 322 → [311, 312, 314, 315, 316, 317, 318, 319, 320, 321, 322]; [313] |
| `stella_maris_pdf06_dense-dialogue.left.event-040` | `repaired_false_split` | `reject_slope` | `+0.00000` | `prior_false_split_preserved` | `284, 285, 286, 287, 288, 289, 290, 291, 292, 293, 294, 295 → [284, 285, 286, 287]; [288, 290]; [289, 291, 292, 293, 294, 295] |
| `stella_maris_pdf06_dense-dialogue.right.event-041` | `new_false_split` | `reject_slope` | `+0.00000` | `harmful_candidate_blocked` | `246, 247, 248, 249 → [246, 247, 248, 249] |
| `stella_maris_pdf06_dense-dialogue.right.event-042` | `new_false_split` | `reject_slope` | `+0.00000` | `harmful_candidate_blocked` | `261, 262, 263, 264, 265, 266, 267 → [261, 262, 263, 264, 265, 266, 267] |
| `stella_maris_pdf18_session-II_p35.left.event-043` | `repaired_false_split` | `apply_slope` | `+0.00789` | `prior_false_split_preserved` | `55, 56, 57, 58, 59, 60, 61 → [55, 56, 57, 58, 60, 61]; [59] |
| `stella_maris_pdf18_session-II_p35.left.event-044` | `repaired_false_split` | `apply_slope` | `+0.01096` | `prior_false_split_preserved` | `19, 20, 21, 22, 23 → [19, 20, 22, 23]; [21] |
| `stella_maris_pdf18_session-II_p35.left.event-045` | `repaired_false_split` | `abstain` | `—` | `repair_not_attempted` | `9, 10, 11, 12 → [9, 10, 12]; [11] |
| `stella_maris_pdf18_session-II_p35.right.event-046` | `repaired_false_split` | `apply_slope` | `+0.00521` | `repaired_false_split` | `148, 149, 150, 151, 152, 153, 154, 155, 156 → [148, 149, 150, 151, 152, 153, 154, 155, 156] |
