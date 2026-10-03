# AUTHORITY.md

# Project Authority

This document defines what agents are allowed to treat as truth, what they may infer, and what they must not silently change.

Symphony owns agent runtime and lifecycle. This file governs only project authority.

---

## 1. Authority Hierarchy

Highest authority first:

1. **User-owned source scan pixels**
   - authoritative for observable document layout;
   - page ordering after explicit preprocessing;
   - visible indentation, spacing, block placement, headings, page furniture, and other typography/layout evidence.

2. **Lexical evidence with explicit provenance**
   - scan-derived recognition observations provide the initial lexical evidence;
   - an independently obtained edition-matching source is optional stronger evidence;
   - neither is silently relabeled canonical by the pipeline.

3. **Explicit project contracts in `PROJECT_SPEC.md`**
   - authoritative for intended behavior, scope, outputs, stage gates, and acceptance criteria.

4. **Deterministic geometric reconstruction**
   - authorized to infer structural boundaries only from observable layout evidence and declared rules.

5. **OCR / recognition output**
   - records what an observer reported and may supply lexical wording when no independent source exists;
   - remains uncertain evidence, not independent lexical authority;
   - paragraph/block labels and confidence values are evidence, not truth.

6. **Textual heuristics**
   - may support structure classification;
   - may not override contradictory page geometry;
   - punctuation/semantics alone do not establish original paragraph boundaries.

7. **Semantic/LLM inference**
   - not part of the initial probe;
   - if later authorized, may resolve explicitly ambiguous cases only;
   - may never silently rewrite source text or manufacture structure as source fact.

8. **Implementation convenience**
   - lowest authority;
   - libraries, internal schemas, module layout, and algorithm choices may change freely if higher-order contracts remain intact.

---

## 2. Core Invariants

Agents MUST preserve these invariants:

### 2.1 Lexical provenance

Source observations and external lexical sources are immutable inputs to a run. The derived `LexicalTranscript` is the lexical input to reconstruction and retains provenance to those inputs. External text may be fully flattened or preserve physical extraction line breaks; those breaks may assist alignment, but do not establish paragraph or block boundaries.

Structural reconstruction may insert Markdown syntax or boundaries into a derived output, but MUST NOT silently alter lexical characters or treat extraction line wrapping as layout authority.

Any lexical repair is a separate operation with explicit provenance. A fixture may document a known extraction anomaly as an observation without authorizing a general repair rule or allowing runtime reconstruction to correct it silently.

### 2.2 Layout fidelity

When page geometry clearly establishes a structural boundary, that evidence outranks semantic convenience.

### 2.3 Uncertainty is allowed

The system is not required to force a decision.

`unresolved` is preferable to an unsupported structural claim.

### 2.4 Recognition is lexical evidence

Agents MUST NOT describe a scan-derived transcript as verified or canonical. The transcript preserves the observer's actual output and factual uncertainty. A human correction is a separate explicit layer.

### 2.5 Derived artifacts are not source authority

Reconstructed Markdown, normalized text, alignment maps, and probe reports are derived artifacts. In the historical controlled fixture contract, `*.raw.md` was independent lexical input and `*.expected.json` was a human-reviewed structural oracle. That experiment does not make external text a production prerequisite.

The original scans and any explicitly supplied external lexical source remain upstream evidence.

### 2.6 Provenance is structural

Every material structural transformation SHOULD be explainable from:

- page;
- source text span;
- geometry;
- rule/evidence;
- confidence.

---

## 3. Authorized Transformations

Agents MAY:

- render PDF pages;
- rotate, crop, deskew, or split spreads in derived images;
- extract OCR boxes/TSV;
- group OCR tokens into physical lines;
- derive indentation and vertical-gap statistics;
- detect repeated page furniture;
- align OCR spans approximately to source text;
- classify structural candidates;
- insert paragraph breaks/headings into derived Markdown;
- omit confidently classified page furniture from derived Markdown;
- produce annotated images and reports;
- add tests and fixtures;
- refactor internal implementation while preserving contracts.

---

## 4. Unauthorized Transformations

Agents MUST NOT:

- overwrite the user’s input PDF or raw extracted text;
- replace raw text with Tesseract text;
- rewrite prose for fluency;
- summarize or paraphrase source material;
- infer missing paragraphs solely because prose “reads better” that way;
- delete ambiguous text as presumed header/page furniture without sufficient evidence;
- use unrestricted LLM rewriting to generate the final Markdown;
- silently repair OCR/browser character errors;
- treat a page boundary as a paragraph boundary by default;
- bypass the probe gate and jump directly to a generalized full-book pipeline;
- add orchestration/lifecycle logic that belongs to Symphony;
- expand project scope merely because an agent can.

---

## 5. Conflict Resolution

When evidence conflicts:

1. preserve the source text;
2. inspect source-page geometry;
3. prefer direct observable layout over OCR labels;
4. prefer abstention over speculative structure;
5. emit a review candidate with provenance;
6. do not hide the conflict behind a heuristic.

Example:

- Tesseract says `par_num` changed;
- geometry shows no indent/gap;
- text semantics are inconclusive.

Result: do **not** assert a paragraph boundary solely from `par_num`.

---

## 6. Probe Gate Authority

The probe is a hard project gate.

Before probe acceptance, agents are authorized to build only what is needed to evaluate the thesis:

- preprocessing;
- geometry extraction;
- visualization;
- layout features;
- alignment;
- probe reports;
- small fixtures/tests.

They are not authorized to invest in a generalized full-book writer beyond a minimal preview required to evaluate the probe.

Probe acceptance requires evidence across multiple books, not success on one Einstein page.

---

## 7. Dependency Authority

Initial expected stack:

- Python 3.12+;
- PyMuPDF;
- Pillow;
- pytesseract + Tesseract executable;
- RapidFuzz;
- NumPy;
- OpenCV headless if needed.

Agents MAY change libraries if they preserve contracts.

Agents MUST NOT add a second OCR engine merely to improve transcription accuracy.

A second engine is justified only by demonstrated failure of Tesseract at the geometry/layout task.

---

## 8. Confidence Authority

Confidence MUST describe evidential support, not model certainty theater.

High-confidence structure should correspond to observable signals such as:

- stable first-line indentation;
- large local vertical gap;
- repeated heading hierarchy;
- repeated stable page-margin furniture;
- strong alignment anchors.

Low-confidence structure MUST remain reviewable and must not be silently hardened into source fact.

---

## 9. Stop Conditions for Agents

An agent SHOULD stop the current line of implementation and surface the problem when:

- the requested behavior would require violating lexical immutability;
- page preprocessing makes reading order uncertain;
- alignment drifts without reliable resynchronization;
- geometry cannot distinguish body text from furniture on representative samples;
- success requires treating OCR transcription as canonical;
- success requires unrestricted semantic rewriting;
- an ambiguity cannot be resolved from authorized evidence;
- the probe acceptance criteria cannot be met.

Stopping with a precise failure report is valid goal progress.

---

## 10. Definition of Correctness

Correctness is not “pretty Markdown.”

Correctness is:

> the strongest reconstruction of document topology licensed by the scanned page, mapped onto the canonical extracted wording, with uncertainty and provenance preserved.

If a visually uglier output is better supported by the source than a prettier inferred output, the supported output wins.
