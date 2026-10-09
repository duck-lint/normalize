# Current scope and authority

Normalize currently implements only this workflow:

1. Scans directory → raw PaddleOCR JSON and Markdown in a Paddle directory.
2. Raw Paddle output directory → probe report of candidate errors, with deterministic
   punctuation-space proposals already supplied by the probe.
3. Extractor → second report containing unchanged copies of punctuation-space
   findings only.
4. Codex in a separate book workspace → approve accepted proposals in report two;
   leave exception statuses unchanged, optionally add notes, and copy exceptions
   into report three.
5. Human-run executor → insert only explicitly approved proposed spaces from
   report two into copied Markdown. The full Paddle directory is copied to a new
   output first; JSON and assets remain unchanged machine observations.

Source scan pixels determine whether a proposed space belongs. Codex owns only
status/note edits in report two and the exceptions report. The executor owns only
mechanical application of approved proposals. Raw scans, raw Paddle output, and
the full probe report remain unchanged. No lexical replacement, alternative
replacement field, batch authorization stage, footnote linking, concatenation,
or compatibility path belongs to the current implementation.

The executor requires untouched report one only to validate the status/note-only
review contract; report two supplies approvals. All offsets refer to original
UTF-8 Markdown bytes. Multiple approved edits on one page are validated together,
then applied from right to left; overlapping ranges are errors. Output must be a
new directory outside raw Paddle input. No manual backup/copy step is required.
