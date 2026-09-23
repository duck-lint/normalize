# Residual geometry forensic report

## A. Baseline

The experiment started from branch `guh`, commit
`a2ccdb1f06f3e97fbcc437fb969636305031355f`, with a clean working tree. The
checkout contains the investigated Slice 2 implementation; the current
`src/normalize/geometry.py` hash is
`15f351c93bf45e95a3d9db136af7415433833d51f9e1d7c1af48b81c6c1e64b5`.

The bare installed entry point was `.venv/bin/normalize`; no `PYTHONPATH` was
used. The verified imports resolve to:

`/home/duck-lint/projects/normalize/src/normalize/__init__.py`

`/home/duck-lint/projects/normalize/src/normalize/geometry.py`

The environment was Python 3.12.12, Tesseract 5.3.4, PyMuPDF 1.28.2,
Pillow 12.3.0, pytesseract 0.3.13, RapidFuzz 3.14.6, NumPy 2.5.3,
opencv-python-headless 5.0.0.93, and pytest 9.1.1. The complete version
record is in `manifest.json`.

The original checkout collected 84 tests. After adding four oracle tests, the
full suite collected and passed 88 tests.

## B. Artifact inventory and reproduction

The versioned evidence is under this directory. `manifest.json` contains the
complete per-file SHA-256, size, timestamp, source-input, fixture-status, and
artifact-path inventory: 27 evidence files totaling 15,334,611 bytes.

The six primary geometry artifacts are:

| Fixture | Path | SHA-256 | Size |
| --- | --- | --- | ---: |
| Relativity 10 | `relativity_pdf10_pp26-27/geometry.json` | `a5d57cc02aea30dc809bdbd7fc0394c0ddad219a20255c33ea7697640b5007d4` | 439,310 |
| Relativity 17 | `relativity_pdf17_pp40-41/geometry.json` | `17bad81b60a8ccb1a893200f316e5c749571ce4410f0302278227e1ca2fd59f5` | 420,301 |
| Relativity 23 | `relativity_pdf23_pp52-53/geometry.json` | `6fe6e0c1fbb9ef347c2ca7a4fda74135b369b0299fd99519d2a8a64d59759c56` | 383,251 |
| Stella Maris 3 | `stella_maris_pdf03_session-I/geometry.json` | `61c4958d4102b7b68340e9be0232c04508c48fbec958a4456668469526451513` | 119,851 |
| Stella Maris 6 | `stella_maris_pdf06_dense-dialogue/geometry.json` | `b834721f181ef06286ebbb36f0cfc9242cf7505b1d4781380342496ccaf8a976` | 434,614 |
| Stella Maris 18 | `stella_maris_pdf18_session-II_p35/geometry.json` | `7353bd8a56908f9abfad18b19569450241dc67d9d13c78479f483b52e88d2255` | 197,287 |

Each fixture directory also contains the two full-page annotation PNGs.
Residual-token crops and their stable identities, candidate sets, crop bounds,
and uncertainty codes are in `residual-annotations.json`. The seven crops are
only derived from preprocessed page images; no PDF was copied into this
directory. `invariance-diagnostics.json` records the exploratory synthetic and
fixture checks.

Reproduction, using only the existing local fixture PDFs and stable paths:

```text
.venv/bin/normalize check-env
.venv/bin/normalize preprocess <fixture_id> --config fixtures/preprocessing.json --output /tmp/normalize-residual-forensics/<fixture_id>/preprocessed
.venv/bin/normalize geometry --preprocessed /tmp/normalize-residual-forensics/<fixture_id>/preprocessed --output research/geometry/residual-forensics/<fixture_id>
.venv/bin/python research/geometry/residual-forensics/make_diagnostic_crops.py
.venv/bin/python research/geometry/residual-forensics/evaluate_invariance.py
.venv/bin/python research/geometry/residual-forensics/make_manifest.py
```

Run the preprocess/geometry pair once for each of the six fixture IDs. The
commands do not copy or modify source PDFs, raw text, or expected fixtures.

## C. Reproduction comparison

The regenerated results agree with the earlier seven-token observation and
with GH-11's reported counts:

