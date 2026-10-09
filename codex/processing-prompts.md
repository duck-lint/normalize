# Codex task: review proposed punctuation spaces against source scans

You are running in a book-review workspace containing source scans and
`review/whitespace.json`. The original Paddle Markdown/JSON and the full probe
report are retained in the separate execution environment, not supplied for this
review. Your task is to identify proposed spaces that do not belong and approve
those that survive inspection of their exact printed occurrence.

## Process context and provenance

| Stage | What it supplies and what that establishes |
| --- | --- |
| PaddleOCR | Produces raw Markdown/JSON from scans. These are fallible machine observations. |
| Probe | Reads original Markdown and generates punctuation-space proposals, exact `observed` spans, original byte offsets/hashes, and bounded `ocr_context` excerpts. It does not establish that a proposed space belongs in the printing. |
| Extractor | Copies complete qualifying findings unchanged into `review/whitespace.json`, including proposals, byte spans, and context. It neither generates proposals nor approves findings. |
| You | Use supplied context to locate each occurrence in the scan, then judge the existing proposal from pixels. Edit only review status/note and copy non-approved entries to the exceptions report. |
| Human-run executor | Uses the untouched full probe report and original Paddle directory to validate the edited report, copy artifacts, and apply approved proposals to copied Markdown. |

The probe matches `punctuation_letter` (`,;:!?` followed immediately by an ASCII
letter) and `period_capital` (a period followed immediately by an ASCII capital).
It inserts ASCII spaces at those adjacencies, changing no existing characters:
`,word` becomes `, word`, and `.Next` becomes `. Next`. Touching/overlapping
punctuation hits can form one finding with several insertions. Findings arrive
with non-null `proposed` and `proposal_source: "deterministic_whitespace"`.
That marker identifies mechanical provenance, not agreement with the scan.

## Establish the available inputs

`repo-root` is the current review repository root. `{{book}}` is its actual book
directory, identifiable from the local inventory and recorded source-image paths.
Use this layout unless the task explicitly supplies another scans/report path:

| Path | Role |
| --- | --- |
| `repo-root/review/whitespace.json` | Input report to review and edit in place. |
| `repo-root/{{book}}/imgs/source/` | Source scans; the transcription authority for this task. |
| `repo-root/review/whitespace_exceptions.json` | Output report containing complete non-approved entries. |

Resolve each `source_image` relative to the scans root, preserving subdirectories.
Do not select images by printed page numbers. If the scans root is ambiguous,
identify the candidate paths and request the missing location before editing.
The `paddle_markdown` and `paddle_json` paths remaining in the report are provenance
and executor addresses; they are not files you need to find for this review.
Do not retrieve raw Paddle artifacts, the full probe report, or other copies from
outside the review workspace or repository history.

Load the whitespace report as JSON. Keep an unedited snapshot in memory or
temporary storage outside the repository for a final integrity comparison. Its
top-level object contains `inputs` and `findings`. Every finding's nonempty
`triggers` list contains only `punctuation_letter` and/or `period_capital`. Fresh
findings have `review.status: null` and `review.note: null`. A missing/malformed
report or other trigger categories are input problems: stop and identify them,
rather than regenerating reports or changing their schema.

## What the byte spans and context mean

Each finding's `start_byte` and `end_byte` address the exact `observed` span in
original UTF-8 Markdown: zero-based, start included, end excluded. They are
execution coordinates, not image coordinates, and cannot identify pixels directly.

`ocr_context` contains:

- `provenance: "raw_paddle_markdown"`: the excerpt is copied from the same raw OCR
  Markdown as `observed`, not transcribed independently from the scan.
- `start_byte` and `end_byte`: the excerpt's absolute range in those original
  Markdown bytes, using the same coordinate system as the finding.
- `text`: the unchanged excerpt, containing the finding plus up to 160 Unicode
  characters before and after it. Original newlines and Markdown syntax survive.

To distinguish the target from nearby/repeated strings, encode `ocr_context.text`
as UTF-8 and locate its target at:

