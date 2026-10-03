# Canonical alignment and reconstruction implementation note

## Starting state

The implementation branch is created from current `guh` at
`473e639b6fe335ffb527d2338234d38e311189ba`. The only pre-existing worktree
addition is the user-provided, untracked `fixtures/einstein/spineless/` input
directory. The pre-change production test baseline is being run before code
changes.

## Existing contracts

- `normalize.geometry.run_geometry` publishes `geometry-probe-v1`. Its `pages`
  records retain page keys/dimensions, token identities (`token_id`, original
  TSV row, OCR text/confidence and box), physical line identities and token
  membership, unresolved line assignments, and measured line gaps/positions.
- Geometry page order and physical-line order are explicit. Those are layout
  observations, not paragraph boundaries.
- `fixtures/einstein/*.raw.md` is the canonical physical-line-preserving text.
  Existing `*.expected.json` records are reviewed structural oracles; the
  `*.normalized.md` files are human reference projections. Production code
  must receive raw text and geometry directly and must not load either oracle.
- `normalize.cli` currently exposes environment, fixture, preprocessing, and
  geometry commands. No production alignment, reconstruction, or Markdown
  emission stage exists.
- The three reviewed fixture pairs cover paragraph continuation and page
  furniture (pp. 26–27), a prose-interrupting figure (pp. 40–41), and display
  math interleaved with prose (pp. 52–53). Their oracles establish these as
  distinct structures; raw line wrapping alone cannot establish them.

## Implementation boundary

The consumer will accept a canonical text source plus ordered page geometry.
Canonical tokens retain original character offsets and only supply emitted
wording. OCR tokens are ordered spatial anchors and may be unmatched,
fragmented, merged, or malformed. Alignment will be monotonic and preserve
unmatched canonical spans and unmatched anchors in its result. Reconstruction
will use physical-line positions, indentation, gaps, and isolation as evidence;
it will not translate every physical line into a Markdown break.

The acceptance adapter may supply already-established page-to-raw spans as
input provenance. Those spans are acquisition metadata, not runtime
structural-oracle content. Production alignment/reconstruction receives only
the selected canonical source text and page geometry. Oracle comparison runs
after output generation.

## Uncertainty boundary

The accepted figure/math expectations describe structures that must survive
in the document model. OCR token boxes can locate their text but do not reveal
image content. Reconstruction may therefore emit a non-transcribed figure
block or display-math block only when the geometry and canonical span support
that classification; otherwise it must retain the canonical text and report
the unresolved structural decision. It must not invent a caption, equation,
or heading wording.
