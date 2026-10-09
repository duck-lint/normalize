# Current scope and authority

Normalize currently implements only this workflow:

1. Scans → raw PaddleOCR JSON and Markdown.
2. Raw Paddle output → probe report of candidate errors, with deterministic
   punctuation-space proposals already supplied by the probe.
3. Extractor → second report containing unchanged copies of punctuation-space
   findings only.
4. Codex in a separate book workspace → approve accepted proposals in report two;
   leave exception statuses unchanged, optionally add notes, and copy exceptions
   into report three.
5. Human-run executor → insert only explicitly approved proposed spaces from
   report two into separate derived Markdown.

Source scan pixels determine whether a proposed space belongs. Codex owns only
status/note edits in report two and the exceptions report. The executor owns only
mechanical application of approved proposals. Raw scans, raw Paddle output, and
the full probe report remain unchanged. No lexical replacement, alternative
replacement field, batch authorization stage, footnote linking, concatenation,
or compatibility path belongs to the current implementation.
