# Current scope and authority

Normalize currently implements only this workflow:

1. Scans directory → raw PaddleOCR JSON and Markdown in a Paddle directory.
2. Raw Paddle output directory → probe report of candidate errors, with deterministic
   punctuation-space proposals, original UTF-8 spans, and bounded OCR context
   already supplied by the probe.
3. Extractor → second report containing unchanged copies of punctuation-space
   findings only.
4. Codex in a separate review workspace with scans and report two → use the
   OCR context only to locate passages in the images, then approve accepted proposals;
   leave exception statuses unchanged, optionally add notes, and copy exceptions
   into report three.
5. Human-run executor → insert only explicitly approved proposed spaces from
   report two into copied Markdown. The full Paddle directory is copied to a new
   output first; JSON and assets remain unchanged machine observations.
6. Repaired output + original scans → Probe 2 of the actual repaired Markdown.
   The probe verifies the execution ledger, reverses recorded spaces only in an
   in-memory JSON comparison view, and checks source page/directory hashes.
   Explained JSON/Markdown discrepancies enter `json_markdown_exceptions`;
   unrelated differences remain findings. Fresh offsets address actual input.

Source scan pixels determine whether a proposed space belongs. Codex owns only
status/note edits in report two and the exceptions report. The executor owns only
mechanical application of approved proposals. Raw scans, raw Paddle output, and
the full probe report remain unchanged. No lexical replacement, alternative
replacement field, batch authorization stage, footnote linking, concatenation,
or compatibility path belongs to the current implementation.

No reviewer-edited comparison flag is added. Execution records alone supply
comparison semantics after validated application; the extractor copies input
provenance and findings intact. The review exceptions report is not the probe's
comparison exceptions audit. Invalid or old execution provenance fails closed.
This implements a single raw → whitespace stage, not a general history engine.
See [the maintained process document](../../docs/process.md).

The executor requires untouched report one only to validate the status/note-only
review contract; report two supplies approvals. All offsets refer to original
UTF-8 Markdown bytes. Multiple approved edits on one page are validated together,
then applied from right to left; overlapping ranges are errors. Output must be a
new directory outside raw Paddle input. No manual backup/copy step is required.

Each context excerpt carries raw-Paddle provenance, its original Markdown byte
range, and unchanged text. Finding ranges remain original repair coordinates;
they are not pixel coordinates. The extractor copies all context and spans
unchanged. Raw Paddle artifacts and report one belong to the separate execution
environment, not the reviewer inputs. The prompt must not require the reviewer
to open or hash files it cannot access. Ambiguous source occurrences remain
unapproved; context never replaces pixel inspection as approval evidence.
