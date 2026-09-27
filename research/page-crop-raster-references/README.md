# Canonical page-side raster references

These twelve PNGs were rendered from the original fixture PDFs using the production page selection, PDF rendering, configured orientation/crop/deskew steps, and left/right split. The reference render is **300 DPI**. The embedded scans are nominally 300 DPI, but their PDF image-placement transforms are not exact pixel-grid quarter-turns, so the production PDF renderer must resample them. The requested 300-DPI renderer fallback is used. The current production raster is 144 DPI; reference coordinates map to production page-side coordinates by the exact ratio **12/25** on each axis. The manifest records source PDF hashes, fixture pages, render dimensions, split positions, side dimensions, and PNG hashes.

You may crop these PNGs manually to mark the intended page boundary. The edited image MUST remain a literal rectangular pixel subset of its supplied PNG. Do not:

- rotate or deskew;
- resize or resample;
- perspective-correct;
- adjust color, contrast, brightness, or sharpness;
- re-render through PDF or another image pipeline.

Remove any desired number of pixels from the top, bottom, left, and right. Save the result as a lossless PNG, preserving RGB pixels exactly.

After editing, use `recover_crop.py` with the canonical reference first and the edited crop second. On one unique exact match it prints `[x0, y0, x1, y1]` in canonical side-local pixels, using an exclusive right/bottom edge. It rejects transformed or modified images and reports ambiguity if identical content occurs at multiple positions. The utility never estimates or corrects a transform.
