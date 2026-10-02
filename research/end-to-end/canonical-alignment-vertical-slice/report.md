# Canonical alignment to Markdown vertical slice

## A. Starting state

- Starting branch: `guh`
- Starting commit: `473e639b6fe335ffb527d2338234d38e311189ba` (`Remove oversized token grouping guard`)
- Feature branch: `feature/canonical-alignment-reconstruction`
- Existing worktree input: `fixtures/einstein/spineless/` was untracked and left unstaged.
- Pre-change production suite: `./.venv/bin/python -m pytest -q --import-mode=importlib` completed successfully with one existing skip.
- Existing downstream production path: none. Before this change, production ended at `normalize.geometry.run_geometry`; there was no canonical alignment, structural reconstruction, or Markdown emission.

## B. Implemented architecture

The production path is:

```text
canonical raw source + geometry-probe-v1 pages + character-offset page spans
    → normalize.alignment.tokenize_canonical / align_monotonic
    → normalize.reconstruction.reconstruct_document
    → normalize.markdown.emit_markdown + document_record
```

`CanonicalToken` preserves source ID, character offsets, original spelling, and a disposable matching form. `GeometryAnchor` preserves page, OCR token ID/text/confidence, box, physical-line ID, and order. `AlignmentLink` maps canonical token indices to OCR anchors and line IDs. `AlignmentResult` retains unmatched canonical tokens and OCR anchors, links, sequence-level ambiguity, and diagnostics. Structural blocks preserve canonical spans, page IDs, physical-line IDs, anchor IDs, and the evidence used for classification.

`normalize reconstruct --raw ... --geometry ... --spans ... --output ... --sidecar ...` is the production CLI entry point. It accepts a raw source and geometry-probe-v1 page records; the spans manifest maps ordered geometry pages to half-open decoded-character offsets. It does not need a fixture catalog.

The implementation note is [implementation-note.md](implementation-note.md). The durable production contract is [DOWNSTREAM_RECONSTRUCTION.md](../../../harness/project-spec/DOWNSTREAM_RECONSTRUCTION.md).

## C. Authority preservation

- All visible prose and retained labels originate in selected canonical raw spans. All three paired runs have an exact canonical token sequence match before Markdown syntax is added.
- OCR text is used only in alignment. Unmatched OCR anchors are recorded in sidecars and cannot be emitted as prose.
- The production alignment/reconstruction/emission modules neither import nor read `*.expected.json` or `*.normalized.md`.
- The CLI generation test supplies only a raw text file, geometry JSON, and page-span JSON in a temporary directory with no structural references.
- The acceptance runner writes paired and combined Markdown before opening the existing structural oracles.
- Canonical source bytes are decoded directly, without newline translation, so recorded character spans stay attached to the actual decoded source.

## D. Alignment behavior

The six geometry records are the frozen prior exact-source observations from `3087f18bb20f562e5dbcdf3a36771b1e14fdde0b`. The saved acquisition record marks the final raster hash, TSV hash, admitted token count, physical-line count, ambiguous count, and unassigned count as matching the exact-source study on every page. No OCR invocation was needed for this downstream run.

| Page | Canonical tokens | Matched canonical tokens | Unmatched canonical | Unmatched OCR anchors | Sequence ambiguity |
|---:|---:|---:|---:|---:|---|
| 26 | 196 | 190 | 6 | 3 | optimal-path tie reported |
| 27 | 274 | 246 | 28 | 19 | optimal-path tie reported |
| 40 | 134 | 132 | 2 | 6 | optimal-path tie reported |
| 41 | 294 | 291 | 3 | 13 | optimal-path tie reported |
| 52 | 132 | 121 | 11 | 19 | optimal-path tie reported |
| 53 | 222 | 208 | 14 | 21 | optimal-path tie reported |

Across the selected spans, 1,188 canonical tokens have a geometry link and 64 remain explicitly unmatched. There are 81 unmatched OCR anchors. Six page-level optimal-path ties are reported; they are not incorrectly projected onto every individual link. Some geometry-order conflicts are also reported where canonical order maps to a higher y position than the preceding mapped line. Those transitions cannot create paragraph boundaries.

The matching costs are documented in the alignment module and production contract: gap cost 0.82; single-token substitutions require at least 0.68 normalized character similarity; grouped 1:2 or 2:1 merge/split matches require 0.88 after concatenation. Canonical output is never assembled from OCR text.

## E. Reconstruction behavior

The combined output contains three headings, fifteen prose paragraphs, one figure block, and one display-math block. It retains all selected canonical words and their page/source provenance. The page-26/27 pair is under-segmented: three expected page-27 paragraph boundaries are missing.

- Headings for pages 26, 40, and 52 are emitted from canonical wording using centered top-page geometry, relative line height, and separation from body text.
- Paragraph breaks use page indentation and substantial vertical separation. Physical-line changes and page changes do not automatically create Markdown breaks.
- The page-40 figure labels and `Fig. 1` are represented as a figure placeholder inline within the surrounding paragraph, retaining its interruption and continuation without implying a new prose paragraph.
- Display math is emitted only for a centered, narrow formula-like geometry line. This conservative rule finds `=0` on page 53. Several other expected math structures remain unresolved and are counted below.
- The source fixture ranges exclude explicit running headers/page labels. Their byte ranges are recorded in `page-spans.json`, and the unselected source gaps are reported by the production model.

