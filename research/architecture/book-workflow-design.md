# Book workflow boundary design

## Reconnaissance

The production package is `src/normalize`. `cli.py` owns the command surface;
`rendering.py` owns fixture-PDF preprocessing; `geometry.py` runs Tesseract and
forms `geometry-probe-v1`; `alignment.py` owns monotonic canonical/OCR matching;
`reconstruction.py` maps page-scoped canonical spans to structural blocks; and
`markdown.py` emits Markdown plus a provenance record. `fixtures.py` is a
fixture-catalog loader, not a production book model.

The current `reconstruct` command is the only end-to-end command. It accepts a
raw lexical file, geometry JSON, and ordered character spans, and does not
consult normalized/expected fixtures. Geometry records retain tokens, boxes,
physical lines, uncertainty/errors, engine metadata, and preprocessing
provenance. Alignment retains matched and unmatched canonical/anchor records;
reconstruction blocks retain canonical spans and physical-line/anchor IDs.

The project authority is defined by `harness/project-spec/PROJECT_SPEC.md` and
`harness/project-spec/AUTHORITY.md`: pixels govern layout, raw text governs
wording, OCR is locating evidence, and uncertain reconstruction stays
reviewable. Existing preprocessing configuration is fixture-specific and
requires six known fixture identifiers. Reusing it for books would preserve a
fixture assumption, so the book path will instead call the same Pillow
transform semantics and the existing geometry/alignment/reconstruction
primitives through a book-neutral engine adapter.

## Boundary choice

Add independent contracts for `BookManifest`, frozen `BookProfile`,
`BookEngine`, `BookRun`, and `ReviewReport`. Manifest order and canonical spans
are explicit. Profile v1 contains only source DPI with provenance, content
bounds, rigid deskew/orientation, lifecycle, and measurement provenance. It has no algorithm thresholds
or book-selected OCR/reconstruction controls. Profiles are immutable value
objects after loading/freezing; recalibration creates an explicit next revision.

The runner processes page images in manifest order. Per-page engine records are
keyed by source hash, page calibration, and engine identity so completed page
observations can be reused only when those inputs match. Page errors are
recorded without dropping their canonical spans; reconstruction receives an
empty geometry observation for failed pages so the canonical text remains in
the emitted document and the missing spatial evidence appears in review.

The new book path uses RGB decoding, half-open crop bounds, then the existing
Pillow bicubic expanded white-fill rigid rotation convention. It passes the
resulting in-memory image to the same fixed Tesseract `eng --psm 6` geometry
observer. It does not alter the established algorithms or their defaults.

## Safe limits

Page-to-canonical spans are optional manifest metadata, but a whole-book run
requires complete spans before it can align pages deterministically. The first
version does not guess spans. Manual profile measurements are supported and
their provenance is retained. Review aggregates facts; corrections remain a
separate future artifact and never rewrite source observations or a frozen
profile.
