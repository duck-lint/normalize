# 1

Please audit the complete PaddleOCR output with the corresponding source page scans.

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

Footnote linking itself is out of scope for this pass. Only verify that the note-call marker and note text were observed correctly enough for a later deterministic linker.

If the pixels do not clearly establish a repair, report the issue but set proposed to null and confidence to "uncertain".

Complete:
1. review/findings.json — every finding must use the entry template currently present in the file.
2. review/summary.md — short counts by category and a list of unresolved/high-risk pages.

Never set the review status yourself.

Preserve the raw Paddle artifacts unchanged.

# 2

Execute the human-reviewed repairs in review/findings.json.

This is an EXECUTION pass, not another audit.

Treat the review object as human authority.

Apply a finding only when:
- review.status == "approved" → apply proposed;
- review.status == "replace" → apply review.replacement.
- review.status == null → carryover into new findings report

Do not apply findings with status pending, reject, or any other value.

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