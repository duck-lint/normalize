# Evidence corrections and discriminating pixel experiments

This report preserves evidence-recording corrections. It does not modify
production geometry, select a pixel classifier, or treat synthetic pixels as
observations from the scanned books.

## A. Baseline and provenance

The isolated branch started at `d2dbea8e8e1a51ad92b38bb2caddb7f209542e72`,
the published `diagnostic-investigation-sparse-vertical` revision, with a
clean working tree. Its first parent is
`6453d2890fce5799640d7219effdd090ea6aed2d`, and the latter is an ancestor.
The existing residual-forensics and diagnostic-investigation snapshots were
hash-checked before changes and are preserved unchanged. Their exact hashes
and the new artifact inventory are in `manifest.json`.

The verified geometry module is the repository source at
`src/normalize/geometry.py`; no `PYTHONPATH=src` override was used to conceal
an installed implementation. The experiment uses the existing virtualenv and
does not install dependencies. No source PDF is copied into this directory.

Reproduction commands:

```text
.venv/bin/python research/geometry/evidence-corrections/pixel_experiments.py
.venv/bin/python -m pytest -q tests/test_evidence_corrections.py
.venv/bin/python -m pytest -q
```

## B. Evidence corrections

`errata.md` corrects two historical records without rewriting either prior
snapshot. The seven-token post-GH-11 observation and the twelve-token GH-11
lifecycle report are distinct records. The exact historical twelve-token
inventory and the reason for the count difference were not reconstructed from
the available evidence.

The earlier two-sided PNG pair was byte-identical. The prior narrative that it
showed distinct continuous and disconnected pixels was therefore not
established. The corrected pair below is the executable replacement evidence.

## C. Pixel experiment

Each pair has exactly one shared payload containing TSV header, all rows,
token text, source rows, boxes, dimensions, and metadata. The pair's input
SHA-256 is identical by construction and checked in code. Token text includes
duplicates on different source rows, so the complete oracle must preserve
identity rather than keying by text.

The source images are mode-L, black/white only, and contain no box annotations.
Separate overlay PNGs show the OCR boxes for inspection. In the continuous
case, the proposed bridge region contains visible synthetic ink structure. In
the disconnected case, that exact region is empty. The wide OCR rectangle is
not drawn as source ink in either case.

| Pair | Bridge ROI | Pixel result | Box-only result |
| --- | --- | --- | --- |
| Two ordinary tokens each side | x=35..144, y=20..29 | continuous support versus a full blank interval | equivalent complete state |
| One ordinary token each side | x=20..149, y=20..29 | continuous support versus a full blank interval | equivalent complete state |

The identity-complete oracle uses the common synthetic identity namespace
`(synthetic-pair, synthetic, source_row)` only to normalize the case label.
It retains every admitted token, duplicate identity, resolved assignment,
candidate set, uncertainty code, line membership, and measurement. Reversed
input order is checked for each case.

The deliberately identical-pixel control fails the discrimination checks:
pixel arrays and bridge-region measurements are equal. This prevents a test
from passing merely because it compares an output with itself.

## D. Candidate measurements and limits

The corrected pairs are distinguished by bridge-region occupancy, occupied
column fraction, empty-column runs, and connected-component measurements at
native and half scale. Those are observations about this controlled image
construction, not an authorized production rule.

The adversarial measurements record three limits:

1. A one-pixel noise path across a disconnected region can look connected to
   occupancy and component tests, producing a false-merge signal.
2. Separate glyph components and spaces can occur in one physical row, so a
   component count cannot establish physical-line identity and could produce a
   false-split signal.
3. Ink from a neighboring row can populate a broad horizontal ROI while the
   token-band ROI remains empty. Vertical alignment is therefore necessary,
   but it still does not by itself establish physical-line identity.

Bounding boxes establish only the represented token rectangles and their
relative topology. They cannot establish the source ink between rectangles,
whether a wide OCR rectangle spans a blank interval, or whether visible ink in
that interval belongs to the same physical row. The current box-only geometry
therefore produces equivalent complete assignments for the corrected pairs;
this is the intended information-loss demonstration, not a production defect
fixed here.

## E. What the evidence establishes

**Established:** identical box/TSV inputs cannot cause the current box-only
algorithm to distinguish different pixel observations.

**Demonstrated:** the corrected paired images differ in the intended pixel
evidence while producing equivalent box-only outputs, and the previous
identical-image defect is rejected by executable checks.

**Not established:** a generally reliable pixel-derived criterion for assigning
arbitrary document tokens to physical lines. The synthetic measurements do not
resolve scan noise, glyph structure, neighboring rows, skew, thresholding, or
the authority boundary between observable ink and inferred physical topology.

The Relativity 17 `lightning A` example and the Relativity 10 vertical
fragmentation traces remain preserved in the earlier diagnostic evidence. This
task does not extend or alter those conclusions.

## F. Next research question

The smallest separately authorized prototype would ask whether a bounded,
source-independent set of pixel measurements—explicitly conditioned on token
vertical bands and tested against noise, glyph gaps, neighboring rows, and
skew—can supply evidence without turning weak continuity into a deterministic
assignment. Acceptance would require complete identity-level state comparisons,
negative controls, and preserved uncertainty. It would not license a
production threshold or geometry correction by itself.

## Scope

Only this dedicated evidence-corrections directory and its focused diagnostic
test are changed. `src/normalize/geometry.py`, the identity-complete oracle,
fixture expectations, source inputs, PDFs, Slice 1, and downstream
reconstruction remain unchanged.
