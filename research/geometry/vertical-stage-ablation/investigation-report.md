# Verification repair and vertical-stage ablation

This report records a research-only experiment. Production geometry, fixture
contracts, source inputs, the identity-complete oracle, and pixel evidence
algorithms were not changed.

## A. Verification defects and repairs

The task started at `dfa6cd1ef2387364dded5ba86f92635d94875b4d`, a clean
descendant of the prior vertical-investigation commit. The pre-repair full
suite reproduced the reported result: 95 tests passed and one test failed,
`test_synthetic_controls_and_negative_controls_are_discriminating`.

The stack trace identified the sole immediate cause: the pixel prototype
required `HEAD == 699771d01c1a83c6f89c6a7eb2102e79a709b671`. That revision is
the historical evidence baseline, but the prototype itself was introduced by
descendant `c0f7ea88493a07e6139e9c71d413a2eda130c17b`. The guard therefore
prevented the reusable test from running on the legitimate current descendant.

`prototype.py` now has two explicit contracts:

- `require_exact_revision=True` requires the historical revision and rejects
  the current descendant.
- Ordinary reusable execution requires historical-baseline ancestry and checks
  content hashes for production geometry, the identity-complete oracle, the
  preserved synthetic pixel inputs, the preserved geometry inputs, the prior
  pixel result, the historical result, and the historical manifest.

The repaired source hash is recorded in
`verification-contract.json`. The historical pixel result and manifest were
not rewritten. The historical manifest retains its original prototype-source
hash (`2cbd7ced…d2295e62`); the repaired source has hash
`4a155f61…b0bb0845`. This distinction is intentional and is recorded as a
linked verification correction rather than presented as a historical
reproduction.

The earlier vertical-investigation JSON was also preserved unchanged. Its
one-pixel field remains a historical full-state comparison. The corrected
assignment-only comparison is implemented in this directory's
`stage_ablation.py` and preserves separate fields for coordinate/input change,
assignment change, and measurement change. It compares stable identity,
resolved assignment, candidate set, uncertainty, and canonical line
partition; raw token coordinates and incidental measurements are excluded from
the assignment verdict.

The regression tests demonstrate:

- descendant execution succeeds;
- exact historical mode rejects a different `HEAD`;
- relevant content mismatch is rejected;
- unrelated repository state is not part of the research content contract;
- a one-pixel coordinate change can leave assignment semantics stable while
  changing measurements;
- membership, candidate-set, and resolved-to-ambiguous transitions are
  detected;
- generated line-ID renaming is ignored by oracle canonicalization.

## B. Verification checkpoint

Focused tests for the pixel prototype, verification contract, prior vertical
investigation, and new stage ablation passed: 16 tests.

The complete suite passed after the verification repairs and before the
ablation was admitted. It also passed after the final ablation changes. The
historical distinction remains explicit: the current geometry observation is
seven residual tokens, while GH-11 reported twelve.

## C. Production-stage boundaries and fidelity gate

The actual implementation does not expose independent public stage functions.
`_line_bands` combines a greedy adjusted-center grouping loop with
`_split_horizontal_regions`; `group_physical_lines` then performs candidate
generation, ambiguity/unassigned reconciliation, line measurements, and
serialization inputs.

The research control therefore:

1. copies the exact pre-split loop from `_line_bands` at the verified source
   revision;
2. calls production `_split_horizontal_regions` unchanged;
3. copies the exact final candidate and uncertainty reconciliation because no
   callable seam exists;
4. compares its complete state against direct `group_physical_lines` output.

The fidelity gate covers all six preserved fixtures and all 12 pages. Complete
identity-level state and actual horizontal-split outputs match direct
production execution for every page. The same control is equivalent on all
eight existing synthetic counterexamples.

No alternative result is treated as admissible unless this gate passes.

## D. Ablation results

The alternatives change only the raw vertical-group constructor:

- `pairwise-components`: connect every adjusted-center-compatible pair that
  also satisfies production horizontal adjacency, then pass the groups to the
  unchanged splitter and reconciliation.
- `fixed-anchor-groups`: admit geometric-order tokens against a fixed first
  token anchor; competing anchors remain separate and are passed to the same
  downstream stages.

All model outputs use stable `(fixture_id, side, source_row)` identities,
complete candidate/uncertainty state, canonical line partition, and separate
measurement state. Both alternatives were permutation-stable on all eight
synthetic cases and the seven residual pages.

### Seven residual identities

