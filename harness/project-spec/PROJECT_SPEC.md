# PROJECT_SPEC.md

# Layout-Guided Markdown Reconstruction — Project Specification

## 1. Purpose

Build a local, deterministic pipeline that reconstructs useful Markdown document structure from user-owned scanned pages. Recognition observations provide a derived lexical transcript; an independently obtained edition-matching text is optional stronger lexical evidence.

The system MUST derive useful structured Markdown from available lexical evidence and observable page layout, retaining provenance and uncertainty.

Symphony owns agent runtime/lifecycle. This repository harness MUST define only project goal, scope, contracts, authority, acceptance criteria, and stop conditions. It MUST NOT define agent orchestration, retry policy, model selection, or lifecycle behavior.

---

## 2. Empirical Basis

A proof-of-concept test on an Einstein scan showed:

- Tesseract transcription remained noisy and unsuitable as canonical text.
- Tesseract layout geometry was materially better: paragraph starts were recoverable from stable first-line indentation even when OCR tokens were wrong.
- Approximate alignment between noisy OCR tokens and raw-extracted text is therefore a plausible bridge from page geometry back to the cleaner text stream.

This empirical split was the thesis of the initial controlled experiment:

> **The experiment used independent raw text as lexical input while OCR supplied geometry/alignment evidence.**

That experiment is historical evidence, not the production input contract.
Production accepts scan-only books and records OCR as lexical evidence in a
derived `LexicalTranscript`; external text remains optional.

The first implementation milestone MUST test this thesis across multiple books before any full reconstruction pipeline is built.

---

## 3. Primary Goal

Given scanned pages and available lexical evidence, produce a structure map that can identify, with explicit uncertainty:

- printed page boundaries;
- physical text lines;
- paragraph starts and continuations;
- headings / section labels where supported;
- running headers;
- page numbers;
- likely captions / footnotes / other page furniture where observable;
- cross-page paragraph continuation;
- source-text spans corresponding to those layout structures.

The system MUST be capable of inserting paragraph/heading boundaries into a derived projection of the `LexicalTranscript` without silently rewriting lexical observations.

---

## 4. Non-Goals

The project MUST NOT, unless this specification is explicitly revised:

- silently claim that Tesseract transcription is verified wording;
- optimize Tesseract for book-quality OCR;
- use an LLM to freely rewrite, re-paragraph, summarize, or “clean up” source prose;
- infer exact publisher paragraph boundaries from semantics when page geometry does not support them;
- mutate source Markdown during the probe milestone;
- solve every document-layout class before the probe is proven;
- build a GUI;
- build a retrieval system, vector store, semantic index, or RAG layer;
- implement Symphony lifecycle/runtime behavior inside this repo.

---

## 5. Authority Split

The implementation MUST obey `AUTHORITY.md`.

At a high level:

1. source scan pixels are authoritative for observable layout;
2. recognition output is lexical evidence and may provide the scan-derived transcript;
3. an independent edition-matching external text is optional stronger evidence;
4. deterministic layout heuristics may classify structure;
5. semantic inference may only resolve explicitly ambiguous cases if later authorized;
6. uncertain structure MUST be represented as uncertain rather than silently invented.

---

## 6. Initial Stack

Target runtime: Python 3.12+.

Initial dependencies:

- `PyMuPDF` — PDF rendering and page access;
- `Pillow` — image operations;
- `pytesseract` — Tesseract TSV/box access;
- Tesseract executable — OCR/layout engine;
- `rapidfuzz` — approximate token/span matching;
- `numpy` — geometry/statistics;
- `opencv-python-headless` — rotation, deskew, gutter/crop helpers where required.

The dependency set MAY be reduced if equivalent behavior is preserved.

PaddleOCR or another OCR engine MUST NOT be added during the first probe merely because Tesseract transcription is inaccurate. A replacement/fallback engine is justified only if Tesseract fails at the geometry task under the probe acceptance criteria.

---

## 7. Architecture Contract

The pipeline is conceptually:

```text
ordered scanned pages
    ↓
page rendering / orientation / spread splitting
    ↓
positioned OCR tokens + line geometry
    ↓
layout features and candidate structural boundaries
    ↓
LexicalTranscript + approximate alignment to spatial anchors
    ↓
source-text span ↔ page-geometry map
    ↓
structure reconstruction
    ↓
Markdown projection
```

### 7.1 Lexical and structural data MUST remain separate

A positioned token record SHOULD resemble:

