# Codex task: verify punctuation-space proposals against source scans

## Task configuration

Target book: '{{BOOK_NAME}}'

## Objective

Review existing deterministic punctuation-space proposals against their exact
printed occurrences in the source scans.

Your task is to evaluate supplied proposals, not discover or perform repairs.

Approve only complete proposals supported by direct visual evidence. Withhold
approval when the printing contradicts the proposal, the occurrence cannot be
identified, or the evidence is insufficient.

Preserve the report's existing schema, proposal values, and execution
coordinates.

Preserve `inputs.json_markdown_comparison` unchanged. This whitespace review
uses a raw-Paddle probe (`mode: "raw"`). Do not add or edit suppression fields.
The executor records applied changes; the later probe independently verifies
them before recording JSON/Markdown comparison exceptions. The non-approved
review exceptions report you create is a different artifact and grants no
comparison authority. See [the process document](../docs/process.md).

Work in manageable source-page groups. Preserve completed decisions and report
partial progress accurately.

## 1. Authority and epistemic boundaries

Read and obey the repository's `AGENTS.md`.

The governing distinction is between observation, proposal, verification,
and authorization.

| Material | What it establishes |
| --- | --- |
| Source scan pixels | Primary evidence of the printed text and spacing. |
| Raw PaddleOCR Markdown/JSON | Fallible machine observations. |
| Full probe report | Mechanical detection results, not verified repairs. |
| Extracted whitespace report | The fixed population of proposals for this review. |
| `ocr_context` | Locating information copied from OCR, not independent evidence. |
| Visual inspection | Whether the exact printed occurrence supports the proposal. |
| `review.status` | An executable review decision consumed by the repair executor. |
| Human review | Final authority to accept the review and authorize execution. |

Maintain these distinctions:

1. Detection identifies a pattern in OCR output.
2. Localization identifies the corresponding printed occurrence.
3. Verification determines whether that occurrence supports the proposed space.
4. Approval records the finding as eligible for subsequent execution.
5. Human authorization governs whether the reviewed report is used for repairs.

Success at one stage does not establish success at the next.

In particular:

- A deterministic proposal is not necessarily correct.
- Valid byte offsets do not establish transcription accuracy.
- A matching OCR excerpt is not independent source confirmation.
- A plausible grammatical correction is not necessarily faithful transcription.
- Failure to observe a contradiction does not establish correctness.
- A missing or unreadable image does not establish that a space belongs.
- Confidence in the proposal cannot substitute for evidence from the scan.

Approval applies only to the specific proposed spacing transformation. It does
not certify the surrounding OCR, punctuation, spelling, or layout.

Codex's review does not itself constitute human confirmation. The human must
review and accept the resulting decisions before invoking the executor.

Do not run the executor.

## 2. Discover the target book and available inputs

The current working directory is the review repository root.

Do not assume a particular book title, filename prefix, or page count. Use the target book specified in Task configuration.

If the target book is missing or ambiguous, stop and request clarification.
Do not automatically select a book.

The repository convention is:

| Path | Role |
| --- | --- |
| `AGENTS.md` | Repository-wide instructions and authority boundaries. |
| `books/<book>/imgs/source/` | Original source scan images. |
| `whitespace_reports/<book>/whitespace.json` | Extracted whitespace report to review. |
| `whitespace_reports/<book>/whitespace_exceptions.json` | Complete non-approved findings report. |

`<book>` represents the actual book directory, not a literal string.

For the target book, verify that:

- The whitespace report exists and is readable.
- The matching source scan directory exists.
- The scan files referenced by the report are available.
- The report and scan directory correspond to the same selected book.

Resolve each finding's `source_image` relative to the selected scans root,
preserving any relative subdirectories.

Do not select scans using printed page numbers.

Do not permit `source_image` paths to escape the selected scans root.

The repository may contain a saved directory inventory or tree document.
Such an inventory may assist path discovery but is not evidence that the listed
scan files are currently available or visually correct.

If the actual directory conventions differ, use the repository's local
structure and report metadata to identify the corresponding paths.

Accept an alternate layout only when the intended report and scan directory
can be established unambiguously.

If the correspondence remains ambiguous, stop and request clarification.
Do not guess.

Paths named `paddle_markdown` and `paddle_json` in the report are provenance
and executor addresses. Their targets need not be present for this review.

The complete probe report and execution scripts may be present in the
repository. Their presence does not expand this task.

If present, do not inspect or retrieve the full probe report, raw Paddle artifacts,
or alternate historical copies to supplement the extracted report.

## 3. Establish the initial repository state

Before editing:

1. Read `AGENTS.md`.
2. Identify the selected book and its actual report and scan paths.
3. Run `git status --short`.
4. Identify any pre-existing modifications to the designated reports.
5. Load the whitespace report as JSON.
6. Preserve a complete, unedited snapshot of the loaded report in memory
   or temporary storage outside the repository.

