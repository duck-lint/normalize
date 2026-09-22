# Vertical-clustering investigation

This is a bounded research record. The production geometry implementation and
the identity-complete oracle were not changed. The alternative models are
implemented only in `investigate.py`; they are not proposed production code.

## A. Recovery

The experiment started from `c0f7ea88493a07e6139e9c71d413a2eda130c17b` on the
isolated branch `vertical-clustering-investigation`. The working tree was clean
before research edits. The production geometry import was verified as
`src/normalize/geometry.py`, with SHA-256
`15f351c93bf45e95a3d9db136af7415433833d51f9e1d7c1af48b81c6c1e64b5`. The
identity-complete oracle was verified with SHA-256
`58e47415dc21e285debda2a4d0112d3289ea781387704f04e8d55c2552b2bf44`.

The exact temporary Relativity 17 right-page image reported by the prior
prototype was present and matched the recorded hash:

`8c9d22680260bb86d76c06cb134f1383dbffbecc6cdb8a23730823f05b8db80e`.

The following derived, unannotated page images and preprocessing metadata were
recovered into `recovered-inputs/` and checked against hashes recorded at
recovery:

| Evidence | Repository path | SHA-256 prefix / suffix |
| --- | --- | --- |
| Relativity 10 left page | `recovered-inputs/relativity_pdf10_pp26-27/relativity_pdf10_pp26-27.left.png` | `b1e56511…ad102820` |
| Relativity 10 right page | `recovered-inputs/relativity_pdf10_pp26-27/relativity_pdf10_pp26-27.right.png` | `fa7c6902…d997eeb` |
| Relativity 10 preprocessing metadata | `recovered-inputs/relativity_pdf10_pp26-27/relativity_pdf10_pp26-27.preprocess.json` | `ee3365ae…419e81e1` |
| Relativity 17 right page | `recovered-inputs/relativity_pdf17_pp40-41/relativity_pdf17_pp40-41.right.png` | `8c9d2268…5b8db80e` |
| Relativity 17 preprocessing metadata | `recovered-inputs/relativity_pdf17_pp40-41/relativity_pdf17_pp40-41.preprocess.json` | `15c97799…27da95b` |

The source PDFs were not copied or committed. Their local references and
recorded hashes remain in the preprocessing metadata. The original temporary
files were not moved or deleted. Other temporary spread/page-side images and
disposable stdout were not imported because they were not required for the
selected residual traces or the four regression controls. These decisions are
recorded independently in `provenance-ledger.json`.

The recovery is durable: reproduction reads the repository paths above and the
versioned geometry JSON under `research/geometry/residual-forensics/`; no
authoritative output requires `/tmp`.

## B. Baseline

The production control calls `normalize.geometry.group_physical_lines`
directly. It matches the versioned geometry artifacts for the selected pages.
The current residual observation remains seven tokens, distinct from GH-11's
historical twelve-token lifecycle result:

| Fixture / side / source row | Text in the recorded geometry | Production state |
| --- | --- | --- |
| `relativity_pdf10_pp26-27 / left / 213` | `system` | unassigned |
| `relativity_pdf10_pp26-27 / left / 216` | `that` | ambiguous: `line-0046`, `line-0047` |
| `relativity_pdf10_pp26-27 / left / 217` | `the` | ambiguous: `line-0046`, `line-0047` |
| `relativity_pdf10_pp26-27 / left / 226` | `with` | ambiguous: `line-0049`, `line-0050` |
| `relativity_pdf10_pp26-27 / left / 227` | `respect` | ambiguous: `line-0049`, `line-0050` |
| `relativity_pdf10_pp26-27 / right / 246` | `impossible` | unassigned |
| `relativity_pdf17_pp40-41 / right / 23` | `A` | ambiguous: `line-0003`, `line-0004` |

