# Slice 2 verification reconciliation

## Scope

This record reconciles the verification contracts at the descendant of
`00fcabf7f01557fb81b3aafdf04711aff13d2e48`. It does not rewrite archived
research outputs or claim an exact historical run that the repository cannot
execute.

## Historical chronology

| Concept | Revision or artifact | Status |
| --- | --- | --- |
| Historical evidence/input baseline | `699771d01c1a83c6f89c6a7eb2102e79a709b671` | Contains the corrected pixel inputs and archived output, but not `prototype.py`. |
| Historical executable implementation | `c0f7ea88493a07e6139e9c71d413a2eda130c17b` | First recorded descendant containing the pixel prototype. |
| Archived historical output | `research/geometry/pixel-evidence-prototype/results.json` | Preserved; SHA-256 `9cb713b636dcd013b248636970c9f2d9329733ee4094399f880425794d4cb7bf`. |
| Archived historical manifest | `research/geometry/pixel-evidence-prototype/manifest.json` | Preserved; SHA-256 `f5011780232530901b5337fc737ff0cea8ce00ad0bc08a39a45811a8b552d8bc`. |
| Current reusable implementation | `research/geometry/pixel-evidence-prototype/prototype.py` | Content-verified descendant implementation; its repaired-source identity is recorded by `vertical-stage-ablation/verification-contract.json`. |

The exact historical evidence baseline cannot be an exact executable prototype
snapshot because the prototype did not exist at that revision. The repository
therefore distinguishes an archived historical output from a historical
executable reproduction. The exact-revision mode correctly rejects the current
HEAD; no positive exact-historical reproduction is claimed.

A current descendant replay is a different claim. The reusable contract accepts
only a descendant of the historical evidence baseline that also contains the
prototype implementation, and verifies production geometry, the
identity-complete oracle, preserved inputs, archived result, and archived
manifest by content hash. The existing descendant-compatible test passes.

## Verification defects and repairs

The former exact-HEAD guard was being used by ordinary regression tests. It
confused “the evidence was recorded from this revision” with “this descendant
still satisfies the recorded content contract.” `prototype.py` now exposes
these as separate modes:

- exact historical mode requires the exact recorded revision and relevant
  archived provenance;
- reusable mode requires verified ancestry and content identities for the
  evidence and implementation dependencies.

The historical result and manifest were not rewritten. In particular, the
archived manifest's original prototype-source hash remains distinct from the
repaired current implementation hash.

The earlier vertical-investigation output also remains unchanged. The
assignment-only coordinate comparison used for current verification is in the
stage-ablation research path; it separates coordinate/input change,
assignment change, and measurement change.

## Independent fidelity verification

The prior dedicated fidelity test only read `results.json`. The current test
suite additionally executes `_fidelity_gate()` against the six repository
geometry artifacts and twelve pages, comparing direct production execution
with the research control for complete identity-level state and horizontal
splits. A second test injects an assignment-field mismatch into the control and
requires `run()` to reject it before writing results. It does not overwrite the
historical ablation output.

Focused verification tests: 12 passed. The complete suite collected 108 tests
and passed. The current full-suite result is not a historical result; it is the
verification result for this descendant.

## Reproduction commands

From the repository root:

```text
.venv/bin/python -m pytest -q tests/test_verification_repair.py tests/test_vertical_stage_ablation.py
.venv/bin/python -m pytest -q
```

The live fidelity test uses the repository-managed geometry JSON. The research
prototype's exact historical mode remains an explicit opt-in and must not be
replaced by a current-code replay.

## Scope and preserved distinctions

No production geometry, fixture contract, identity-complete oracle, source PDF,
preprocessing input, or historical research snapshot was changed. The current
reproduced residual observation remains seven tokens; GH-11's historical
lifecycle report remains a distinct twelve-token record.
