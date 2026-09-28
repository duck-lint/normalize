# Normalize fixture contract

This directory contains a small, intentionally selected development corpus for the layout-reconstruction probe:

- Einstein, *Relativity* — conventional prose, headings, figures/display math, page furniture, and cross-page continuation;
- McCarthy, *Stella Maris* — session headings and dense, unlabelled dialogue with wrapped turns.

These are the current probe and MVP acceptance source classes. Other books and layout classes are deferred validation, not current gates. The existing core/stretch fixtures are preserved; this corpus is not expanded by manufacturing additional hand-normalized examples.

Each fixture keeps three tracked, distinct artifacts:

- `*.raw.md` — the immutable raw/browser-extracted lexical substrate. Existing files preserve physical extraction line breaks; a future input may also be fully flattened. Raw line breaks can assist alignment but do not establish paragraph or block structure.
- `*.expected.json` — the human-reviewed structural oracle. Its assertions describe scan-visible layout and short locators into the raw substrate; they do not authorize lexical correction.
- `*.normalized.md` — a human-produced reference structural normalization for inspection and benchmarking. It is derived, non-authoritative, and not an exact whole-file output oracle.

The tracked Markdown files are textual excerpts used for development and fixture inspection. This README makes no claim about ownership, permission, or redistribution beyond describing what is present in this repository.

## Local PDF substrate

The fixture PDFs are required local inputs for executable geometry tests. They are intentionally ignored by Git and are not part of the tracked repository. A clean clone without these local PDFs cannot execute geometry-dependent tests. Such tests MUST fail or skip explicitly according to their test contract and MUST NOT silently substitute another source or report a geometry result without the PDF.

The `source_pdf` value in each `*.expected.json` names the exact sibling PDF expected locally. The current bindings are:

Each listed local PDF is a one-page fixture asset. `fixture_pdf_page_index_1_based` is the page index used to open that local asset and is `1` for every current fixture. `source_pdf_page_index_1_based` preserves the original source-PDF index as provenance; it is not a local runtime page selector.

| Source | Expected JSONs | Local PDF names |
| --- | --- | --- |
| Einstein, *Relativity* | `relativity_pdf10_pp26-27`, `relativity_pdf17_pp40-41`, `relativity_pdf23_pp52-53` | `Einstein, Albert - Relativity 10.pdf`, `Einstein, Albert - Relativity 17.pdf`, `Einstein, Albert - Relativity 23.pdf` |
| McCarthy, *Stella Maris* | `stella_maris_pdf03_session-I`, `stella_maris_pdf06_dense-dialogue`, `stella_maris_pdf18_session-II_p35` | `McCarthy, Cormac - Stella Maris.pt2 3.pdf`, `McCarthy, Cormac - Stella Maris.pt2 6.pdf`, `McCarthy, Cormac - Stella Maris.pt2 18.pdf` |

The numeric suffixes identify the local page/spread fixture asset; they are not a claim that the ignored PDF is a complete source work.

## Raster research evidence

PNG and PDF files are globally ignored and are not durable repository artifacts. Canonical/manual crop rasters and derived research page images may remain as local inputs only. Archived JSON and Markdown may preserve their paths, dimensions, and hashes as provenance; those records do not assert that the binary remains present in a checkout. Ordinary pixel-behavior tests generate controlled synthetic images at runtime. Manual raster recovery is an optional local audit when both canonical and manual inputs are available. Historical Git SHAs likewise remain provenance; reusable research checks validate current content hashes rather than requiring purged commit objects.