- Relativity 10: four ambiguous and two unassigned;
- Relativity 17: one ambiguous and zero unassigned;
- the other four fixtures: no residual assignments.

The current seven-token identity set is:

| Fixture / side | Source row | OCR token | State | Candidate lines |
| --- | ---: | --- | --- | --- |
| Relativity 10 / left | 213 | `system` | unassigned | — |
| Relativity 10 / left | 216 | `that` | ambiguous | `line-0046`, `line-0047` |
| Relativity 10 / left | 217 | `the` | ambiguous | `line-0046`, `line-0047` |
| Relativity 10 / left | 226 | `with` | ambiguous | `line-0049`, `line-0050` |
| Relativity 10 / left | 227 | `respect` | ambiguous | `line-0049`, `line-0050` |
| Relativity 10 / right | 246 | `impossible` | unassigned | — |
| Relativity 17 / right | 23 | `A` | ambiguous | `line-0003`, `line-0004` |

No previous artifact hashes were supplied, so hash equality with the earlier
run cannot be asserted. The historical twelve-token control from older code is
kept conceptually separate and was not regenerated or relabeled as current
evidence.

## D. Oracle implementation

`tests/geometry_oracle.py` provides the test-only canonicalizer used by the
updated Slice 2 tests. Its token identity is `(fixture_id, side, source_row)`.
The parser's exact-payload deduplication contract remains explicit: an exact
duplicate is admitted once, retaining the first source row. Duplicate text on
different source rows therefore remains distinguishable.

The oracle compares every admitted token's identity, text and measured box,
resolved physical-line assignment or absence, complete candidate-line set,
uncertainty code, line membership, unresolved membership, line bounds and
measurements. Generated line IDs are replaced with labels assigned by
geometric order, so consistent line-label renaming is ignored.

The focused tests deliberately prove that it detects:

1. an identity swap between equal-text tokens;
2. a changed resolved assignment with the same unresolved count;
3. a changed candidate set; and
4. a stable assignment under different token input order while ignoring
   consistent generated line-label renaming.

The focused oracle run passed 5 tests. The fixture diagnostic applied the same
canonicalizer to all six regenerated fixtures and found all serialized-token
permutations equivalent by stable identity.

## E. Verification

- Focused oracle tests: 5 passed.
- Full suite: 88 passed.
- `git diff --check`: passed.
- Production geometry: byte-identical to the initial checkout; no diff and
  the recorded SHA-256 is unchanged.
- Fixture expectations, raw inputs, PDFs, and preprocessing configuration:
  unchanged.
- Manifest hashes were generated from the committed-path artifacts listed in
  the manifest.
- Reproduction uses `/tmp/normalize-residual-forensics`, not the vanished
  `/tmp/normalize-forensic-ZtuJM5/` directory.

## F. Remaining findings

The seven residual assignments remain unresolved. No geometry threshold,
assignment predicate, uncertainty category, or acceptance criterion was
changed.

The existing sparse oversized-rectangle behavior remains visible: a wide box
is allowed to preserve continuity only when ordinary tokens support it on both
sides; an unsupported bridge in a sparse region splits the physical-line
connectivity. The existing synthetic test preserves this finding. Dense
dialogue with covered horizontal extent remains a separate, passing case.

Translation was evaluated separately from scale. The three synthetic cases
preserved complete assignment state under translation and under token-order
permutation. Scale is exploratory rather than a mandatory Slice 2 contract:
the ambiguous synthetic case changed under both 2x and 0.5x coordinate scaling
after integer rounding, because its ambiguous token became resolved. This is
recorded as a genuine geometry behavior and not corrected or weakened.

## G. Scope

Changed files are:

- `tests/test_slice2.py`;
- `tests/geometry_oracle.py`;
- `research/geometry/residual-forensics/` evidence, reports, and supporting
  diagnostic scripts.

`src/normalize/geometry.py`, all fixture contracts and source inputs, Slice 1,
and downstream reconstruction are unchanged. During the task, the user-owned
`.gitignore` change adding `*.pdf` and `*.png` was observed and preserved; it
is not part of the task implementation commit, so intended PNG evidence must
be explicitly staged. No dependencies were installed, and no secrets, source
PDFs, pushes, merges, deployments, or SYMPHONY changes were made.