Do not reset, discard, stage, or commit changes.

Existing repository changes must not be attributed to this invocation.

A malformed or missing report is an input failure. Stop rather than
regenerating it or changing its schema.

## 4. Understand the deterministic proposal contract

The probe identifies two punctuation adjacency categories:

- `punctuation_letter`: one of `,;:!?` immediately followed by an ASCII letter.
- `period_capital`: a period immediately followed by an ASCII capital letter.

It proposes inserting ASCII spaces without otherwise changing characters.

Examples:

`observed: ",word"`
`proposed: ", word"`

`observed: ".Next"`
`proposed: ". Next"`

Touching or overlapping punctuation detections may form one finding with
multiple insertions.

Qualifying findings contain:

- Nonempty `triggers` using only the two permitted categories.
- Non-null `proposed`.
- `proposal_source: "deterministic_whitespace"`.
- An exact `observed` span.
- Original UTF-8 byte offsets and hashes.
- OCR context.
- A `review` object containing `status` and `note`.

The extractor copies these findings without generating or modifying proposals.

The extracted report is the fixed review population.

Do not:

- Add or remove findings.
- Generate new proposals.
- Rewrite `observed` or `proposed`.
- Change offsets or hashes.
- Change trigger categories.
- Merge or split findings.
- Generate alternative replacements.
- Normalize unrelated whitespace or punctuation.

An individual finding is indivisible. Approve the entire proposal or leave
the entire proposal unapproved.

### Validate the proposal

Confirm each finding's `proposed` value matches the deterministic
transformation applied to `observed`:

```python
import re

expected = re.sub(
    r"([,;:!?])(?=[A-Za-z])",
    r"\1 ",
    finding["observed"],
)

expected = re.sub(
    r"\.(?=[A-Z])",
    ". ",
    expected,
)

assert expected != finding["observed"]
assert finding["proposed"] == expected
```

This establishes mechanical validity only.

It does not establish that the space belongs in the printing.

Do not run the probe or normalization scripts.

## 5. Validate the report structure and context

The extracted report must have the existing top-level structure:

```json
{
  "inputs": {},
  "findings": []
}
```

Verify:

- `findings` is a list.
- Finding IDs are unique.
- Required proposal, source, and review fields exist.
- Triggers contain only permitted categories.
- `proposal_source` matches the expected value.
- `review.status` is null or `"approved"`.
- `review.note` is null or a string.
- The original finding order is preserved.

Unsupported trigger/status categories, duplicate IDs, or malformed top-level
structure are report-level input failures.

Stop and report them without rewriting the input.

Individual findings with inconsistent byte coordinates, context, or proposals
must remain unapproved and be documented as blocked.

If an invalid finding is already approved, stop and report the existing
approval conflict.

### Byte coordinates

Each finding's `start_byte` and `end_byte` identify the `observed` span in
the original UTF-8 Paddle Markdown.

They are zero-based, start-inclusive, and end-exclusive.

They are Markdown byte coordinates, not image coordinates.

Each `ocr_context` supplies:

- `provenance: "raw_paddle_markdown"`
- `start_byte`
- `end_byte`
- `text`

The context is an unchanged excerpt from the same raw OCR Markdown as
`observed`, including original newlines and Markdown syntax.

Validate the relationship:

```python
context = finding["ocr_context"]
context_bytes = context["text"].encode("utf-8")

relative_start = (
    finding["start_byte"] - context["start_byte"]
)
relative_end = (
    finding["end_byte"] - context["start_byte"]
)

assert context["provenance"] == "raw_paddle_markdown"

assert (
    len(context_bytes)
    == context["end_byte"] - context["start_byte"]
)

assert 0 <= relative_start < relative_end <= len(context_bytes)

assert (
    context_bytes[relative_start:relative_end]
    == finding["observed"].encode("utf-8")
)
```

These checks establish internal consistency.

They do not independently verify the complete original Markdown or the
accuracy of its transcription.

The human-run executor later validates the raw artifacts, source hashes,
and approved execution coordinates.

Do not reconstruct or modify those artifacts here.

## 6. Review each exact printed occurrence

Group findings by source scan and work through manageable page batches.

Review all eligible findings for a selected source page together whenever
possible.

Do not impose an arbitrary book-wide page limit.

If the task specifies a page range or batch size, respect it.

Otherwise, process a manageable amount of evidence, save verified decisions,
and continue when practical.

If the invocation cannot complete the entire book, leave the remaining
findings unchanged and report the stopping point.

### Step A — Validate the finding

Before visual inspection, confirm:

- The proposal is mechanically valid.
- Context and byte coordinates are internally consistent.
- The source image resolves to an available file.
- No incompatible review state prevents processing.

Invalid findings are not eligible for approval.