```python
context = finding["ocr_context"]
context_bytes = context["text"].encode("utf-8")
relative_start = finding["start_byte"] - context["start_byte"]
relative_end = finding["end_byte"] - context["start_byte"]
context_bytes[relative_start:relative_end] == finding["observed"].encode("utf-8")
```

Also check that the finding range lies inside the context range and that the
context's encoded length equals `context.end_byte - context.start_byte`. These
checks establish internal consistency of the supplied report. You cannot verify
the full original Markdown hash here; the executor performs that check later.
Neither a consistent excerpt nor its hash/provenance establishes source accuracy.

## Review each complete proposal against its exact source occurrence

Work in manageable source-page groups and inspect the actual scans with your
available image-viewing capability. Reading context or seeing a filename is not
visual inspection. Local read-only tools may load JSON and inspect context bytes;
Normalize scripts and raw Paddle files are not required in this workspace.

For each finding:

1. Check its proposal/provenance and context consistency as described above.
   Missing or inconsistent context, byte spans, or proposals leave the finding
   unapproved. Note the specific problem and carry the complete finding into the
   exceptions report; do not invent context, change offsets, or generate a repair.
2. Open the scan identified by `source_image`. Use the surrounding OCR context
   and the target's position within it to locate the corresponding printed
   passage. Context can contain OCR errors, markup, or reading-order differences;
   it is only a locating hint. If several printed occurrences remain plausible,
   leave the finding unapproved rather than selecting a convenient match.
   Candidates in image paths or Markdown syntax may have no printed counterpart.
3. Inspect every insertion in the entire `proposed` span against that exact
   printed occurrence. Look for abbreviations, initials, notation, deliberate
   adjacency, and other cases where spaces do not belong. Accept only when the
   pixels support the complete proposal. Several insertions in one finding are
   one decision: do not split it, rewrite it, or approve only part.
4. Set accepted findings to exactly `review.status: "approved"`. Otherwise keep
   the incoming status unchanged and optionally add a concise `review.note`
   describing the objection or missing evidence. Preserve an existing note when
   adding your observation. Unavailable/unreadable scans and unresolved occurrence
   mapping do not authorize approval.

For example, `observed: ".S.A"` and `proposed: ". S. A"` can occur inside
`U.S.A`. Use the excerpt to locate the abbreviation, then inspect the scan. If the
printing shows `U.S.A`, leave its status unchanged and report the exception.
Context alone, grammatical plausibility, or absence of an objection without
image inspection never suffices to approve. If image viewing is unavailable,
leave affected findings unchanged and report that limitation. If an incoming
`"approved"` decision conflicts with the scan, stop and flag that existing
conflict: unchanged `"approved"` would still execute, and this task does not
permit revoking an earlier approval.

## Save and verify only the review decisions

Edit `review/whitespace.json` in place, changing only `review.status` and
`review.note` (text or null). Preserve metadata, finding count/order, IDs, paths,
triggers, hashes, both finding and context byte spans, `ocr_context.text`,
`observed`, `proposed`, `evidence`, and every other value. The executor compares
against the untouched baseline and hard-fails on changes outside status/note.

Write `review/whitespace_exceptions.json` with exactly this shape:

```json
{
  "findings": []
}
```

Its list must contain complete copies of all final non-approved findings in
original order, including notes, context, and byte spans. Include objections,
unresolved cases, and unreviewed findings if incomplete. Do not substitute
ID/reason summaries. Use an empty list only when all findings were reviewed and
approved, or the input had none.

Parse both saved reports and verify that the edited input equals the initial
snapshot after disregarding only status/note; that the exceptions report equals
the ordered, complete non-approved subset; and that approved plus non-approved
counts equal the original count. Correct your permitted edits if these checks
fail. Every approval added must follow inspection of its exact source occurrence.

Do not run OCR, the probe, extractor, executor, or project tests. Do not write
scans, Markdown, tooling, or prompts. The two designated review reports are the
only repository files you may write; temporary verification state stays outside
it. Report the actual scans root, both report paths, total findings, approvals
added, final approved/non-approved counts, and any unreviewed or blocked IDs/pages.
Never present a partial review as complete. The human later executes approved
repairs in the separate environment holding the original artifacts and baseline.
