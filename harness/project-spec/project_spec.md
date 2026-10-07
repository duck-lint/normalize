# Process
1. scan book with Canon imageFORMULA R30 Office Document Scanner
2. get JPGs from scans
3. run JPGs through PaddleOCR, producing x1 `.md` per JPG
4. normalize and append `.md` files with an output report flagging any leftover ambigous text.

# Authority
- JPG scans retain lexical and structural authority, not `.md` files from PaddleOCR

# Invariants
- superscripts in prose must be preserved in `.md` prose and reflected in Obsidian `.md` syntax ([^1] superscipt in prose linked to lines after main book body text)
- substantive footnotes/endnotes must never be dropped;
- note-call superscripts in prose must survive and remain linkable to their note;
- page furniture such as page numbers/running headers may be excluded from body Markdown but must remain observable in the raw Paddle artifact;
- raw Paddle output must be preserved unmodified before Normalize applies any policy or repair.