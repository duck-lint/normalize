# Normalize — MVP Implementation Plan

## Goal

Reach MVP through vertical slices that preserve the project’s authority model:

`scan pixels → layout geometry → OCR anchors → raw-text alignment → structural reconstruction → derived Markdown`

Do not build broad infrastructure ahead of demonstrated need.

The empirical probe is a hard gate: the generalized reconstruction pipeline must not be built until the geometry/alignment thesis succeeds across the representative fixture set.

---

## Slice 0 — Repository Setup

### Deliver

* Python 3.12+ package / CLI shell
* dependency setup for:
  * PyMuPDF
  * Pillow
  * pytesseract
  * Tesseract executable
  * RapidFuzz
  * NumPy
  * OpenCV headless where needed
* fixture directory and expected-output loading
* basic test command
* environment check for Tesseract availability/version

Fixture PDFs are local test inputs, intentionally ignored and untracked. Geometry-dependent tests MUST report the missing-PDF condition explicitly on a clean clone and MUST NOT substitute another source.

### Acceptance

* package imports
* tests run
* fixture metadata loads
* Tesseract can be invoked
* one source PDF page can be rendered without modifying the source

### Stop condition

Do not begin layout logic until the runtime and fixture substrate are independently runnable.

---

## Slice 1 — Page Rendering and Preprocessing

Implement derived page rendering with observable preprocessing. The v3 configuration uses a 300-DPI working raster for `spread_crop`, split boundaries, and page-side crops. Crop rectangles are [x0, y0, x1, y1], with right and bottom edges exclusive. A page result requires the page key; a spread result requires exactly left and right. `dpi` remains the emitted OCR raster DPI (144); `render_dpi` sets the working raster (300).

The transform order is:

1. render the source fixture PDF at `render_dpi`;
2. apply configured orientation;
3. apply optional spread_crop;
4. apply configured deskew;
5. split a spread into logical sides;
6. apply each page_crops rectangle independently;
7. apply an optional rigid rotation to each cropped physical page side;
8. downsample each side to `dpi` and publish the derived OCR images;
9. emit provenance.

Page-side rotation is physical-page preprocessing. It applies one configured angle to an isolated side after its authoritative crop and before downsampling. It is separate from OCR-line slope compensation: downstream geometry neither infers nor undoes page rotation. Angle detection remains a separate, future mechanism; absent page-side configuration means no authorized rotation, while an explicit 0° is a measured no-op. Nonzero rotation uses Pillow bicubic interpolation, expanded canvas, and white fill; downsampling uses LANCZOS with nearest-half-up dimension rounding.

Each logical page records the source PDF page, working and output DPI, pre- and post-crop dimensions, exact crop operation and rectangle, coordinate stage, rotation status/angle and canvas behavior, downsampling method, retained side-local rectangle, split-side source rectangle, and fixture/source PDF page indices. The existing spread_output remains a 144-DPI spread-level preview before independent page-side crops and rotation.

The six selected fixture spreads use human-established operational rectangles in fixtures/preprocessing.json. Their exact 300-DPI recovery, hashes, rational 144-DPI conversion, and validation are recorded in fixtures/page-crop-bounds.json. The v3 config reuses the exact recovered 300-DPI crop rectangles; it does not infer them by reversing rounded 144-DPI bounds. Automatic physical-page boundary and orientation detection are deferred to separate work; these hand-selected fixture values are not generalized detectors.

Support:

* page/spread rendering
* orientation correction
* left/right spread ordering
* optional spread-level crop
* optional independent page-side crop after splitting
* optional gutter split
* optional deskew
* page-level crop provenance in preprocessing metadata

### Acceptance

* selected Relativity and Stella Maris fixture pages render in correct reading orientation
* left/right page order is explicit and remains unchanged by side-local cropping
* every applied transform is recorded at its actual coordinate stage
* independent left/right page crops and different output dimensions are supported
* preprocessing output can be inspected visually
* source PDFs remain unchanged
* missing local fixture PDFs produce an explicit fail/skip outcome rather than silent substitution
* the one-page local fixture index is distinguished from the original source-PDF page index retained as provenance

### Stop condition

Do not compensate downstream for uncertain page order, rotation, crop, or gutter detection.

---

## Slice 2 — Geometry Probe

Extract Tesseract TSV/box geometry.

Produce:

* OCR token boxes
* physical line groupings
* block identifiers as evidence only
* line-left / line-right positions
* line height
* vertical spacing
* annotated page image

### Acceptance

On the core fixture set:

* ordinary body lines are localized consistently
* first-line indentation is measurable where visibly present
* short dialogue blocks are spatially distinguishable from wrapped continuation lines
* running headers and page numbers occupy separable page regions
* OCR transcription quality is not used as the success metric

### Stop condition

If Tesseract cannot provide stable geometry on representative pages, stop and surface the failure before adding another OCR engine.

---

## Slice 3 — Structural Candidate Detection

Derive candidate document structure from geometry.

Detect at minimum:

* paragraph starts
* paragraph continuations
* dialogue-turn starts
* headings / session headings
* running headers
* page numbers
* figures / non-prose blocks where spatially evident
* display-math blocks where spatially evident

Use measurable evidence such as:

* first-line indentation
* vertical gap relative to local line spacing
* block isolation
* centeredness
* repeated margin position
* numbering hierarchy
* cross-page continuation geometry

### Acceptance

