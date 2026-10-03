# Downstream reconstruction contract

> This document records the original low-level raw-text reconstruction
> boundary used by controlled fixtures. Production book runs now adapt a
> `LexicalTranscript` plus ordered page geometry into the same reconstruction
> implementation. Scan-only OCR wording is derived evidence, not canonical
> text. External raw text remains optional. See `docs/BOOK_WORKFLOW.md`.

The original low-level downstream boundary is:

```text
canonical raw source + geometry-probe-v1 pages + source page spans
    → monotonic alignment
    → conservative structural blocks
    → normalized Markdown + provenance sidecar
```

## Historical fixture authority

For this explicit raw-text path, supplied text provides emitted words. OCR
locates lexical tokens against geometry. A token with no usable anchor remains in output and
is listed as unmatched. OCR-only anchors remain in the alignment result and
never enter prose. `*.expected.json` and `*.normalized.md` are acceptance
material; the production reconstruction modules do not import or read them.

Page spans are explicit caller-supplied character offsets into the decoded raw
source. They retain source ID and original offsets. Gaps outside the selected
page spans and canonical tokens with no OCR match receive machine-readable
diagnostics. Page order must agree with source order and spans may not overlap.

## Alignment

`normalize.alignment.tokenize_canonical` uses non-whitespace lexical units and
retains each source character span. `matching_form` applies NFKC, case folding,
and punctuation normalization only to the temporary match key. Canonical
spelling is never replaced.

`align_monotonic` uses dynamic programming over ordered token sequences.
Canonical and OCR gaps cost 0.82. A one-token substitution requires at least
0.68 character similarity. A 1:2 or 2:1 merged/split match requires 0.88
similarity after token concatenation. These asymmetric bounds allow ordinary
single-token OCR noise while requiring near identity when token boundaries
change. Matches that miss the bound become explicit gaps. Equal-cost global
paths are reported as sequence-level ambiguity; the implementation does not
mislabel every selected link as uncertain.

Alignment links retain canonical token indices, OCR token IDs, physical-line
IDs, relation kind, and cost. Unmatched canonical indices and OCR IDs remain
in the result and serialized sidecar.

## Reconstruction

`normalize.reconstruction.reconstruct_document` reads only the provided raw
string and geometry page records. Physical lines provide grouping and
position evidence, never automatic Markdown breaks. A new prose paragraph
requires a stable first-line inset between 1.4 and 3.0 typical line heights
relative to the page's flush edge, plus a left-edge change relative to the
preceding band, or a vertical gap greater than 0.8 typical line heights. The
upper inset bound treats very large offsets as detached line fragments rather
than paragraph indentation. A page boundary alone does not split a paragraph.
If canonical order maps backward in page y, that transition cannot create a
boundary and an order-conflict diagnostic is recorded.

Headings require a centered cluster within the top 22% of a page, line height
at least 1.05 times the median body line height, and a gap of at least 1.5
body line heights before body text. Figures require a caption locator plus at
least three sparse lines within seven typical line heights. Display math
requires a centered line no wider than 65% of the page, at most six canonical
tokens, and formula-like characters or a short numeric expression. These are
conservative geometric candidates, not semantic recognition; weak or absent
evidence remains visible in diagnostics and the canonical wording remains
present.

The structural block model currently includes `heading`, `paragraph`,
`figure`, and `display_math`. Figure and math text, when included, comes from
canonical spans. The figure marker may be placed inline between surrounding
prose when their geometry supports paragraph continuity. A display-math block
remains separate in Markdown; its relationship to surrounding prose is
available through block order and provenance.

## Command

```bash
normalize reconstruct \
  --raw source.raw.md \
  --geometry geometry.json \
  --spans page-spans.json \
  --output normalized.md \
  --sidecar normalized.provenance.json
```

`geometry.json` uses the existing `geometry-probe-v1` schema. `page-spans.json`
contains an ordered `pages` array, each item with `page_id`, `start`, `end`,
and optional `page_index`. `start` and `end` are decoded Python character
offsets, with the right edge exclusive. No fixture catalog is needed by this
command.
