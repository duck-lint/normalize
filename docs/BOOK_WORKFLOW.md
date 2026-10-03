# Whole-book workflow architecture

Normalize separates fixed engine semantics from data describing a particular
book, from orchestration state, and from review evidence.

```text
BOOK SOURCE (ordered page images + canonical raw text)
                    ↓
              BookManifest
                │       │
                │       └── calibration measurements
                │                    ↓
                │               BookProfile
                │                    ↓ freeze
                └────────────────────┐
                                     ↓
                               GLOBAL ENGINE
                                     ↓
                                  BookRun
                               /           \
                              ↓             ↓
                     normalized.md     ReviewReport
```

> Per-book calibration is allowed to describe the book. It is not permission
> to tune the engine until the book passes.

## Global Engine

The engine owns fixed preprocessing, OCR, geometry, canonical alignment,
reconstruction, and Markdown semantics. The v1 book adapter applies calibrated
source-pixel bounds, quarter-turn orientation, the established bicubic
expanded white-fill rigid deskew, and the fixed 144-DPI LANCZOS sampling
transform. It calls the shared raster preprocessing stage. It then uses the
existing Tesseract `eng --psm 6` geometry observer and the existing downstream
stages. Book identifiers and calibration provenance do not select algorithms.
Engine configuration is identified in every run record; no profile field can
override algorithmic thresholds or OCR settings.

## BookManifest

`book-manifest-v1` describes an ordered collection of physical page images,
stable page IDs, source hashes (computed at manifest load when not supplied), source DPI, canonical raw-text path,
and optional half-open canonical character spans. Page images are a first
class source; a book need not first be assembled into a PDF. A whole-book run
requires spans for every page, in source order, covering the canonical text.
Normalize refuses to guess missing spans.

## BookProfile v1

`book-profile-v1` is bound to a manifest identity digest covering the ordered
page identities/source hashes, canonical source hash and source spans, plus
the book identifier. It contains source DPI, calibration page IDs, per-page
content rectangle or full-page/unresolved status, quarter-turn orientation,
rigid deskew angle, explicit no-transform/unresolved states, source-DPI
provenance, and measurement source/note provenance. Supported sources are
`human`, `measured`, `detector`, and `imported`. Content bounds use source-image
pixels before orientation.

V1 deliberately excludes paragraph spacing thresholds, OCR confidence cutoffs,
alignment weights, heading/display scores, and other algorithm knobs. Those
belong to the global engine, not the book profile.

Manual measurement is the supported calibration workflow. Measurements enter
as a draft and are validated against the manifest and source image dimensions;
`normalize calibrate freeze` writes a frozen value with an integrity digest.
Normal loading rejects edited frozen contents. A run requires that frozen
state. Recalibration uses an explicit new revision via the
calibration API; it never retunes or rewrites a profile during a run.

Typical command sequence:

```text
normalize book validate --manifest book.json
normalize calibrate freeze --manifest book.json --measurements calibration.json \
  --profile-id my-book --output profile.json
normalize run --manifest book.json --profile profile.json --output book-run/
```

To freeze revised measurements, pass `--previous-profile profile.json` and the
same `--profile-id`; the new profile revision increments explicitly.

## BookRun and resumability

`normalize run` processes pages in manifest order and writes `run.json`,
`normalized.md`, `provenance.json`, `review.json`, and per-page geometry,
alignment, and processing records under `pages/<page-id>/`. Run identity binds
manifest, profile, canonical text, engine/build, and fixed config hashes.

Page geometry is independently cached by source hash, page calibration, and
engine identity. Matching completed page results can be reused; changed source,
calibration, or engine identity invalidates that page's cached observation.
Alignment and reconstruction are regenerated from the current canonical
source on every run. A failed page is recorded and processing continues. Its
canonical span remains in output with absent spatial evidence, and the page
failure is surfaced in review rather than silently omitting its words.

## Review and correction boundary

The review report aggregates actual stage diagnostics: page failures, geometry
errors/uncertainties, unmatched canonical material, unmatched OCR anchors,
alignment ambiguity, and reconstruction diagnostics. It does not score,
correct, or feed changes back into engine/profile state.

Future manual corrections belong in a separately identified correction layer:

```text
source evidence → engine result → review/correction layer → reviewed projection
```

They must not overwrite source observations or mutate a frozen BookProfile.
The existing fixture-PDF preprocessing commands remain available as low-level
fixture tooling and are not the definition of a book source.