```json
{
  "ocr_text": "sen5e",
  "page": 12,
  "x0": 322,
  "y0": 544,
  "x1": 413,
  "y1": 573,
  "line_id": 17,
  "ocr_confidence": 82.1
}
```

An alignment record SHOULD map that evidence to the lexical transcript (the
historical fixture example used an independent raw-text source):

```json
{
  "source_text": "sense",
  "source_start": 1837,
  "source_end": 1842,
  "page": 12,
  "line_id": 17,
  "alignment_confidence": 0.93
}
```

A structural boundary record SHOULD be explicit about evidence:

```json
{
  "kind": "paragraph_start",
  "source_offset": 1924,
  "page": 12,
  "confidence": 0.98,
  "evidence": {
    "first_line_indent_px": 49,
    "median_body_indent_px": 0,
    "vertical_gap_ratio": 1.03
  }
}
```

The exact schema may evolve, but these distinctions MUST remain.

---

## 8. Milestone 0 — Probe

### 8.1 Purpose

The initial research gate tested whether Tesseract-derived geometry could recover useful topology while independent raw text supplied wording. That is historical evidence about the experiment, not a production requirement.

### 8.2 Probe corpus

Use the intentionally selected source classes already represented by the repository fixtures:

- Einstein, *Relativity* — conventional prose / sectioned technical text;
- McCarthy, *Stella Maris* — dialogue-heavy unconventional typography.

The current probe/MVP gate requires only these two source classes and their existing core/stretch fixtures. Gärdenfors and any fourth prose/philosophy source are deferred validation, not current acceptance inputs. Additional books and layout classes may be added later without changing the current gate.

### 8.3 Probe inputs

These are inputs to the historical controlled probe, not mandatory inputs to
current production runs.

For each fixture:

- source PDF;
- corresponding raw/browser-extracted text/Markdown, either fully flattened or physical-line-preserving;
- page or spread range to inspect.

When physical line breaks are present, they are admissible alignment evidence but are not paragraph/block authority. Geometry, not extraction line wrapping, determines observable structure.

Fixture PDFs are required for executable geometry tests but are intentionally ignored and untracked. A clean clone without the local PDFs MUST fail or skip geometry-dependent tests explicitly according to the test contract; it MUST NOT substitute another source or silently pass.

Each local fixture PDF is a one-page asset. The runtime/local PDF page index is therefore `fixture_pdf_page_index_1_based: 1`. The original source-PDF page index is separate provenance in `source_pdf_page_index_1_based`; it MUST NOT be used to open a page in the local fixture asset.

### 8.4 Probe outputs

The probe MUST produce all of the following without modifying the source Markdown:

1. **Annotated page image**
   - physical line boxes;
   - inferred paragraph starts;
   - running-header/page-number candidates;
   - confidence markings or labels.

2. **Geometry JSON**
   - page;
   - OCR token boxes;
   - reconstructed physical lines;
   - paragraph-start candidates;
   - relevant measurements.

3. **Alignment report**
   - OCR span;
   - matched raw/source span;
   - alignment confidence;
   - unmatched/ambiguous spans.

4. **Human-readable probe report**
   - detected paragraph starts;
   - confidence;
   - false positives / false negatives found during inspection;
   - any failure mode that would block a full implementation.

The probe MAY additionally emit a non-authoritative preview Markdown, but MUST label it as a preview and MUST NOT overwrite input.

### 8.5 Probe acceptance criteria

The probe passes only if human inspection shows:

- conventional prose paragraph starts are recovered reliably enough to be useful across the selected Relativity fixtures;
- OCR transcription errors do not materially prevent alignment for ordinary body text;
- page furniture can be distinguished from body structure often enough to avoid systematic contamination;
- the approach can represent uncertainty instead of forcing a boundary;
- *Stella Maris* yields enough geometric signal to make dialogue-turn reconstruction plausible, or its distinct failure mode is explicitly characterized.

The overall probe acceptance requires human inspection of both Einstein and McCarthy fixtures. The probe MUST NOT be declared successful based on a single Einstein page or on the Relativity fixtures alone.

### 8.6 Probe failure criteria

Stop and reconsider the architecture if any of these are systemic:

- geometry boxes frequently merge unrelated regions;
- line ordering is unstable after orientation/spread preprocessing;
- fuzzy alignment drifts irrecoverably after local OCR errors;
- repeated page furniture causes persistent incorrect text alignment;
- paragraph-start geometry is not stable across representative sources;
- the only way to obtain acceptable output is to trust OCR wording or use unrestricted semantic rewriting.