* candidate boundaries include confidence and evidence
* Tesseract `par_num` / block IDs are never treated as authority
* punctuation alone cannot create a paragraph boundary
* page boundaries do not automatically create paragraph boundaries
* unresolved candidates are representable

### Stop condition

Do not convert low-confidence candidates into hard structure merely to improve apparent completeness.

---

## Slice 4 — Raw-Text Alignment

Align noisy OCR geometry to the canonical raw/browser text, whether fully flattened or physical-line-preserving.

Requirements:

* approximate token/span matching
* page-scoped or bounded alignment windows
* monotonic source order
* local high-confidence anchors
* explicit unmatched spans
* explicit resynchronization after OCR corruption or page furniture
* repeated phrases are not resolved by string score alone

### Acceptance

For the core fixtures:

* known expected anchors map to the correct page regions
* isolated OCR character errors do not derail later alignment
* running headers/page numbers do not poison body-text alignment
* alignment confidence is surfaced
* raw text remains byte-for-byte unchanged as source input
* physical extraction line breaks, when present, are not promoted to paragraph/block authority

### Stop condition

If alignment drift cannot reliably resynchronize, stop rather than masking drift with broader fuzzy matching.

---

## Slice 5 — Probe Gate

Run the empirical probe across the human-reviewed Einstein and McCarthy fixture corpus.

Core set:

* Relativity — conventional prose / cross-page continuation
* Relativity — figure embedded inside prose
* Stella Maris — Session I / unlabeled dialogue
* Stella Maris — dense dialogue / wrapped turns

Stretch set:

* Relativity — display-math-heavy spread
* Stella Maris — session-heading reading-order anomaly

### Deliver

For every fixture:

* annotated page image
* geometry JSON
* alignment report
* candidate structure JSON
* comparison against `*.expected.json`
* human-readable probe report

### Acceptance

The probe passes only if:

Overall probe acceptance requires evidence from both the Relativity fixtures and the Stella Maris fixtures.

* conventional paragraph starts are recovered reliably across Relativity samples
* wrapped physical lines are not confused with new paragraphs/dialogue turns
* unlabeled Stella Maris dialogue turns are recoverable from geometry
* figures/display math can interrupt prose without forcing false paragraph boundaries
* cross-page continuation is recoverable
* page furniture can be excluded from body structure
* alignment survives ordinary OCR noise
* uncertainty is surfaced rather than hidden

Success on one Einstein page is insufficient; the current gate requires both selected source classes.

### Stop condition

If the core fixture set does not satisfy the project-spec probe acceptance criteria, do not proceed to generalized Markdown reconstruction.

---

## Slice 6 — Structural Reconstruction

Project accepted structure onto the canonical raw text.

Support:

* paragraph breaks
* dialogue-turn breaks
* heading boundaries
* cross-page continuation
* omission of confidently classified page furniture from clean output
* preservation of figures/display-math as structural blocks without treating OCR wording as canonical

### Acceptance

* reconstruction is written to a derived file
* source PDF and source raw text remain unchanged
* structural insertions correspond to aligned page evidence
* page furniture is not emitted as body prose when confidently classified
* the system can abstain on unresolved structure
* no lexical cleanup occurs implicitly

### Stop condition

Do not silently alter lexical characters while performing structural reconstruction.

---

## Slice 7 — Provenance and Confidence

Attach provenance to material structural decisions.

Each reconstructed boundary should identify:

* source-text offset/span
* source PDF page
* layout evidence
* classification rule
* confidence

Separate structural edits from any future lexical repair ledger.

### Acceptance

* every emitted structural boundary is traceable
* unresolved/low-confidence candidates remain inspectable
* derived Markdown is clearly identified as reconstructed output
* provenance survives serialization/reload

---

## Slice 8 — Cross-Fixture Hardening

Add regression coverage for:

* first-line indentation
* vertical-gap paragraphing
* short dialogue turns
* wrapped dialogue turns
* page-boundary continuation
* figure interruption
* display-math interruption
* running headers
* page numbers
* highlighting / annotation noise
* repeated-text alignment
* OCR corruption and resynchronization

### Acceptance

* every test states which authority layer it verifies
* OCR text accuracy is never used as proof of reconstruction correctness
* alignment tests do not substitute for structural tests
* expected JSONs remain human-reviewed structural oracles, not lexical source text
* normalized Markdown references are inspectable benchmarks/examples only and are not exact whole-file output oracles
* implementation cannot improve a fixture by rewriting its expected JSON or normalized reference

---

## Slice 9 — MVP Hardening

Verify:

* no source-file mutation
* no hidden assumption that one scan image equals one printed page
* no hidden fixed DPI requirement
* no hidden fixed indentation threshold
* no hidden dependence on Tesseract paragraph IDs
* no page-boundary-equals-paragraph assumption
* no unrestricted semantic/LLM rewriting
* explicit failure when Tesseract is unavailable
* stable reruns on identical inputs
* deterministic derived artifacts for the same configuration

### MVP Completion

MVP is complete when the acceptance criteria in `harness/project-spec/PROJECT_SPEC.md` are satisfied.

The minimum successful end state is:

* one selected full book processes end-to-end;
* canonical raw wording is preserved;
* reconstructed paragraph/dialogue/heading topology is materially faithful to the scan;
* page furniture is excluded with provenance;
* uncertainty remains explicit;
* every material structural edit can be traced back to page-layout evidence.

---
