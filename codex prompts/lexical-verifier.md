# Lexical verifier session — independent scan verification

Target book: {{BOOK_NAME}}

Access only the FROZEN lexical-proposals.json and the correct source scans. Read the local AGENTS.md. Optional segmentation suggestions or proposal notes are hints, NOT evidence. Do not inspect raw Paddle/Markdown, earlier review transcripts, full probe, executor, or writable shared lexicon.

Treat every non-null proposed value as an unverified claim from another agent. Locate the exact occurrence on the source scan. Compare ALL differences in the proposed replacement, including every changed, inserted or deleted glyph and word separator, to what was printed. Even a grammatical or dictionary-valid replacement can be wrong. The source may genuinely be printed ambiguously; Greek and Latin lookalikes require especially conservative scrutiny.

For an entire replacement unambiguously supported by the pixels, set review.status to "approved" and add a concise review.note describing direct visual evidence. Otherwise keep review.status null with an informative note. Never infer an approval from the absence of a contradiction. Findings with null proposed remain null. A lexicon_suggestion is *not* an approved lexicon entry; only the human can authorize global vocabulary via a different file.

Report integrity: modify ONLY review.status and review.note on existing findings. Keep every proposal, evidence note, lexicon_suggestion, input hash, offset, source path, vocabulary, finding ID, order and other field unchanged. Save a NEW lexical-reviewed.json without overwriting lexical-proposals.json. Never execute repairs. The human accepts/rejects your decisions before manually invoking the executor and separately authors any persistent lexicon approval file.