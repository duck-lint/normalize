# Process
1. scan book with Canon imageFORMULA R30 Office Document Scanner
2. get JPGs from scans
3. run JPGs through PaddleOCR, producing x1 JPG per scan
4. normalize and append `.md` files with an output report flagging any leftover ambigous text.

# Authority
- JPG scans retain lexical and structural authority, not `.md` files from PaddleOCR

# Invariants
- superscripts in prose must be preserved in `.md` prose and reflected in Obsidian `.md` syntax ([^1] superscipt in prose linked to lines after main book body text)