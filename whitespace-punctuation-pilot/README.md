# Whitespace review handoff (book-agnostic)

This is a separate, deterministic stage **after** the existing OCR anomaly probe. It does not run OCR, replace the probe, or process lexical findings. It uses the original full findings report as input and produces a smaller report containing only findings whose *entire* trigger set is `punctuation_letter` and/or `period_capital`.

## 1. Prepare a Codex-only review batch

Run the existing probe as you normally do. Then:

```bash
python whitespace_review.py prepare \
  --report findings.baseline.json \
  --out whitespace_batch.json
```

`whitespace_batch.json` contains each selected finding's ID, page ID, image/Markdown location, exact UTF-8 byte offsets, `observed` span, complete `proposed` span, and triggers. Every proposal **only inserts ASCII spaces**. It does not contain `unrecognized_token`, lexical proposals, or the remainder of the original report.

## 2. Have Codex seek contradictions

Give Codex **only** `whitespace_batch.json`, access to the corresponding source scans (and optionally the original page Markdown for locating passages), plus `codex_whitespace_exceptions_prompt.md`. Do **not** give Codex `findings.baseline.json` in this task. Have Codex process the batch in bounded page groups, not by printing the entire JSON into one context window.

Codex writes `whitespace_exceptions.json` with this shape:

```json
{
  "checked_pages": ["<actual page id>"],
  "exceptions": [
    {"id": "<exact finding id>", "reason": "<source-based objection or uncertainty>"}
  ]
}
```

Codex **does not** edit findings, make repairs, or assign `review.status`.

## 3. Human reviews exceptions; batch authorizes uncontested proposals

First preview **without** changing anything:

```bash
python whitespace_review.py authorize \
  --report findings.baseline.json \
  --batch whitespace_batch.json \
  --exceptions whitespace_exceptions.json \
  --out findings.reviewed.json \
  --require-complete
```

After you've reviewed objections and chosen to accept the risk that Codex missed some, explicitly authorize:

```bash
python whitespace_review.py authorize \
  --report findings.baseline.json \
  --batch whitespace_batch.json \
  --exceptions whitespace_exceptions.json \
  --out findings.reviewed.json \
  --require-complete \
  --approve-uncontested
```

Only uncontested findings on `checked_pages` receive `review.status: "approved"`. Exceptions, unchecked pages, and **every non-whitespace finding** remain untouched in the full report. `--require-complete` ensures all candidate pages were declared checked before authorization. This verifies reported coverage, not the truthfulness of Codex's inspection.

The script rejects altered batches, unknown exception IDs, invalid replacement spans, changed original proposals, and accidental output overwrites. The original baseline is never modified.

## 4. Feed the unchanged executor

The existing `execute_repairs.py` remains the downstream consumer:

```bash
python execute_repairs.py \
  --baseline findings.baseline.json \
  --report findings.reviewed.json \
  --paddle original-paddle.zip \
  --out repaired
```

This is a dry run. Add `--execute` only when ready to produce separate derived Markdown files. The executor checks original file hashes and exact byte spans.

## Out of scope

Lexical/unrecognized-token findings remain in the original full report for a **separate** task. This handoff neither sends them to Codex nor changes their proposals or statuses.
