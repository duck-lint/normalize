# Codex task: parallel whitespace verification against source scans

## Run configuration — fill in before dispatch

```yaml
target_book: "{{BOOK_NAME}}"
# 1-based, inclusive positions in the selected book's SOURCE SCAN sequence.
batches:
  agent1: "{{RANGE_1}}"
  agent2: "{{RANGE_2}}"
  agent3: "{{RANGE_3}}"
  agent4: "{{RANGE_4}}"
```

For example, a book with 200 source scans might use `1-50`, `51-100`,
`101-150`, and `151-200`. These are examples, **not** configured defaults.
Replace all placeholders before dispatch. Remove unused agents rather than
assigning empty ranges. No pipeline transitions are delegated: the human
invokes the joiner, reviews its output, and separately runs the executor.

## Parent: assign and dispatch, do not review

Read the review workspace's `AGENTS.md`. The workspace contains the selected
book's original source scans and **untouched extracted** whitespace report;
raw Paddle JSON/Markdown and Probe 1 must not be available to reviewers.
Typical paths are `books/<book>/imgs/source/` and
`whitespace_reports/<book>/whitespace.json`, but establish actual paths.

The page positions above refer to the original scan sequence, **not**
printed page numbers or finding indices. Establish the sequence from actual
source-image filenames/ordering. If ordering is ambiguous (such as inconsistent,
un-padded numbering), stop and request an explicit sequence rather than guess.
Resolve each inclusive range to an explicit list of relative `source_image`
paths and pass that list to its worker. Pages with zero whitespace findings
still count when assigning scan positions.

Verify the book, report, available scans and configured ranges. Ranges must
be nonoverlapping and cover the whole source-image sequence. Do not silently
adjust ranges, guess paths, or assign unconfigured work. Resolve image paths
beneath the selected scans root, rejecting path traversal or ambiguity.

Create a separate batch input report for each assignment: keep the original
`inputs` and only the findings whose `source_image` belongs to that agent.
Preserve original order and values. Do not modify canonical `whitespace.json`.
Keep inputs and outputs in separate folders:

- `whitespace_reports/<book>/batches/inputs/agent1.json`
- `whitespace_reports/<book>/batches/outputs/agent1.json`

Apply the same pattern for the configured agents. An agent with zero assigned
findings has no output; record that fact. Each nonempty agent output must
contain **all** its assigned findings, not just approvals. Only the completed
JSON outputs belong in the outputs directory; the joiner reads that directory.

Spawn one identical Codex subagent per nonempty batch, concurrently up to the
CLI's configured limit. Give each worker the **Worker review contract** below,
its image list, immutable batch input path, and exclusive output path.
The parent does no visual reviews, does not edit agent decisions, and never
runs the joiner or executor. Wait for all children and accurately report
their outcomes and paths. A parent summary is not evidence of completed
visual inspection or report integrity.

## Worker review contract — provide to every subagent

You are a scan-based verifier, not a text editor or an OCR repair agent.
Read the workspace's `AGENTS.md`. Access only your assigned batch and its
original source scans. Do not consult raw Paddle artifacts, full Probe 1,
historical OCR reports, or other agents' outputs. Do not stage, commit, reset,
or modify source scans, upstream reports, scripts, or shared vocabulary.

**Hard prerequisite: open and visually inspect the actual source scan images.**
Establish that your image-viewing capability works and that all required
source images are accessible. If source pixels cannot be viewed, a required
image is unavailable, or access is lost during review, **stop immediately**.
Report the failure to the parent, and publish no completed batch output.
File listings, filesystem reads, filenames and OCR excerpts are not visual
verification.

For each assigned finding:

1. Check internal consistency of the fixed proposal and the byte/context
   relationship. Coordinates refer to original Markdown UTF-8 bytes, **not**
   image pixels. OCR context locates text but is not evidence of correctness.
2. Locate the exact printed occurrence in its source image. If repeated
   instances cannot be distinguished, do not approve.
3. Inspect **every** proposed punctuation-space insertion. Only approve the
   indivisible finding if every insertion is unambiguously printed. Remember
   abbreviations (`U.S.A`), initials, citations, numbers and unusual typography.
4. Record `review.status: "approved"` only with direct visual evidence.
   Otherwise leave status `null` and write a nonempty `review.note` beginning
   with `SCAN_REJECTED:`, `SCAN_UNRESOLVED:`, or `SCAN_BLOCKED:`.
   A visible contradiction, inconclusive inspected print, and a finding
   that cannot be located/validated are different outcomes.
5. Never infer, modernize, rewrite, partially approve, or execute a repair.
   Plausibility, grammatical expectations or lack of contradiction do not
   establish that a proposed insertion matches the print.

Write a **new full batch report**, retaining precisely the incoming top-level
`inputs` and `findings`, in assigned order. Only `review.status` and
`review.note` may change. Preserve all IDs, paths, hashes, spans, context,
proposals, and other fields. Status may only be `null` or `"approved"`.
Every unapproved finding in a completed output requires an explicit outcome
note. Never overwrite an input, the canonical report or another worker's
output. Do not create or maintain exceptions reports.

If interrupted or unable to finish, report the incomplete scope and **do not
publish a completed batch output**. Do not run OCR, the probe, extractor,
joiner, executor, or project tests. Human acceptance remains separate.

## Human handoff

The joiner reconstructs the complete report from Probe 1 and imports only
review fields from exact-once completed batch outputs. It emits the informational
exceptions report. Its structural checks **cannot prove image inspection**.

From the tooling checkout, after all agents complete (paths illustrative):

```bash
python /path/to/normalize/join_whitespace.py \
  --baseline review/probe1.json \
  --report review/whitespace.json \
  --batches 'whitespace_reports/<book>/batches/outputs' \
  --out review/whitespace-reviewed.json \
  --exceptions-out review/whitespace_exceptions.json
```

Review the joined report, then run the existing `execute_repairs.py` with
`--baseline review/probe1.json --report review/whitespace-reviewed.json`
for its normal dry run and human-authorized execution. Never replace the
untouched extracted whitespace report with worker output.