| Identity | Production | Pairwise components | Fixed anchors |
| --- | --- | --- | --- |
| Relativity 10 left row 213 `system` | unassigned | resolves to `physical-line-0045` | resolves to `physical-line-0074` |
| Relativity 10 left row 216 `that` | ambiguous, two candidates | remains ambiguous, different candidates | remains ambiguous, different candidates |
| Relativity 10 left row 217 `the` | ambiguous, two candidates | remains ambiguous, different candidates | remains ambiguous, different candidates |
| Relativity 10 left row 226 `with` | ambiguous, two candidates | remains ambiguous, different candidates | remains ambiguous, different candidates |
| Relativity 10 left row 227 `respect` | ambiguous, two candidates | remains ambiguous, different candidates | remains ambiguous, different candidates |
| Relativity 10 right row 246 `impossible` | unassigned | resolves to `physical-line-0050` | resolves to `physical-line-0088` |
| Relativity 17 right row 23 `A` | ambiguous, two candidates | remains ambiguous with the same candidate set | remains ambiguous with the same candidate set |

Every real-page model difference first appears at the vertical-grouping
stage. The unchanged splitter and reconciliation then propagate or transform
the changed opportunities. That establishes where the experimental paths
diverge; it does not establish that a deterministic replacement assignment is
physically correct.

### Synthetic controls and falsification

- The continuous variable-height row remains assignment-equivalent under both
  alternatives.
- The center-chain median-drift case changes assignment under fixed anchors,
  producing the constructed two-group split. Since the construction represents
  one continuous row, this is a false-split risk of the fixed-anchor model.
- The competing-row transitive-chain case retains the baseline assignment
  under pairwise components and changes under fixed anchors. The construction
  still falsifies the shared pairwise/transitive assumption: the greedy control
  and pairwise model both merge the competing rows. Fixed anchors preserve an
  unresolved state rather than selecting a row.
- Horizontal fragmentation and sparse-support cases show that a vertical
  partition difference can be absorbed by unchanged downstream stages in some
  cases and alter final assignment in others.
- Nearby distinct rows and overlapping rectangles do not produce a new
  assignment difference in these controls; that is not evidence that boxes
  alone establish physical identity.
- The skewed-row case remains a limitation of the shared bounded geometry
  predicates; neither alternative supplies general skew invariance.

The four successful fixtures are regression controls, not target outcomes.
Several pages show complete assignment changes under both models; some pages
retain assignment stability despite vertical partition or measurement changes.
The results preserve these disagreements rather than ranking them by resolved
count.

### Perturbation semantics

The one-pixel diagnostic now records all three concepts separately. In the
continuous variable-height case, production and both alternatives report an
input-coordinate change, assignment stability, and measurement change. The
horizontal-fragmentation and sparse-support cases expose assignment changes
under the same one-pixel perturbation. The multiple-row compatibility case
changes measurements without changing assignment for both models. A changed
full-state digest alone is no longer treated as assignment sensitivity.

## E. Causal conclusions

Established:

- The ablation is stage-isolated after a passing fidelity gate.
- The real residual model differences originate at the substituted vertical
  grouping stage, while horizontal splitting and final reconciliation remain
  fixed.
- Vertical grouping can change downstream candidate opportunities without
  changing the reconciliation rules.
- Fixed anchors can trade median drift for false splits or retained ambiguity.
- Pairwise transitivity does not establish physical continuity; its competing
  row merge is already visible in the greedy control for the constructed case.

Not established:

- that greedy grouping is the sole cause of any real residual;
- that resolving `system` or `impossible` is correct;
- that fixed anchors or pairwise components are generally safer;
- that a changed final assignment was caused by vertical evidence alone rather
  than the interaction of the changed partition with unchanged downstream
  predicates.

The strongest causal statement supported here is therefore: vertical grouping
is an independently observable point of divergence, and its interaction with
horizontal splitting and reconciliation materially affects the final state.
The evidence does not license a production replacement.

## F. Production implications

No vertical modification warrants a production implementation experiment.

A separately authorized experiment would require source-independent cases with
independent physical interpretations, explicit false-merge and false-split
acceptance criteria, complete identity-level comparison, permutation and
coordinate-perturbation checks, and a callable or independently proven seam
for holding horizontal splitting and reconciliation constant. It must retain
uncertainty where evidence is insufficient and must not optimize unresolved
counts or fixture status.

## G. Reproduction and scope

From the repository root:

```bash
.venv/bin/python -m pytest -q tests/test_pixel_evidence_prototype.py tests/test_verification_repair.py
.venv/bin/python research/geometry/vertical-stage-ablation/stage_ablation.py
.venv/bin/python -m pytest -q tests/test_vertical_clustering_investigation.py tests/test_vertical_stage_ablation.py
.venv/bin/python -m pytest -q
git diff --check
```

The stage generator uses only repository-managed geometry JSON and the
previously preserved research scripts. It does not require the vanished
temporary image directory, copy source PDFs, or write durable output outside
`research/geometry/vertical-stage-ablation/`.

The manifest records the baseline revision, environment, production/oracle
hashes, all six geometry-input hashes, model parameters, commands, and output
hashes. Its self-hash is excluded to avoid a self-referential manifest.