Record the specific obstacle without modifying upstream data.

### Step B — Locate the occurrence

Open the actual source image using an available image-viewing capability.

Reading the OCR context or a directory listing is not visual inspection.

Use the supplied `ocr_context` to identify the corresponding printed passage.

Locate the exact occurrence, not merely a similar or repeated phrase.

OCR context may contain:

- Recognition errors.
- Missing or extra characters.
- Incorrect punctuation.
- Markdown syntax.
- Reading-order differences.
- Line or paragraph boundary differences.

Treat these as potential localization complications.

If multiple printed occurrences remain plausible and cannot be distinguished,
leave the finding unapproved.

If the apparent finding originates from OCR markup or an image path and has
no corresponding printed text, do not invent a printed occurrence.

### Step C — Inspect the proposal

Inspect every insertion within the complete proposed span.

Determine whether the exact printed occurrence supports each insertion.

Pay particular attention to:

- Abbreviations.
- Initials and acronyms.
- Numerical or symbolic notation.
- Quotations and citations.
- Deliberate punctuation adjacency.
- Unusual typography.
- Line or paragraph transitions.
- Damaged or unreadable printing.
- OCR errors affecting the relevant punctuation.

For example:

`observed: ".S.A"`
`proposed: ". S. A"`

This may occur inside `U.S.A`.

If the source prints `U.S.A` without those spaces, the complete proposal
must remain unapproved.

Do not approve merely because the proposed result resembles conventional
modern punctuation.

Do not reject merely because another OCR error exists nearby, provided the
exact occurrence is established and the spacing evidence is independently
clear.

Do not repair any unrelated OCR error.

### Step D — Decide the complete finding

Approval requires all of the following:

1. The supplied finding is structurally valid.
2. Its exact printed occurrence was located unambiguously.
3. Every proposed insertion is supported by the source.
4. No part of the complete proposal contradicts the printing.

If any condition is unmet, withhold approval.

Do not approve only part of a finding.

Do not substitute a new proposal.

Do not treat contextual plausibility as a replacement for source evidence.

If image viewing is unavailable, leave affected findings unapproved and
report that limitation.

## 7. Record review decisions

Only these fields may change:

- `review.status`
- `review.note`

Use the existing status values only:

- `"approved"` — the complete proposal is supported by visual inspection.
- `null` — the proposal is not authorized for execution.

Do not introduce new status values.

### Approved

For a visually confirmed complete proposal:

```json
{
  "status": "approved",
  "note": null
}
```

A note may contain a concise observation when useful, but an approval note
is not required.

Preserve any pre-existing note.

Never claim visual confirmation without actually inspecting the exact scan.

### Rejected

When inspection reveals a concrete contradiction:

- Leave `status` as null.
- Record a concise objection in `review.note`.

Use:

`SCAN_REJECTED: <specific visible contradiction>`

For example:

`SCAN_REJECTED: Printed abbreviation contains no spaces after the periods.`

A rejection is a finding about the printing, not a judgment based solely
on grammatical expectations.

### Unresolved

When the scan has been inspected but the evidence remains insufficient:

- Leave `status` as null.
- Record the specific uncertainty.

Use:

`SCAN_UNRESOLVED: <specific uncertainty>`

Do not treat uncertainty as rejection or approval.

### Blocked

When inspection cannot proceed because of missing scans, inconsistent context,
invalid proposals, or another concrete obstacle:

- Leave `status` as null.
- Record the obstacle.

Use:

`SCAN_BLOCKED: <specific obstacle>`

Do not invent missing evidence or modify source data to resolve the blockage.

### Unreviewed

Findings not reached by this or any previous review retain their incoming
state.

For a fresh finding, that is:

```json
{
  "status": null,
  "note": null
}
```

Do not assign a review outcome merely to make the batch appear complete.

### Resuming an existing review

Preserve prior decisions.

- Do not automatically reapprove previously approved findings.
- Do not overwrite existing notes.
- Do not silently reverse completed rejections.
- Do not treat a nonempty note as proof of visual inspection unless it clearly
  documents an inspection outcome.
- Revisit unresolved or blocked cases when the human requests reconsideration
  or the missing evidence becomes available.

By default, continue with findings not yet reviewed, respecting any
explicit page-range instructions.

The edited report is the durable review state.

Do not create another progress-tracking file or database.

If an existing `"approved"` decision visibly conflicts with the source,
stop and report the conflict.

Do not leave a known conflicting approval unreported.

Do not revoke that approval without human direction.

## 8. Strict write boundary

You may write only the two designated reports for the selected book:

1. `whitespace_reports/<book>/whitespace.json`
2. `whitespace_reports/<book>/whitespace_exceptions.json`

Use the actual resolved report paths if the repository's convention differs.

Edit the whitespace report in place.

Preserve every field outside `review.status` and `review.note`.

In particular, preserve:

