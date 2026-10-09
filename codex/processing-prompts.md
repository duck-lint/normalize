# Codex task: review proposed punctuation spaces in a book workspace

Run this task in the workspace repository containing the book scans, raw Paddle
artifacts, and reports. This is not a task to edit the Normalize tooling repository.

Inputs (replace these paths with the actual book-workspace paths):

- `review/whitespace.json`: report two, copied by the extractor from the probe.
- Source page scans, using each finding's `source_image` path relative to the
  source-image root. For paths such as `scans/page001.jpg`, that root is
  the book workspace; for paths without a `scans/` prefix, it is the scans directory.
- Raw Paddle Markdown, using `paddle_markdown` relative to the extracted Paddle
  root, if needed to locate the passage. Choose the root in the same way as
  for scan paths, without adding a duplicate directory prefix. `start_byte` and `end_byte` are
  offsets in the original UTF-8 Markdown bytes, not character indices.

Review every finding in report two against its corresponding source scan. Look
for proposed spaces that do not belong, including abbreviations such as `U.S.A`,
initials, and punctuation that is correctly adjacent in the printing. The probe's
proposal is a candidate, not evidence that the source contains a space. If the
scan is missing, unreadable, or ambiguous, do not approve the finding.

Work in manageable page groups so every proposal is reviewed. Do not load the
whole book into one context window or infer approvals from absence of objections.

Edit `review/whitespace.json` in place:

- For each accepted proposal, set `review.status` to exactly `"approved"`.
- For a proposal that does not belong, or cannot be verified, leave its status
  unchanged and optionally explain the objection in `review.note`.
- Edit only `review.status` and `review.note`. Preserve all findings, their order,
  and every other value, including IDs, triggers, observed/proposed text, offsets,
  paths, hashes, and report metadata. Do not revise proposals or add alternatives.

Write report three to `review/whitespace_exceptions.json`:

```json
{
  "findings": []
}
```

Populate `findings` with complete copies of every non-approved finding from the
edited report two, including any note you added. Include exceptions and uncertain
cases only; use an empty list if all proposals were reviewed and accepted. Do not
invent a separate exception schema or summarize away finding fields.

Do not read the full probe report for this task. Do not edit scans, raw Paddle
artifacts, Markdown, scripts, or prompts. Do not execute repairs. The human runs
`execute_repairs.py` afterward over the edited report two. Report three records
exceptions; it never authorizes execution.

If you cannot finish, leave unreviewed statuses unchanged, include those findings
in report three, and state which pages or findings remain unreviewed. Never call
an incomplete review complete.
