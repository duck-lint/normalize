# Codex task: review proposed punctuation spaces in this book workspace

You are running in a workspace repository containing a complete book scan,
original PaddleOCR artifacts, and accompanying reports. Your task is to identify
punctuation-space proposals that do not belong and approve those that survive
source review. The proposals are already generated before you begin.

## Process context and proposal provenance

| Stage | What it produces and what that establishes |
| --- | --- |
| PaddleOCR | Reads scanned images and produces raw Markdown/JSON. These are fallible machine transcriptions, not the printing itself. |
| Probe | Reads the original Paddle Markdown, identifies pattern candidates, and generates their `proposed` strings in `review/findings.json`. It also records the exact `observed` text, original UTF-8 byte span, source paths, and Markdown hash. |
| Extractor | Selects punctuation-space findings and copies each complete entry unchanged into `review/whitespace.json`. It does not generate or revise proposals, inspect scans, or approve findings. |
| You, in this task | Inspect each candidate's exact printed occurrence and edit only its review decision and optional note. Copy non-approved findings into the exceptions report. |
| Human-run executor | Checks the reviewed report against the untouched probe report, copies the original Paddle directory, and applies only approved proposals to copied Markdown. |

The probe's two punctuation rules are `punctuation_letter` (`,;:!?` immediately
followed by an ASCII letter) and `period_capital` (a period immediately followed
by an ASCII capital). Its proposal inserts ASCII spaces at those adjacencies,
without changing existing characters. For example, `,word` becomes `, word` and
`.Next` becomes `. Next`. Overlapping/touching punctuation hits may be combined
into one finding with several insertions.

Such findings arrive with a non-null `proposed` value and
`proposal_source: "deterministic_whitespace"`. That marker identifies the
proposal's mechanical origin; it does not certify agreement with the scan.
The rules also match legitimate adjacency such as abbreviation periods. Your
source review supplies the judgment those pattern rules cannot make. You are
neither generating new proposals nor applying the repairs during this task.

## Workspace and artifact roles

`repo-root` means the current workspace repository root, not a literal directory
named `repo-root`. `{{book}}` means the actual book directory in this repository;
identify it from the local file inventory and the report's artifact references.
Do not assume access to the commands or conversation that created these files.

| Workspace path | Role in this task |
| --- | --- |
| `repo-root/review/findings.json` | Full probe report, retained as the untouched baseline for the human-run executor. It is not another review work surface. |
| `repo-root/review/whitespace.json` | Whitespace-only report to review and edit in place. Its entries are complete copies from the probe report. |
| `repo-root/{{book}}/` | Original Paddle Markdown, JSON, and assets. Read-only machine observations. |
| `repo-root/{{book}}/imgs/source/` | Source page scans. Their pixels determine whether the proposed spaces belong. |
| `repo-root/review/whitespace_exceptions.json` | Report to write with complete copies of every finding left non-approved. |

Confirm the book directory before editing. Each `paddle_markdown` and
`paddle_json` path is relative to `repo-root/{{book}}/`. Each `source_image` path
is relative to `repo-root/{{book}}/imgs/source/`. Preserve any subdirectories in
those values; do not prefix a scan path with the Paddle root or choose a page by
its printed page number. If the book root cannot be identified unambiguously,
report the candidate paths and request the missing location before editing.

Load `review/whitespace.json` as JSON and keep an unedited snapshot in memory or
temporary storage outside the repository for the final integrity comparison.
Its top-level object contains `inputs` and `findings`.
Every finding's nonempty `triggers` list contains only `punctuation_letter`
and/or `period_capital`. A fresh finding has `review.status: null` and
`review.note: null`. If the report is missing, malformed, or contains other
trigger categories, stop and identify the problem rather than substituting
`findings.json`, regenerating reports, or changing their schema.

The report supplies candidates, not proven errors. Paddle Markdown and JSON
record what OCR observed; they can locate a passage but cannot establish what the
source printed. Language conventions and plausible prose also cannot substitute
for inspection of the corresponding scan.

## Locate the exact occurrence and review the complete proposal

Work through all findings in manageable source-page groups. Use your available
image-viewing capability to inspect the actual scans. Reading OCR text or seeing
an image filename is not visual inspection. Local read-only tools may be used to
load JSON, hash files, and inspect bytes; Normalize scripts need not be installed
in this book workspace.

For each finding:

1. Confirm the finding has text in `proposed` and
   `proposal_source: "deterministic_whitespace"`. A missing or unexpected
   proposal is an upstream report problem: leave the status unchanged, note the
   problem, and include the finding in the exceptions report. Do not generate a
   replacement yourself. Resolve `paddle_markdown` under the original book directory and read its raw
   bytes without newline normalization. Check the file against
   `source_md_sha256`, then verify
   `raw[start_byte:end_byte] == observed.encode("utf-8")`. These are zero-based
   UTF-8 byte offsets; `start_byte` is included and `end_byte` is excluded. They
   are not character positions or image coordinates. A mismatch leaves the
   finding unapproved: report it without changing offsets or locating a
   convenient substitute occurrence in another file.
2. Read sufficient surrounding Markdown to locate that exact occurrence on the
   scan identified by `source_image`. The observed span may begin at punctuation
   inside a larger expression, and the same text may occur more than once. Use
   the surrounding passage to distinguish occurrences; do not just inspect the
   first matching string on the page. A candidate in Markdown syntax, an image
   path, or metadata may have no printed counterpart; leave it unapproved rather
   than treating that syntax as source prose.
3. Compare every insertion in the complete `proposed` span with that printed
   occurrence. Look for deliberate adjacency, abbreviations, initials, notation,
   and other cases where the proposed spaces do not belong. Accept only when
   the source supports the complete existing proposal. A finding containing
   several insertions is one decision: if any insertion does not belong or
   cannot be verified, do not approve part of it, split it, or rewrite it.
4. For an accepted proposal, set `review.status` to exactly `"approved"`.
   Otherwise leave its incoming status unchanged and optionally add a concise
   `review.note` stating the source-based objection or specific missing evidence.
   Preserve an existing note when adding your observation.
   Missing/unreadable scans, ambiguous occurrence mapping, and failed byte/hash
   checks are unresolved findings, not grounds for approval.

For example, a finding inside `U.S.A` may have `observed: ".S.A"` and
`proposed: ". S. A"`. Inspect the whole abbreviation in its printed context. If
the scan shows `U.S.A`, leave the status unchanged and carry the finding into the
exceptions report. A span in `word.Next` may instead support an insertion if the
scan shows `word. Next`. Neither example is a global rule overriding the scan.

Do not approve by default merely because no objection was found without viewing
the evidence. If image inspection is unavailable, leave affected findings
unchanged and report that limitation. If a proposal is already `"approved"` and
you find an objection, stop and flag the conflicting existing decision: leaving
that status unchanged would still permit execution, and this task does not
authorize revoking an earlier approval.

## Save the decisions and exceptions without changing the findings

Edit only `review.status` and `review.note` in `review/whitespace.json`. Notes
must remain text or null. Preserve the top-level metadata, finding count and
order, IDs, paths, triggers, hashes, byte offsets, `observed`, `proposed`,
`evidence`, and all other values. Do not add fields, remove findings, change
proposals, or create alternative replacements. The executor mechanically compares
this report with the untouched baseline and hard-fails on other changes.

Write `review/whitespace_exceptions.json` with exactly this top-level shape:

```json
{
  "findings": []
}
```

Populate `findings` with complete copies of every finding whose final
`review.status` is not `"approved"`, in the original order and including any note
you added. Include objections, unresolved cases, and unreviewed findings if the
review is incomplete. Do not reduce entries to ID/reason summaries. An empty
list is appropriate only when every input finding was reviewed and approved,
or the input report contained no findings.

Before finishing, parse both saved reports and verify that:

- After disregarding only `review.status` and `review.note`, the edited whitespace
  report equals its initially loaded contents; no findings or other values changed.
- The exceptions report equals the ordered, complete non-approved subset of the
  edited whitespace report. Approved plus non-approved counts equal the original
  finding count.
- Every approval added in this run followed inspection of its exact source
  occurrence; unresolved or unreviewed findings did not acquire approval.

If your report edits fail these checks, correct them within the permitted fields
before claiming completion. Do not edit or use `review/findings.json` for this
work. Do not run OCR, the probe, extractor, executor, or project tests. Do not edit
source scans, Paddle artifacts, Markdown, scripts, or prompts. The two designated
review reports are the only repository files you may write; temporary state
for the integrity comparison must stay outside the repository.

Finish by reporting the actual book directory, both output report paths, the
input finding count, approvals added in this run, final approved/non-approved
counts, and whether all findings were reviewed. Identify any unreviewed findings
or blocked pages by their recorded IDs/paths. Never present a partial review as
complete. The human runs the executor against the edited whitespace report; the
exceptions report records what remains outside execution.
