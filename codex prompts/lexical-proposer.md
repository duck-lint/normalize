# Parallel lexical proposition — original scan pixels are authoritative

## Parent configuration (fill before running)

```yaml
target_book: "{{BOOK_NAME}}"
# Inclusive 1-based positions in the full source-image sequence, NOT printed page numbers:
batches:
  agent1: "{{RANGE_1}}"
  agent2: "{{RANGE_2}}"
  agent3: "{{RANGE_3}}"
  agent4: "{{RANGE_4}}"
```

Example for 181 source scans: `1-45`, `46-91`, `92-137`, `138-181`.
Replace placeholders; remove unused agents. These are example ranges, not
defaults. Run all proposer workers, then a **separate fresh Codex
session** for verifiers. **Do not run the joiner until both sets of workers
have finished.**

## Parent agent — dispatch only

Read the local `AGENTS.md`. Work in the scan-only book review workspace.
Inputs: the selected book's original source scans, untouched
`lexical.json` from Probe 2, and optionally the **read-only**
deterministic segmentation-hints sidecar. No raw Paddle JSON/Markdown, full
Probe 2, executor, or writable lexicon should be accessible to reviewers.
Verify actual paths instead of assuming a book title or layout; do not consult
other OCR artifacts.

Resolve source pages by the **actual source-image sequence** (including
zero-finding pages), never printed page numbers or array positions in the
findings report. If image ordering is ambiguous, stop and ask for an explicit
ordering. Confirm configured ranges cover that sequence exactly, without
gaps or overlaps. Resolve each range to explicit relative source-image paths,
reject paths escaping the scan root, and keep findings associated with each
image together. Refuse findings with missing/ambiguous images.

Prepare one immutable partial batch input per nonempty range. Preserve the
full `format`, `inputs`, and **complete global `vocabulary` inventory**
from the extracted report, and select only that range's findings in original
order, without changing any field. Use separate paths, for example:

- `lexical_batches/proposals/inputs/agent1.json`
- `lexical_batches/proposals/outputs/agent1.json`

Keep only completed `agent*.json` files in the outputs directory; the joiner
reads every JSON there. Do not rewrite the canonical extracted report.
If a configured range has no lexical findings, record that explicitly and do
not dispatch an empty batch.

Spawn one identical subagent per nonempty batch concurrently, up to CLI
limits. Supply each worker the contract below, the selected original scans,
the immutable batch input, its exclusive output, and the optional read-only
hints. The parent does not make or edit proposals. Collect worker results,
report completed/failed batches, and stop. **Do not run the joiner, verifier,
lexicon reviewer, or executor.** Preserve existing repository changes; do
not stage, commit, reset or overwrite inputs.

## Worker contract — include with every delegated assignment

Your only job is to propose *per-occurrence* lexical corrections supported
by the original source pixels. Read `AGENTS.md`. Inspect only your assigned
batch, assigned original scans and optional segmentation hints. OCR context,
recognized-word frequency, segmentation suggestions and dictionaries are
locating/hypothesis aids, **not** evidence of what is printed.

**Mandatory image-access gate:** establish that you can open and visually
inspect the required actual source images. If you cannot view pixels, an image
is missing/unreadable, or image access fails during work, **stop immediately**
and report the failure. Publish **no completed batch output**. A filename,
directory listing, OCR excerpt, or successful file read does not count.

For **each** finding, confirm its recorded UTF-8 context/byte relationship
locates the corresponding occurrence (offsets are Markdown bytes, not image
coordinates), then inspect that exact printed occurrence. When printed
evidence supports a different transcription, set:

- `proposed`: the *complete* scan-faithful replacement for `observed`
- `proposal_source`: `"codex_scan_proposal"`
- `evidence`: concise direct visual evidence, including location

`proposal_note` may add an explanation and `lexicon_suggestion` may suggest
human vocabulary consideration. No agent may admit words to the shared lexicon.
If print agrees with `observed`, leave `proposed` null and write a nonempty
`proposal_note` beginning `SCAN_VERIFIED:` explaining the inspected
occurrence; this does **not** certify that the form is a general dictionary
word. For an ambiguous/non-localizable occurrence, leave `proposed` null
and give a nonempty `SCAN_UNRESOLVED:` or `SCAN_BLOCKED:` note with
the concrete obstacle. These notes distinguish reviewed no-repair decisions
from untouched findings.

Do not guess, modernize spelling, translate, or silently clean typography.
Treat Greek/Latin lookalikes, foreign text, historical forms, names and
unusual printed spellings conservatively. Never adopt segmentation hints
without examining the exact source pixels. Every finding is indivisible.

Write **one complete partial batch output** retaining precisely the incoming
`format`, `inputs`, global `vocabulary`, findings and their order. You may
change **only** `proposed`, `proposal_source`, `evidence`,
`proposal_note`, and `lexicon_suggestion`. Leave all
`review.status` / `review.note` null. Do not add fields, touch other
agents' artifacts, overwrite any input, run OCR, repairs, joiners, tests,
or modify repository history. If unable to finish, publish no completed output
and accurately report what remains.

## Handoff to verification — no join yet

Keep each completed proposer output immutable. In a **fresh verifier Codex
session**, assign the same source-image ranges and use the completed proposer
batch files as read-only verifier inputs. The verifier workers must see only
their assigned proposed findings and actual source scans, not the proposers'
conversations, earlier OCR, or other workers' outputs. This preserves
independent judgment about the propositions without requiring an intermediate
merged report.

After all verifier outputs exist, **the human runs `join_lexical.py` once**,
providing both output directories; see the verifier prompt for the command.
That one invocation creates the complete `lexical-proposals.json` and
`lexical-reviewed.json` expected by the unchanged lexical executor.