## F. Six-page generated artifact

- Combined Markdown: [generated.md](generated.md)
- Paired outputs: [26-27.md](per-page/26-27.md), [40-41.md](per-page/40-41.md), [52-53.md](per-page/52-53.md)
- Per-page Markdown: `per-page/26.md`, `27.md`, `40.md`, `41.md`, `52.md`, and `53.md`
- Alignment and structure sidecars: corresponding `.json` files in `per-page/`

The combined artifact includes explicit fixture-pair boundaries so page 27 is not presented as continuous prose with page 40.

## G. Structural comparison

The page-26/27 output preserves the heading, continuation across the printed-page boundary, and final Nevertheless paragraph. It misses expected paragraph boundaries before If, We advance, and As long, combining those three logical paragraphs with the paragraph that began on page 26. The 40/41 output preserves its expected heading, figure interruption, and paragraph starts. The page-40 figure placeholder is a serialization difference; it retains canonical labels and caption locator.

The page-52/53 oracle expects a two-equation group on page 52, a continuation expression at the top of page 53, further displayed expressions, and prose relationships across those interruptions. The generated Markdown does not separate four of those expression sites as display math and creates a paragraph break around the one `=0` display it does recognize. The three page-27 merges plus five math structure/relationship issues are the eight recorded defects. Full locations and oracle comparisons are in [comparison.json](comparison.json) and [defects.json](defects.json). Reference files were not used to generate the output.

## H. Known geometry propagation

The known physical splits on pages 26 and 53 do not appear as line breaks in Markdown: `changes its position relative to the embankment yet` and `and for still greater velocities the square-root becomes` each remain continuous. Page 27 is different. The phrase `If Kis a Galileian co-ordinate system, then every other` is not split at the physical band transition, but the expected paragraph start before `If` is missing and the expected paragraphs before `We advance` and `As long` are also merged. The geometry imperfection does not create a literal line break; reconstruction still produces a wrong final paragraph structure at that location. The separate page-53 `=0` block causes another paragraph-continuity defect.

## I. Page-27 malformed OCR

The raw OCR contains seven target observations. `insufficient` (`token-0192`) and `foundation` (`token-0193`) each have a 3×2 px box; their confidence values are 69.451653 and 95.356232. Both still align 1:1 to the corresponding canonical words. The generated text contains the exact canonical sequence `affords an insufficient foundation for the physical`; no canonical word was dropped or substituted. The text remains inside the oversized paragraph because page-27 paragraph boundaries are missing, but the malformed boxes themselves cause no additional lexical or local structural loss.

## J. Diagnostics

The sidecars and [diagnostics.json](diagnostics.json) retain:

- unmatched canonical token indices and unmatched OCR token IDs;
- six sequence-level optimal-path ties;
- canonical/geometry order conflicts;
- malformed anchor IDs, including the two tiny page-27 target boxes;
- explicit source ranges outside selected page spans;
- page-boundary review notes.

The unmatched spans around the math-heavy material make those locations inferable for review. The paragraph relationship around `=0` is not pointed to by an existing diagnostic and is classified as silent.

## K. Manual-review burden

- Final defects: **8**: three page-27 paragraph merges and five display-math structure/relationship defects.
- Affected pages: **3** (27, 52, and 53).
- Localized edit sites: **8**.
- Lexical loss/duplication: **0**.
- Destructive structural merges: **3**.
- Already-flagged defects: **0**.
- Inferable from existing alignment diagnostics: **7**. These diagnostics indicate weak/unmatched alignment or geometry order around the affected material but do not explicitly identify a missing paragraph boundary.
- Silent defects: **1** (the false paragraph continuation around the =0 display).

The edits are localized, but the missing prose boundaries show reconstruction is not yet sufficiently complete. No correction-time estimate is made.

## L. Harmless intermediate errors

The physical splits within the page-26 “yet”, page-27 “If K...”, and page-53 “and for still greater...” phrases do not themselves create line breaks in Markdown. The tiny page-27 OCR boxes also do not alter canonical wording. However, page 27 has three separate missing paragraph boundaries; those are final defects, not harmless geometry differences.

## M. Layer attribution

The three page-27 paragraph merges arise in structural reconstruction: aligned canonical material is retained, but current boundary evidence does not produce the expected starts. The page-52 equation group and page-53 display-expression omissions also arise at structural reconstruction; the page-53 top continuation additionally has weak raw OCR/anchor evidence. The `=0` continuity defect arises at structural reconstruction/Markdown projection because the model emits a separate block without retaining a logical paragraph-continuation relation. No final defect is attributed to lexical alignment replacing source text.

## N. Verification

Pending final verification before commit. The final execution summary records test commands, production diff, tracked-binary check, branch, commit, and worktree status.

## O. Decision and limits

`alignment_is_viable_but_reconstruction_remains_incomplete`

Normalize produces genuine Markdown from canonical raw text and the established geometry observations, with machine-readable provenance. Alignment preserves canonical wording, but three missing page-27 paragraph boundaries and five math structure/relationship defects leave reconstruction incomplete for this acceptance corpus.

This run covers only six heavily studied fixtures. It does not estimate whole-book or general-text performance. Full-novel runs remain the relevant workflow and generalization test.
