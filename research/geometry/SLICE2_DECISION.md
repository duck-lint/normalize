# Slice 2 decision record

Status: the production horizontal-continuity rule has been updated on the dedicated guard-removal branch. The earlier observations and residual inventory below remain records of their stated baselines.

This record consolidates the evidence under
[`research/geometry/`](.) and links to the detailed reports. It distinguishes
observations, constructed demonstrations, interpretations, and hypotheses.

## A. Accepted current state

### Current horizontal-continuity rule

Production horizontal continuity uses cumulative observed token-box extent. For
each token admitted to a horizontal region, its actual `x1` updates the region
extent with `max(covered_right, token.x1)`. A following token starts a new
region only when its true gap from that extent exceeds the page-local limit
`2 * median(token_width_px)`. Production no longer classifies boxes by width or
withholds their observed extent. Final candidate assignment uses the same
ordinary region interval and horizontal-neighbor conditions.

This change was made because two independent crop-controlled studies found
only repaired false splits and no destructive merges on the representative
corpus: the earlier 300-DPI study and the production-cropped 144-DPI ablation
(research commit `b1728222b054e16053b756becd415ea602d2dee7`,
`research/production-cropped-guard-ablation/results.json` and
`adjudications.json`). The 144-DPI result was 43 adjudicated repaired false
splits, zero destructive merges, and zero unresolved events across 11
nonblank sides. This is corpus-bounded evidence, not a universal guarantee.

The implemented Slice 2 geometry parses admitted OCR tokens, applies the
recorded vertical grouping and horizontal splitting rules, reconciles candidate
physical lines, and serializes resolved, ambiguous, or unassigned states. The
current implementation remains the authority for the behavior being measured;
scan pixels remain authority for observable layout, raw/browser text remains
lexical authority, and OCR wording remains non-authoritative.

The pre-guard-removal six-fixture baseline contained four fixtures with no
residual assignment and two fixtures with residuals. Its seven-token residual
inventory was:

| Fixture / side | Source row | OCR token | Current state |
| --- | ---: | --- | --- |
| Relativity 10 / left | 213 | `system` | unassigned |
| Relativity 10 / left | 216 | `that` | ambiguous |
| Relativity 10 / left | 217 | `the` | ambiguous |
| Relativity 10 / left | 226 | `with` | ambiguous |
| Relativity 10 / left | 227 | `respect` | ambiguous |
| Relativity 10 / right | 246 | `impossible` | unassigned |
| Relativity 17 / right | 23 | `A` | ambiguous |

This seven-token observation is not GH-11's historical twelve-token lifecycle
result (Relativity 10: four ambiguous and six unassigned; Relativity 17: one
ambiguous and one unassigned). The exact twelve-token inventory was not
independently reconstructed. See the [historical-count erratum](evidence-corrections/errata.md)
and [residual report](residual-forensics/forensic-report.md).

Four successful fixture executions are regression evidence, not proof that all
physical-line assignments are correct in arbitrary scans.

## B. Established findings

The following claims are supported at the stated scope:

- Bounding-box topology alone does not establish physical-line continuity.
- The corrected paired synthetic pixel images have identical OCR/box inputs,
  distinct source pixels, and equivalent current box-only assignment states.
  The distinction is therefore information unavailable to the box-only
  algorithm, not an observation about the scanned books.
- Pixel measurements distinguish some constructed controls, but no tested
  measurement establishes a general physical-line criterion. The
  [pixel-prototype report](pixel-evidence-prototype/investigation-report.md)
  records the adversarial limitations.
- Greedy vertical grouping, horizontal splitting, and final reconciliation
  interact. The stage-isolated control reproduces direct production behavior
  for six fixtures and twelve pages; alternative vertical grouping is then a
  point of divergence, while downstream stages remain fixed in the research
  path.
- The alternatives can reduce unresolved counts in selected constructed or
  real residual cases without establishing physically correct assignments.
  A resolved token is not itself evidence that the chosen line is correct.

## C. Falsified or unsupported hypotheses

These broad claims are not licensed by the evidence:

- Pairwise or transitive geometric connectivity is not a general continuity
  rule; a constructed competing-row chain can merge distinct rows.
- A fixed anchor is not a general cure for median drift; the variable-height
  continuous-row construction exposes a false-split risk.
- Pixel connectedness is not physical-line identity: noise can bridge regions,
  glyphs can be disconnected, and ordinary spaces can be blank.
- A blank gap does not prove separate physical lines; genuine words and rows
  contain gaps.
- Lower unresolved counts do not establish correctness.

These results falsify the generalizations, not the possibility that a bounded
measurement can be useful as uncertain evidence in a particular case.

## D. Remaining uncertainty

The seven current identities remain unresolved or differently assigned by the
research alternatives. The preserved evidence does not provide an independent
physical-line authority for every case. Synthetic constructions establish
counterexamples and information boundaries; they do not establish performance
on arbitrary scans. Real-scan observations are bounded by the available,
provenance-recorded page images and by the ambiguity of interpreting pixels.

The unresolved state is therefore partly an evidence limit, not automatically a
production defect requiring a deterministic answer.

## E. Production-change decision

The width-based oversized-token special case was removed from production using
the bounded evidence stated above. The ordinary page-local gap predicate
remains the separation rule. This does not authorize a new width threshold,
token-type exception, OCR-text rule, or change to vertical grouping, slope,
OCR admission, or reconciliation. The ablation’s guard-on/guard-off identities
and human adjudications remain archived evidence; they are not generalized
claims about arbitrary scans.

## F. Future research boundaries

Horizontal pixel evidence and vertical clustering are separate questions. Pixel
work requires hash-verified unannotated images and an evidence protocol for
continuity, separation, and abstention. Vertical work requires independent
nearby-row and continuous-row controls and stage-fidelity checks. Neither line
of work authorizes a generalized geometry rewrite or a new production
threshold.

Primary supporting records:

- [residual forensics](residual-forensics/forensic-report.md)
- [diagnostic investigation](diagnostic-investigation/investigation-report.md)
- [evidence corrections](evidence-corrections/investigation-report.md)
- [pixel evidence prototype](pixel-evidence-prototype/investigation-report.md)
- [vertical clustering](vertical-clustering-investigation/investigation-report.md)
- [stage-isolated ablation](vertical-stage-ablation/investigation-report.md)
- [verification reconciliation](VERIFICATION_RECONCILIATION.md)
