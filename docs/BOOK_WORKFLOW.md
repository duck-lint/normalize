# Whole-book workflow architecture

Normalize accepts physical scans as a first-class source. An independent,
complete transcription can strengthen lexical evidence, but it is optional.

> An external complete transcription is optional. Scan-only books are a
> first-class production input.
>
> OCR is lexical evidence, not independent lexical authority.

```text
V2 SCAN-ONLY PRODUCTION PATH (available now)
ordered page images → BookManifest v2 → calibration → BookProfile v2
                              ↓
                     page observation
                      ├─ geometry / spatial evidence
                      └─ LexicalObservation
                              ↓
                   LexicalTranscript
                              ↓
                reconstruction → BookRun
                               /       \
                    normalized.md   ReviewReport

V1 EXTERNAL-TEXT CONTROLLED PATH (available now)
BookManifest v1 + external raw text + explicit spans
                         ↓
             reconstruction with page geometry

FUTURE V2 RECONCILIATION CAPABILITY
additional observers or external lexical evidence
                         ↓
         reconciliation with a v2 LexicalTranscript
```

## Authority layers

- Source pixels are authoritative for physical page content, geometry, layout,
  and acquisition evidence.
- Recognition systems report lexical observations from those pixels. OCR text
  is evidence and retains the observer's wording, confidence, and provenance.
- An independently obtained edition-matching text is optional stronger lexical
  evidence. It remains identified as an external source.
- `LexicalTranscript` is the working lexical input to reconstruction. A
  scan-derived transcript is derived recognition output, can be uncertain, and
  is never called canonical merely because no other text exists.
- Markdown is derived from the transcript, spatial evidence, and structural
  inference. Explicit human corrections belong in a separate future review
  layer and do not overwrite observer records.

## BookManifest

`book-manifest-v2` is the preferred scanned-book contract. It contains a book
identifier, source DPI, and ordered page IDs, image references, and source
hashes. It has no text path or character spans. Its identity is based on the
physical source identity and order. Changing lexical evidence does not change
that identity.

`book-manifest-v1` remains a legacy controlled workflow contract. It declares
an external raw-text path and may declare manually supplied page spans. It is
not the recommended contract for a new scanned book. V1 records are not
silently reinterpreted or rewritten.

## BookProfile contracts

`book-manifest-v1` pairs with `book-profile-v1`. That legacy controlled
workflow preserves the historical `manifest_sha256` binding, including its
external text identity.

`book-manifest-v2` pairs with `book-profile-v2`. Its explicit
`physical_manifest_sha256` binds calibration to physical source identity only.
It does not depend on OCR wording, transcript identity, or external text
hashes. A v2 profile can be drafted and frozen with no lexical source. The two
profile versions are validated only with their matching manifest versions.

Profile bounds use source-image pixels before orientation. The profile cannot
override OCR settings, alignment costs, structural thresholds, or other engine
semantics. Manual measurements enter as a draft and `normalize calibrate
freeze` writes a frozen value with an integrity digest.

## Page observations and transcripts

One page observation pass invokes Tesseract once. Its TSV response supplies
both existing geometry anchors and a `LexicalObservation`; recognition is not
repeated to construct text evidence. Observations retain page ID, source image
hash, observer identity, token IDs/text/confidence/anchors, and factual
diagnostics. Failed pages remain present with failed, empty observations.

`single-observer-transcript-v1` is the scan-derived transcription baseline. It
projects each page's observed word rows in Tesseract TSV row order, including
word rows whose spatial geometry was rejected. It preserves page boundaries
and creates ordered page and token ranges automatically. This is a lexical
sequence only; it does not introduce paragraph, heading, or other document
structure. Confidence and malformed-observation diagnostics are carried into
review. Tesseract confidence is observer evidence, not a correctness score.

This transcript is not independent verification of wording. Its lexical
tokens and spatial anchors come from the same recognizer, so successful
alignment to those anchors establishes spatial association and structure only;
it does not confirm lexical correctness. Additional observers or an external
text source may support future lexical reconciliation without changing
BookManifest or BookProfile identity. In this release, external lexical text
is wired through the legacy v1 controlled path; attaching it to a v2 run is
not yet supported.

Legacy v1 manifests with complete contiguous spans can still use their
independent text as explicit external lexical evidence. The low-level
`normalize reconstruct --raw --geometry --spans` command also remains available
for controlled experiments.

## BookRun and resumability

`normalize-book-run-v2` records the physical manifest and profile identities,
page observation identities, transcript method and identity, optional external
source, reconstruction engine, outputs, and review diagnostics. A scan-only
run needs only ordered page images and a frozen physical profile:

```text
normalize book validate --manifest book.json
normalize calibrate freeze --manifest book.json --measurements calibration.json \
  --profile-id my-book --output profile.json
normalize run --manifest book.json --profile profile.json --output book-run/
```

The per-page cache contains geometry and lexical observation from one OCR pass.
It depends on source pixels, physical calibration, and observation engine
identity. Transcript and reconstruction outputs are regenerated from cached
observations, so transcript-method or external-text changes do not require
reprocessing unchanged page images. A failed page remains in manifest order,
has an empty failed lexical observation, and makes the run failed with review
evidence.

## Review and correction boundary

Review aggregates actual observer uncertainty, OCR failures, geometry errors,
unmatched transcript material, unmatched spatial anchors, and ambiguous
alignment. It does not score correctness or feed changes back into engine or
profile state. Human corrections must be explicit, separately identified, and
must preserve the original observation.

Fixture-PDF preprocessing remains available as low-level tooling and does not
define the production book source contract.