---

## 9. Geometry Rules

The implementation SHOULD derive structure from measurable geometry, not Tesseract paragraph IDs alone.

Useful features include:

- first-line indentation relative to the dominant body left edge;
- vertical gap relative to local median line spacing;
- line-height change;
- horizontal extent / centeredness;
- repeated text at stable top/bottom positions;
- numbering pattern;
- block isolation;
- cross-page continuation geometry;
- stable page-region recurrence.

Tesseract block/paragraph/line identifiers are signals, not authority.

---

## 10. Page Preprocessing

The implementation MUST make page preprocessing observable and debuggable.

For each rendered source page/spread, preserve enough metadata to explain:

- rotation applied;
- crop applied;
- spread split boundary;
- deskew transformation;
- resulting printed-page order.

Automatic spread splitting MAY be used, but every decision MUST be inspectable.

Manual overrides SHOULD be possible by configuration if automatic gutter detection is wrong.

Preprocessing MUST NOT permanently alter the source PDF.

---

## 11. Alignment Contract

For production book runs, alignment is between:

- noisy OCR token/line sequences; and
- `LexicalTranscript` tokens derived from lexical observations or explicit
  external lexical evidence.

The low-level fixture/research interface may still align OCR to independently
supplied raw text. That controlled path does not make external text mandatory
for a production scanned-book run.

Requirements:

- approximate, not exact, matching;
- local anchors and bounded windows to prevent global drift;
- explicit unmatched spans;
- resynchronization after page furniture or OCR corruption;
- monotonic source order unless the page-order model explicitly says otherwise;
- repeated phrases MUST NOT be resolved by nearest-string score alone.

The implementation SHOULD prefer many local high-confidence anchors over one global fuzzy match.

Alignment confidence MUST be surfaced.

---

## 12. Structural Reconstruction Rules

### 12.1 Paragraphs

A paragraph boundary MAY be emitted when geometry supports it through one or more strong signals, e.g.:

- first-line indent;
- abnormal inter-line gap;
- isolated paragraph block;
- dialogue-turn spacing;
- page-layout continuation pattern.

Sentence punctuation alone MUST NOT be sufficient evidence of an original paragraph boundary.

### 12.2 Cross-page continuation

A page boundary is not a paragraph boundary by default.

The implementation MUST distinguish:

- paragraph continues onto next printed page;
- new paragraph begins at top of next printed page;
- heading begins at top of next printed page.

### 12.3 Headings

Heading detection MAY use:

- numbering hierarchy;
- typography/line height;
- centeredness;
- isolation;
- repeated section patterns.

Markdown heading *level* is an interpretation and MUST be derived from explicit hierarchy rules, not arbitrary font size alone.

### 12.4 Page furniture

Running headers and page numbers MUST first be classified, not immediately deleted.

The projection layer may omit them from cleaned Markdown once classification confidence is high.

### 12.5 Hyphenation

Line-end hyphenation repair MUST be conservative.

A hyphen MUST NOT be removed merely because a physical line ended with `-`.

Any lexical repair that changes source characters MUST be logged separately from structural edits.

---

## 13. Confidence and Abstention

The system MUST support at least:

- `high`;
- `medium`;
- `low`;
- `unresolved`;

or an equivalent numeric confidence plus thresholds.

Low-confidence structure MUST NOT be silently projected as source fact.

When evidence is insufficient, the correct output is an unresolved candidate requiring review.

---

## 14. Provenance

Every projected structural edit SHOULD be traceable to:

- source text offset/span;
- source PDF page;
- geometry evidence;
- classification rule;
- confidence.

The system MUST preserve input lexical observations and any external lexical
source unchanged. Derived transcript text and Markdown remain identified as
derived artifacts.

A reconstructed Markdown file is a derived artifact, never a replacement authority.

---

## 15. CLI Shape

Exact commands may evolve, but the probe SHOULD converge on a simple local interface similar to:

```bash
python -m layout_reconstruct probe \
  --pdf "Einstein.pdf" \
  --text "Einstein.md" \
  --pages 27-31 \
  --out ".probe/einstein"
```

A future reconstruction command MAY resemble:

```bash
python -m layout_reconstruct reconstruct \
  --pdf "Einstein.pdf" \
  --text "Einstein.md" \
  --out "Einstein.reconstructed.md"
```

The final command names are not authoritative; the behavioral contracts are.

---

