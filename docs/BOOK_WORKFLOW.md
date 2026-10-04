# Whole-book workflow architecture

Normalize accepts physical scans as a first-class source. An independent,
complete transcription can strengthen lexical evidence, but it is optional.

> An external complete transcription is optional. Scan-only books are a
> first-class production input.
>
> OCR is lexical evidence, not independent lexical authority.

```text
V2 PHYSICAL SOURCE / CALIBRATION PATH
ordered page images
        ↓
BookManifest v2
        ↓
any calibration proposer
        ↓
CalibrationProposal ─── method-specific evidence (by digest)
        ↓
human review → explicit calibrate accept
        ↓
BookProfile v2 draft → calibrate freeze
        │
        └──────────────────────────────────────────┐
                                                   ↓
PAGE OBSERVATION                              page pixels
        ├─ geometry / spatial evidence              │
        └─ LexicalObservation ← one OCR pass ───────┘
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
semantics.

## Calibration proposals and acceptance

`calibration-proposal-v1` is a physical-source-bound evidence artifact. It
contains a stable content-derived proposal identity, `book_id`,
`physical_manifest_sha256`, generic producer provenance (`source`, `method`,
`evidence_sha256`, and `note`), and ordered sparse per-page values. A page may
propose `content_bounds`, `orientation_degrees`, and/or `deskew_degrees`.
Omitted fields mean no proposal for that field; null is not used to mean
unresolved or to clear an existing value. Proposal identity excludes local
paths and output locations. Method-specific evidence stays outside this
contract and is referenced by its digest.

CalibrationProposal values are proposed evidence, not profile authority.
Accepting a proposal is an explicit human authorization event. It does not
rewrite or upgrade the quality of the originating evidence.

Create an unresolved `book-profile-v2` draft for the physical manifest, then
create and inspect a proposal. Proposal validation checks it against the
manifest without requiring a profile:

```text
normalize calibrate draft --manifest book.json --profile-id my-book \
  --output profile-draft.json
normalize calibrate proposal create --manifest book.json --values values.json \
  --evidence measurement-evidence.json --source imported \
  --method scanner-import-v1 --note "Imported physical calibration" \
  --output proposal.json
normalize calibrate proposal validate --manifest book.json --proposal proposal.json
```

Acceptance requires an explicit page selection (`--page-id` or `--all`) and an
explicit field selection (`--field` or `--all-fields`). It changes only the
selected values in the input v2 draft and writes a new draft plus a structured
acceptance record. `content_bounds` maps to `content_status=measured` after
human authorization; orientation and deskew map to their existing measured or
no-transform states. Other values, fields, and pages retain their prior
values. Accepted rows use `source=human` and retain the proposal ID, producer,
method, and evidence digest in their note. Partial or uncertain evidence may
still be accepted; core preserves its reference without interpreting its
method-specific meaning.

```text
normalize calibrate accept --manifest book.json --profile profile-draft.json \
  --proposal proposal.json --page-id page-001 --field deskew \
  --output accepted-profile.json
normalize calibrate freeze --manifest book.json --profile accepted-profile.json \
  --output frozen-profile.json
```

Acceptance keeps the draft revision and never freezes it. Freezing is a
separate profile integrity operation.

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
normalize calibrate freeze --manifest book.json --profile accepted-profile.json \
  --output profile.json
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
