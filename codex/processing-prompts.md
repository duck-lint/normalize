# 1

Please audit the complete PaddleOCR output for the present book in the repo against the corresponding source page scans.

This is a REVIEW-ONLY pass. Do not modify source scans, Paddle JSON, Paddle Markdown, or any derived Markdown.

For every page, compare:
- the source scan;
- the corresponding Paddle _res.json;
- the corresponding Paddle .md.

Report only concrete transcription or structure defects supported by the source pixels. Do not make stylistic edits, modernize spelling, regularize punctuation, improve prose, or infer missing wording from context alone.

Pay particular attention to:
- OCR character/word errors;
- fused or missing spaces;
- incorrect dehyphenation;
- omitted substantive text;
- note-call numerals/superscripts;
- footnote text and footnote numbering;
- headings misclassified as prose or prose misclassified as headings;
- reading-order errors;
- substantive material mistakenly treated as page furniture.

Footnote linking itself is out of scope for this pass. Only verify that the note-call marker and note text were observed correctly enough for a later deterministic linker, post lexical repair.

If the pixels do not clearly establish a repair, report the issue but set proposed to null and confidence to "uncertain".

Complete:
- review/findings.json — every finding must use the entry template currently present in the file. In the "observed" line, only add the content in question verbatim. Do not add commentary that isn't there—use "evidence" for this. That will allow easy visual comparison of "observed" and "proposed". 
Bad:
  "observed": "\u0027affiliated places\u0027 is transcribed as \u0027afficiated places\u0027.",
  "proposed": "affiliated places",
Good:
  "observed": "afficiated places",
  "proposed": "affiliated places",

Never set the review status yourself.

Preserve the raw Paddle artifacts unchanged.

# 2

Execute the human-reviewed repairs in review/findings.json.

This is an EXECUTION pass, not another audit.

Treat the review object as human authority.

Status legend:
- review.status == "approved" → apply proposed;
- review.status == "replace" → apply review.replacement.
- review.status == null → carryover into post repair report.

Do not apply findings with status pending, rejected, or any other value.

Do not discover, propose, or perform any new repairs during this pass.

Never modify:
- source scans;
- raw Paddle _res.json;
- raw Paddle .md;
- the human review decisions.

Write repaired page Markdown to a separate derived directory, preserving one output file per input page and the original page ordering.

Copy unchanged pages into that derived directory unchanged.

For every executed repair, write an execution record containing:
- finding ID;
- page;
- original text;
- final replacement;
- whether the replacement came from proposed or review.replacement.

Fail rather than guess if an approved finding cannot be located unambiguously in its stated page.

Do not perform footnote linking or book concatenation. Those are later deterministic stages.

# AGENTS.md

## Purpose

This repository contains scanned-book OCR artifacts and reviewed repairs.

The goal is faithful transcription and structure preservation, not editorial improvement.

## Source of truth

Authority order:

1. source scan pixels
2. human review decisions
3. raw PaddleOCR JSON / Markdown as machine observations
4. derived repaired Markdown

Raw source scans and raw PaddleOCR artifacts must never be modified.

## Audit pass

When auditing:

- compare each Paddle page against its corresponding source scan;
- report only concrete defects supported by the pixels;
- do not edit files except the designated review report files;
- do not modernize spelling, punctuation, wording, or style;
- do not infer missing text from context alone;
- if evidence is unclear, mark the finding uncertain.

## Repair pass

When repairing:

- apply only findings explicitly approved by the human reviewer;
- do not discover or perform additional repairs;
- use the approved replacement exactly;
- if an approved repair cannot be applied unambiguously, stop and report it;
- write repaired Markdown to the designated derived-output directory;
- never modify source scans, raw Paddle JSON, raw Paddle Markdown, or review decisions.

## Verification

Every repair must correspond to an approved finding.

No approved finding = no permitted content change.

Any unrelated diff is a failure.

## Scope

Footnote linking and whole-book concatenation are separate deterministic stages unless explicitly requested.

# findings.json template

```
[
  {
    "id": "",
    "page": "",
    "category": "",
    "source_image": "",
    "paddle_json": "",
    "paddle_markdown": "",
    "observed": "",
    "proposed": "", 
    "evidence": "",
    "confidence": "",
    "review": {
      "status": "",
      "replacement": "", 
      "note": ""
    }
  }
]
```

# Codex task: Find objections to deterministic whitespace proposals

You are reviewing an OCR-derived digital reconstruction against scans of the physical source. **Your job is to find and report changes that do not belong.** Do not affirm or rewrite individual correct-looking proposals.

## Inputs

- `whitespace_batch.json`: the ONLY findings report for this task. It contains exclusively punctuation/period-adjacency candidates selected from a separate full probe report. **Do not read or request the full probe report or other defect categories.**
- Source page images, accessible via each entry's `source_image` (resolve relative paths using the project's source-image root).
- Original page Markdown, if useful for **locating** the exact occurrence using `paddle_markdown` and UTF-8 `start_byte`/`end_byte` offsets. The image, never the Markdown, remains the transcription authority.

The proposed change for each entry inserts ASCII spaces without changing existing characters. Some insertions may be inappropriate (for example, abbreviations, initials, or typography matching the physical source). Look for these and for any cases you cannot verify visually.

## Review procedure

Work through the batch in manageable page groups rather than loading thousands of findings into one prompt, using the image associated with each page. For every proposal, compare `observed` and `proposed` to the physical printing in the relevant area. Focus on **disproving** the proposed insertion, not on justifying it. Record an exception if the proposal conflicts with the image or if the image is unreadable, missing, or insufficient to establish the placement of the space.

A page belongs in `checked_pages` only after you have actually inspected the source image and reviewed *all* whitespace findings for that page. Do not mark unfinished pages as checked. If you cannot inspect a page, leave it unchecked and list at least one affected finding as an exception explaining why that page could not be inspected; the human must be told which pages remain unchecked. An empty exception list is acceptable only after thorough review of the pages you declare checked.

## Output

Write a **separate** `whitespace_exceptions.json` file:

```json
{
  "checked_pages": ["<actual page id>"],
  "exceptions": [
    {"id": "<exact finding id>", "reason": "<evidence from scan or uncertainty>"}
  ]
}
```

Include only exceptions; never enumerate approvals. Use exact page and finding IDs from the whitespace batch. Do not edit the batch, original scanner report, source images, Paddle artifacts, review statuses, or Markdown. Do not perform repairs. The human will decide whether to batch-authorize all uncontested proposals.