## 16. Test Strategy

### 16.1 Unit tests

Cover:

- line grouping from token boxes;
- indentation statistics;
- vertical-gap statistics;
- spread ordering;
- page-furniture recurrence;
- fuzzy anchor matching;
- alignment resynchronization;
- confidence calculation;
- cross-page continuation;
- serialization/provenance.

### 16.2 Reviewed probe fixtures

Maintain small, human-reviewed representative fixtures with an `*.expected.json` structural oracle containing expected:

- printed-page orientation/order;
- paragraph-start coordinates;
- heading candidates;
- page-furniture classifications;
- source-text alignment anchors.

Fixture roles are distinct:

- `*.raw.md` is the immutable lexical substrate;
- `*.expected.json` is the human-reviewed structural oracle for explicit assertions;
- `*.normalized.md` is a human-produced reference structural normalization for inspection and benchmarking only.

The normalized reference MUST NOT be treated as authoritative lexical text and MUST NOT require exact whole-file equality from an implementation. Acceptance SHOULD evaluate the explicit structural assertions in `*.expected.json`, provenance, source-span preservation, page-furniture handling, uncertainty, and other project contracts. A normalized reference may illustrate a plausible projection; it does not define the only valid projection.

### 16.3 No metric gaming

A test suite MUST NOT define success solely as token-alignment percentage.

The project goal is correct document structure. A high alignment score with wrong paragraph boundaries is failure.

---

## 17. Development Sequence

Agents SHOULD proceed in this order:

1. repository skeleton and dependency setup;
2. render/orient/split one representative page;
3. extract Tesseract TSV geometry;
4. visualize lines/boxes;
5. infer paragraph-start candidates from geometry;
6. produce probe JSON/report;
7. align geometry to raw/browser text;
8. run probe across the required Einstein and McCarthy fixture corpus;
9. evaluate probe against acceptance criteria;
10. only after probe acceptance, design the generalized reconstruction/projection layer.

Agents MUST NOT skip directly to full-book rewriting.

---

## 18. Explicit Agent Loop Traps and Mitigations

### Trap: “Improve OCR until transcription is clean”
Mitigation: OCR wording is non-authoritative. Optimize geometry/alignment only.

### Trap: Overfit first-line indent to Einstein
Mitigation: the current probe corpus MUST include both Einstein's conventional prose and McCarthy's dialogue-heavy layout before acceptance. Hierarchical and other layout classes are deferred validation.

### Trap: Trust Tesseract `par_num` as truth
Mitigation: derive paragraph evidence from measured geometry; OCR structural IDs are only features.

### Trap: Global fuzzy match drifts after one bad region
Mitigation: local anchors, monotonic windows, page-scoped alignment, explicit resynchronization.

### Trap: Repeated headers poison alignment
Mitigation: classify stable margin recurrence before body-text alignment or exclude those regions from canonical alignment.

### Trap: “Fix” source text while restructuring
Mitigation: source text is immutable during structural projection. Lexical repairs require a separate explicit edit ledger.

### Trap: Turn uncertainty into aggressive heuristics
Mitigation: abstention is required. Unresolved candidates are valid outputs.

### Trap: Build a full framework before proving geometry
Mitigation: Milestone 0 probe is a hard gate.

### Trap: Add more OCR engines prematurely
Mitigation: only replace/add engine if probe evidence shows Tesseract geometry fails.

### Trap: Hide preprocessing mistakes downstream
Mitigation: orientation, crop, gutter split, and deskew outputs MUST be visualizable and logged.

### Trap: Treat page boundaries as paragraph boundaries
Mitigation: explicit cross-page continuation classification and tests.

### Trap: Optimize for pretty Markdown rather than source fidelity
Mitigation: acceptance is based on structural correctness + provenance, not aesthetics.

---

## 19. Definition of Done

### Probe done

Milestone 0 is done when:

- the selected Einstein and McCarthy fixture sample has been processed;
- outputs are inspectable;
- paragraph/layout recovery has been manually evaluated;
- failure modes are documented;
- the project thesis is either accepted or falsified with evidence.

### MVP done

The reconstruction MVP is done when:

- a full selected book can be processed end-to-end;
- source text remains unchanged except separately authorized lexical repairs;
- reconstructed paragraphs/headings are materially faithful to page layout;
- page furniture is excluded from cleaned Markdown with provenance;
- uncertainty is surfaced;
- the result is reproducible from the same inputs;
- every structural insertion can be traced back to page/layout evidence.