The production trace preserves the adjusted center, tolerance, raw greedy
band, provisional band, bands considered, horizontal support, and final
reconciliation for each of these identities. For example, `system` enters raw
band source rows `[219, 218, 214, 215, 216, 217, 212, 211, 213]`, is provisionally
associated with `line-0047`, and ends with no final candidate. `that` and `the`
share the two final candidates `line-0046`/`line-0047`; `with` and `respect`
share `line-0049`/`line-0050`; `A` retains `line-0003`/`line-0004`. The exact
records are in `results.json` under `baseline.production_traces`.

## C. Experimental models

The greedy production implementation is the control. Two research-only
alternatives were evaluated against identical token boxes:

1. **Pairwise components.** Every token pair is connected when adjusted-center
   distance is within the measured tolerance and the existing horizontal
   adjacency predicate holds. Connected components are then split by the
   existing horizontal extent rule. This removes sequential median drift but
   admits transitive chains.
2. **Stable-anchor groups.** Tokens are processed in geometric order and are
   admitted only against a fixed first-token adjusted-center anchor. The anchor
   does not drift. A token compatible with competing anchors is retained as a
   competing group rather than selected by text, OCR line, or input order. The
   same research horizontal extent split is applied afterward.

Both adapters use the complete identity-level state: `(fixture_id, side,
source_row)`, physical-line membership, resolved assignment or absence,
candidate set, uncertainty, and line measurements. Generated line labels are
canonicalized by geometry before comparison. Zero candidates remain
unassigned; multiple candidates remain ambiguous. The models use no OCR text or
OCR line identifiers for grouping.

## D. Comparative results

### Real residuals

The research models do not establish a correction. On the seven residuals,
pairwise components resolve every token, while stable-anchor grouping resolves
every selected identity but retains additional uncertainty elsewhere on the
page. The identity-level changes are:

| Identity | Pairwise-components | Stable-anchor-groups | Evidence consequence |
| --- | --- | --- | --- |
| `system` | resolves to `physical-line-0033` | resolves to `physical-line-0067` | two incompatible deterministic answers replace production abstention |
| `that`, `the` | each resolves to `physical-line-0032` | each resolves to `physical-line-0065` | production ambiguity is removed without independent line authority |
| `with` | resolves to `physical-line-0034` | resolves to `physical-line-0069` | same uncertainty removal problem |
| `respect` | resolves to `physical-line-0034` | resolves to `physical-line-0068` | model disagreement within the pair is exposed |
| `impossible` | resolves to `physical-line-0049` | resolves to `physical-line-0088` | production unassigned state is replaced by competing answers |
| `A` | resolves to `physical-line-0003` | resolves to `physical-line-0003` | production ambiguity is removed, but the experiment supplies no new authority |

These are complete-state observations, not a success score. A lower
unresolved count is not evidence of a physically correct assignment.

### Synthetic falsification cases

The eight source-independent cases are defined in `investigate.py` and
materialized in `results.json`: varying token heights, a center-coordinate
chain, horizontal fragmentation, nearby distinct rows, overlapping separate
rows, sparse support, skew, and a token compatible with multiple rows.

The useful discriminations were:

- The center-chain case demonstrates the intended median-drift contrast:
  pairwise components retain one connected component, while fixed anchors
  split the constructed chain into `[1, 2]` and `[3, 4]`. This is a model
  distinction, not proof that either physical interpretation is correct in an
  arbitrary scan.
- The multiple-row-compatibility case is a falsification of transitive
  pairwise grouping: pairwise components merge source rows `[1, 3, 5, 2, 4]`
  into one component, while stable anchors retain two groups and one
  unresolved token. The latter preserves uncertainty rather than asserting a
  row.
- Horizontal fragmentation and sparse-support cases show that fixed anchors
  can preserve a vertical group before the horizontal split, but both models
  can still produce multiple final regions. Boxes alone do not establish that
  separated regions are one physical row.