- Top-level `inputs`.
- Finding count and ordering.
- IDs and page identifiers.
- Source-image and Paddle paths.
- Rules and triggers.
- Hashes.
- Finding byte spans.
- Context byte spans.
- `ocr_context` and its exact text.
- `observed`.
- `proposed`.
- `proposal_source`.
- `evidence`.
- Every other pre-existing field and value.

JSON formatting may change as a consequence of serialization, but all
unauthorized values must remain identical.

Do not modify:

- Source scans.
- Raw Paddle artifacts.
- Full probe reports.
- Normalization or execution scripts.
- Repository instructions.
- Directory inventories.
- Other book reports.
- Any other repository files.

Do not generate supporting scripts inside the repository.

Temporary verification state must remain outside it.

Read-only local tooling for JSON inspection and integrity comparison is
permitted.

Do not run OCR, the probe, extractor, executor, or project tests.

Do not stage, commit, reset, or rewrite Git history.

Git is an independent audit mechanism for detecting changes, not evidence
that the proposed repair is correct.

## 9. Generate the exceptions report

Write the selected book's exceptions report with this exact structure:

```json
{
  "findings": []
}
```

Populate `findings` with complete copies of all final non-approved findings
from the edited whitespace report.

Preserve their original order.

Include:

- Rejected findings.
- Unresolved findings.
- Blocked findings.
- Unreviewed findings.

Every exception must preserve the complete final finding object, including
its note, context, proposal, offsets, metadata, and evidence.

Do not replace complete entries with ID/reason summaries.

Do not omit findings outside the current page batch.

Generate the exceptions report from the final whitespace report state.

Do not incrementally maintain a separate exception history.

An empty exceptions list is valid only if the original report contains no
findings or every finding is approved.

The exceptions report is informational.

It is not an independent source of permission to execute repairs.

## 10. Verify the saved reports

After writing, parse both JSON reports again.

Compare the edited whitespace report with the initial unedited snapshot from
this invocation.

Verify:

1. The total finding count is unchanged.
2. Finding IDs and order are unchanged.
3. Every field outside `review.status` and `review.note` is identical.
4. All review statuses use permitted values.
5. The exceptions report equals the ordered complete subset whose final
   status is not `"approved"`.
6. No findings are duplicated or omitted.
7. Approved plus non-approved counts equal the original finding count.
8. Every newly approved finding was visually inspected.
9. Completed rejections and unresolved cases have explanatory notes.
10. Unreviewed findings were not converted to approvals.
11. Only the two designated repository reports were written.

Inspect `git status --short` and the relevant diffs.

Account for pre-existing changes separately.

If validation fails, correct only the authorized report edits.

If correction would require changing upstream artifacts, stop and report
the failure.

Do not conceal validation failures or alter baseline data to make
verification pass.

## 11. Report progress and completion

At the end of the invocation, report:

- Selected book.
- Actual scans root.
- Actual whitespace report path.
- Actual exceptions report path.
- Total findings.
- Source pages inspected in this invocation.
- Findings inspected in this invocation.
- Newly approved findings.
- Final approved count.
- Rejected count.
- Unresolved and blocked counts.
- Remaining unreviewed findings and pages.
- Any existing approval conflicts or input problems.
- Whether report integrity verification passed.
- Whether the two-file write boundary was preserved.

Distinguish:

**Batch complete:** all eligible findings in the selected batch were processed,
and the resulting reports passed verification.

**Review coverage complete:** every finding has been inspected or explicitly
documented as unresolved or blocked; no unreviewed findings remain.

**All proposals approved:** every finding has status `"approved"`.

These are different outcomes.

A completed review may contain rejected or unresolved findings.

A completed batch does not imply the entire book was reviewed.

Never report incomplete inspection as complete.

Do not claim to have inspected findings carried forward from previous runs
unless you actually inspected them during this invocation.

The human must examine and accept the review decisions before executing
approved repairs.

## 12. Non-negotiable constraints

This task verifies existing proposed transformations.

It does not perform transcription, normalization, editorial correction,
or free-form OCR repair.

Do not:

- Discover new repairs.
- Rewrite proposed replacements.
- Repair unrelated text.
- Modernize spelling or punctuation.
- Infer missing spaces from grammatical expectations.
- Use OCR context as independent confirmation.
- Substitute mechanical consistency for source fidelity.
- Modify upstream artifacts to make proposals easier to approve.
- Authorize ambiguous findings.
- Execute approved repairs.
- Represent incomplete work as complete.

The governing rule is:

**A finding is eligible for approval only when its entire unchanged proposal
is supported by the exact printed occurrence. Where that evidentiary
relationship cannot be established, authorization must be withheld.**

The human subsequently reviews the decisions and runs the existing executor
against the original artifacts and untouched probe baseline.

Your work ends with the two verified review reports.
