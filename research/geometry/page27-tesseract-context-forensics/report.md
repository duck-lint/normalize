# Page 27 Tesseract Context-Sensitivity Forensics

## Result

**Decision: `full_page_context_segmentation_failure`.** With the exact source
pixels, OCR configuration, and resolution held fixed, a broad text-column crop
changes the full-page multirow observation into partial word geometry; a
smaller crop that still contains the target and its adjacent physical rows
produces seven ordinary word boxes spanning the visible target row. The
upstream observation is context-sensitive. This demonstrates a segmentation
context effect; it does not establish one unique physical feature as its
mechanism.

## A. Full-page reproduction

The source is `fixtures/einstein/spineless/pg.27.jpg`, SHA-256
`d2ca32d3924df8f2e41db6f0d12bf387bb127aed405b9aead7759a297018b490`. Reusing
the prior `[0,0,1500,2340]` crop and `-0.9399999999999995°` Pillow deskew
reproduced the 739×1136 raster hash
`891fd22858854195cb20e8a60561b8c9073a014c4678e48f5f527cb5806a75d1`. The
runtime was Tesseract 5.3.4 with language `eng`, `--psm 6`, called via
`pytesseract.image_to_data(..., output_type=Output.STRING)`. Full-page TSV hash
matched the prior value exactly:
`f74204417cb310096d4993a1606d38a01d20ff3835c59d293c235e1aed65cd72`.

The fixed target ink is the highlighted row at x≈118–641, y=671–685:
“affords an insufficient foundation for the physical.” The immediately
preceding row occupies y=643–657; the following highlighted row occupies
y=699–719. Target highlight pixels span approximately x=118–622 and
y=670–693. The OCR-independent pixel bounds and crop definitions are recorded
in `crop-manifest.json`.

Full-page raw TSV has a line-level hierarchy row 189 at `[7,640,639,696]`
(level 4, line 22), then two word-level records intersecting the target:

| TSV row | IDs page/block/par/line/word | text locator | confidence | page box |
|---:|---|---|---:|---|
| 190 | 1/1/1/22/1 | `See` | 14.663147 | `[7,640,624,696]` |
| 191 | 1/1/1/22/2 | `ae` | 33.175888 | `[625,671,639,686]` |

The first box is 617×56 px and spans both the preceding physical row and the
target row. The second is a 14×15 px fragment at the target row's far right.
The target outcome is therefore `multirow_merged_observation`. The records
are raw word-level TSV; no production admission or geometry stage was run.

## B–E. Crop matrix and raw TSV evolution

All crop rectangles use page coordinates `[x0,y0,x1,y1]`, are direct Pillow
views of the saved raster, and are neither resized nor deskewed. The matched
highlighted control is the next row, “description of all natural phenomena,”
and receives the same crop dimensions translated down 31 px (except the
full-page control, which is the same page).

| Crop | Target bounds | Control bounds | Target raw outcome | Control raw outcome |
|---|---|---|---|---|
| A full page | `[0,0,739,1136]` | same | multirow merged | normal per-word |
| B text column, broad vertical | `[105,575,665,755]` | `[105,606,665,786]` | partial per-word | normal per-word |
| C target + adjacent rows | `[105,632,665,731]` | `[105,663,665,762]` | normal per-word | normal per-word |
| D target + vertical padding | `[105,660,665,696]` | `[105,691,665,727]` | normal per-word | normal per-word |
| E tight target neighborhood | `[110,660,650,696]` | `[110,691,650,727]` | normal per-word | normal per-word |
| Bx full width, broad vertical | `[0,575,739,755]` | `[0,606,739,786]` | multirow merged | normal per-word |
| Bx left margin, broad vertical | `[0,575,665,755]` | `[0,606,665,786]` | multirow merged | normal per-word |
| Bx left edge trimmed | `[70,575,665,755]` | `[70,606,665,786]` | partial per-word | normal per-word |
| Bx right margin, broad vertical | `[105,575,739,755]` | `[105,606,739,786]` | partial per-word | normal per-word |

The first improvement away from the full-page merged class is B, which retains
only the text-column width and a broad vertical neighborhood. B still has
partial geometry: several boxes are normal-sized, but `insufficient` and
`foundation` are emitted as 3×2 px fragments. C is the first crop with a
complete usable per-word observation: seven boxes cover the target from x=124
to x=639, with heights 10–21 px. D and E retain the same seven page-coordinate
boxes as C.

The horizontal diagnostic holds y=575–755 fixed. At x=105–665 the target is
partial; extending left to x=0 makes Tesseract emit multirow-sized boxes
(`Se` `[7,640,248,696]` and `oo` `[344,671,639,686]` in the left-only
variant). Trimming the left boundary to x=70 returns to partial geometry.
Extending only the right side also gives partial geometry. Thus inclusion of
the far-left strip x=0–69 is associated with the severe multirow form. The
source pixels show a dark vertical scan-edge mark in that strip around the
affected y range. These crops localize a context association; they do not
prove that the mark itself, rather than crop framing around it, is the unique
cause.

The vertical comparison holds x=105–665 fixed: broad B is partial, while C,
which removes more distant rows but retains the target and adjacent rows, is
normal. Context outside the target neighborhood also affects segmentation.
The crop results do not isolate which particular removed row or blank region
matters.

## F–H. Context, highlighting, and matched control

The neighboring highlighted control row is recognized as nine ordinary
word-level boxes in the full-page control and remains per-word across every
matched crop. Its segmentation class is therefore not damaged by the same
context changes, although some confidence values change substantially (two
control words receive confidence `0.0` in D/E while retaining ordinary
spatial boxes). Crop context can affect OCR measurements even when word-box
geometry remains usable.

The target is visibly highlighted in the original pixels and becomes
per-word-observable in C–E without recoloring or changing pixels. The adjacent
highlighted control is also recognized on the full page. This evidence does
not support highlighting as a sufficient explanation for the target failure;
it does not exclude a highlight interaction specific to this target's other
visual/context properties.

## I. Determinism

Every target and matched-control crop was OCRed twice with identical pixels
and arguments. All repeated raw TSV SHA-256 pairs match, and the extracted
word identities/boxes also match. The full-page TSV reproduced the archived
hash. `raw-tsv-comparison.json` contains the per-run hashes and records.

## J. Interpretation

The full-page OCR failure is reproducible, but it is not a stable local-image
failure: unchanged target pixels yield usable seven-word geometry under C–E.
Reducing the far-left and distant vertical context changes Tesseract's raw
segmentation. Because both the visible target and adjacent highlighted
control remain physically unchanged, the outcome is specific to the target
region's interaction with its surrounding context. The strongest spatial
association is the far-left strip with a visible dark scan-edge mark; the
experiment does not prove a single-feature cause.

## K. Candidate future question

At fixed crop dimensions and target position, does the far-left scan-edge mark
itself drive the merged observation, or does merely moving the crop boundary
past x≈70 change Tesseract's segmentation?

## L. Scope and verification

Research artifacts are confined to this directory. No production OCR,
preprocessing, geometry, PSM, image resolution, or source image was changed.
The primary analysis did not run Normalize grouping or admission. Crop outputs
are JSON records only; no raster files are committed.
