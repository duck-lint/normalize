# Codex task: review proposed punctuation spaces in a book workspace

This task is running in a workspace repository containing a complete book scan, raw Paddle artifacts, and accompanying reports. 

Inputs:

- `repo-root/review/findings.json`: the report that the extractor pulls the content of this task from.
- `repo-root/review/whitespace.json`: the report this task is to be executed on, copied by the extractor from the probe report `findings.json`.
- `repo-root/{{book}}/`: has original Paddle Markdown and json.
- `repo-root/{{book}}/imgs/source/`: has source page scans to be used for resolving ambiguity and proposing a solution in `review/whitespace.json`. 

Review every finding in the `whitespace.json` report against its corresponding source scan. Look for proposed spaces that do not belong, including abbreviations such as `U.S.A`, initials, and punctuation that is correctly adjacent in the printing. The probe's proposal is a candidate, not evidence that the source contains a space. If the
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