- The skew case defeats both bounded models as written: the constructed shared
  slope yields six singleton groups. This falsifies any claim that the current
  pair predicates provide general skew invariance.
- All synthetic model runs were stable under reverse input order after
  canonicalization. Every one-pixel perturbation changed the canonical output
  digest in these deliberately boundary-sensitive cases; this demonstrates
  sensitivity, not instability or correctness.

The four successful fixture controls were also evaluated. The alternatives
changed complete assignment states on several pages and introduced unresolved
tokens under the stable-anchor model. Those changes are preserved in
`successful_fixture_controls`; they were not tuned toward the six-fixture
success target.

## E. Causal findings and hypothesis matrix

| Claim | Status | Supporting observation | Falsification or limit |
| --- | --- | --- | --- |
| Sequential median drift is a real mechanism that can distinguish a greedy model from a fixed-anchor model | demonstrated synthetically | center-chain construction gives one pairwise component but two fixed-anchor groups | the construction does not identify which model matches an arbitrary scan |
| Pairwise connectivity is safe against false merges | falsified | multiple-row-compatibility case merges competing rows transitively | a local pair predicate cannot by itself encode global row identity |
| Fixed anchors eliminate false splits | falsified | horizontal fragmentation and skew cases split or remain singleton groups | fixed anchors trade drift for anchor dependence and threshold sensitivity |
| The seven residuals are caused by greedy grouping alone | not established | research grouping changes residual states | the same outputs also pass through horizontal splitting and final reconciliation |
| Resolving `system` or `A` is an improvement | not licensed | alternatives produce deterministic assignments | no independent physical-line label was introduced by the model |
| A non-greedy model can replace explicit uncertainty | contradicted by the cases | stable anchors retain ambiguity in the multiple-compatibility case; pairwise removes it by merging | more deterministic output can be less faithful to the evidence |

The current evidence supports a narrower causal statement: grouping strategy is
one contributor to the observed states, and median drift is a plausible,
synthetically demonstrated mechanism. It does not isolate grouping as the
necessary cause of any real residual. Horizontal extent splitting and final
candidate reconciliation remain coupled mechanisms requiring separate
ablation.

## F. Next decision

No experimental vertical model warrants a production integration experiment.
The smallest justified next question is an ablation study that holds the
production horizontal and reconciliation stages fixed while replacing only
vertical grouping, with independently reviewed physical interpretations for
source-independent cases.

Before authorizing that study, the evidence should include:

- durable, permission-checked unannotated page images for the evaluated real
  regions;
- synthetic cases with an explicit physical interpretation and adversarial
  countercases for every proposed predicate;
- complete identity-level comparison, including false merges and false splits,
  rather than unresolved counts;
- permutation and small-coordinate-perturbation analysis;
- a stated abstention contract for competing rows and insufficient evidence;
- controls showing that any improvement is not obtained by changing the
  horizontal splitter, reconciliation, fixture expectations, or OCR authority.

The appropriate conclusion for the current seven residuals is therefore
“uncertainty remains,” not “non-greedy clustering is the solution.”

## G. Verification and reproduction

From the repository root, using the already-installed project environment:

```bash
.venv/bin/python research/geometry/vertical-clustering-investigation/investigate.py
.venv/bin/python -m pytest -q tests/test_vertical_clustering_investigation.py
.venv/bin/python -m pytest -q
git diff --check
```

The generator records Python, Tesseract, package versions, source hashes,
recovered-input hashes, model parameters, output paths, and output hashes in
`manifest.json`. The manifest deliberately excludes itself from its artifact
hash inventory to avoid a self-referential hash. `provenance-ledger.json`
records the recovery decisions separately.

Production geometry, the identity-complete oracle, fixture contracts, source
inputs, and prior research snapshots are byte-identical to the verified
starting commit. The new research code calls production geometry for the
control and imports its geometric predicates as measured evidence; it never
writes production assignments or feeds experimental results back into the
application.
