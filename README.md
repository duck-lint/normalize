# Normalize: staged OCR repairs

The original stage inserts ASCII spaces after punctuation, preserving raw
Paddle observations. A new **separate lexical stage** supports reviewed word
segmentation and character corrections plus an explicitly human-approved
persistent lexicon; it never widens the original punctuation executor.
See [punctuation process](docs/process.md) and the complete
[lexical stage contract](docs/lexical-stage.md) for distinct handoffs,
immutable snapshots, CLI usage, chained reprobe provenance, and recovery.
Both lexical Codex review stages now permit manual, nonoverlapping source-scan
batches: see [parallel proposer](codex%20prompts/lexical-proposer.md) and
[independent verifier](codex%20prompts/lexical-verifier.md).
After all proposer and independent verifier agents finish, the human runs
**one** `join_lexical.py` command with both batch directories. It publishes
complete `lexical-proposals.json` and `lexical-reviewed.json` artifacts for
the **unchanged** lexical executor. No pipeline scheduling or lexicon
admission is delegated.

1. `paddle_scan.py` processes page scans into raw PaddleOCR JSON and Markdown.
2. `normalize_probe.py` reads that output and writes the full candidate report.
   It records exact original UTF-8 byte spans and bounded OCR locating context.
   It supplies deterministic space proposals for `punctuation_letter`
   (`,;:!?` followed by an ASCII letter) and `period_capital` (a period followed
   by an ASCII capital). Lexical and structural candidates can appear in this
   full report but have no repair proposals. Punctuation findings stay separate
   from overlapping lexical findings so extraction does not lose them.
   Lexical checks operate on whole Unicode-letter tokens (including combining
   marks), not ASCII fragments of accented words. Structural HTML, Markdown
   code and link destinations, and TeX command names are excluded from lexical
   checks without changing source text or byte offsets. Punctuation-space
   proposal patterns remain unchanged. The separate lexical stage uses
   English, German and French Hunspell dictionaries plus the human lexicon.
3. `extract_whitespace.py` copies findings whose nonempty trigger set contains
   only `punctuation_letter` and/or `period_capital` into report two. Each finding
   is copied intact, including its proposal and `review` object. The extractor
   does not calculate, alter, approve, or repair anything.
4. The human configures source-image ranges in the
   [parallel whitespace review prompt](codex%20prompts/whitespace.md). One
   parent Codex agent dispatches identical subagents to disjoint batches.
   Each visually checks original scan pixels and writes its own batch report;
   the untouched extraction is never edited.
5. The human runs `join_whitespace.py` to rebuild a complete reviewed report,
   accepting only `review.status` and `review.note` changes across exactly-once
   findings. The joiner also derives an informational exceptions report. After
   reviewing the joined result, the human runs the **unchanged** executor;
   only exact `"approved"` statuses enable repair.

6. `normalize_probe.py` probes the repaired directory again. Its execution report
   is automatically verified and used to exclude only JSON/Markdown mismatches
   explained by executed punctuation spaces. Remaining detections use the actual
   repaired Markdown, with fresh offsets and hashes.

For the post-Codex, **post-bulk Review UI** cross-book diagnosis before exhaustive\nhuman vocabulary review, see [corpus analysis](docs/post-bulk-corpus-analysis.md).\nThe analyzer preserves pending and bulk-excluded findings separately, joins\noriginal source hashes, and makes no repair or lexicon decisions.\n\n## Files and commands

Keep Normalize scripts in a tooling checkout. Run these commands from a separate
book workspace. Replace `/path/to/normalize` with the tooling checkout path.
Inputs are ordinary directories, searched recursively. Page image stems must
match their Paddle `.md` and `_res.json` stems and must be unique within each
artifact type, even across subdirectories. Image suffixes are case insensitive.

Use Python 3.11 or newer. PaddleOCR and its matching PaddlePaddle runtime must
already be installed for step one. The probe and segmentation sidecar require
`libhunspell-1.7` and **all three** Hunspell dictionary pairs:
`/usr/share/hunspell/{en_US,de_DE,fr_FR}.{aff,dic}`. On Ubuntu install
`libhunspell-1.7-0 hunspell-en-us hunspell-de-de hunspell-fr-classical`.
Use `--hunspell-dir` for both commands if files live elsewhere. Missing pairs
cause a hard error, never a silent English-only fallback. All six file hashes
are recorded by language in `inputs.dictionary_sha256`. Extraction and execution
use the standard library only; they do not instantiate Hunspell or PaddleOCR. Artifact directories must contain regular files/directories, not
symlinks to outside content.

```bash
python /path/to/normalize/paddle_scan.py --images scans --out paddle --device gpu:0
python /path/to/normalize/normalize_probe.py \
  --scans scans --paddle paddle --out review/probe.json
python /path/to/normalize/extract_whitespace.py \
  --report review/probe.json --out review/whitespace.json
```

Keep reports outside the raw input directories. `review/probe.json` is report
one and stays untouched. Each `source_image` is relative to the `--scans`
directory; each `paddle_markdown` and `paddle_json` is relative to the `--paddle`
directory. These paths do not include the input root's name. Moving an unchanged
input directory does not invalidate reports: directory hashes cover relative
file names and file contents, not the root's absolute path or file timestamps.

Report two initially looks like this (illustrative values):

```json
{
  "inputs": {"paddle_dir_sha256": "...", "source_dir_sha256": "...", "dictionary_sha256": {}, "json_markdown_comparison": {"mode": "raw", "execution_report_sha256": null}},
  "findings": [
    {
      "id": "page001:punctuation_letter:11",
      "page": "page001",
      "rule": "punctuation_letter",
      "triggers": ["punctuation_letter"],
      "source_image": "page001.jpg",
      "paddle_markdown": "page001.md",
      "paddle_json": "page001_res.json",
      "source_md_sha256": "...",
      "start_byte": 11,
      "end_byte": 16,
      "json_block_id": null,
      "ocr_context": {
        "provenance": "raw_paddle_markdown",
        "start_byte": 0,
        "end_byte": 17,
        "text": "Hello world,word."
      },
      "observed": ",word",
      "proposed": ", word",
      "proposal_source": "deterministic_whitespace",
      "evidence": null,
      "review": {"status": null, "note": null}
    }
  ]
}
```

Give Codex the unchanged extracted whitespace report and source scans in
a separate review workspace. Original Paddle output and Probe 1 stay outside
the agents' accessible environment. The parent maps manually configured
1-based source-image ranges to disjoint subagent inputs; each worker writes a
complete batch report or stops without publishing if scans cannot be viewed.
For `U.S.A`, a proposal must remain unapproved if the source prints no spaces.

The human then joins only completed JSON outputs, held in a directory containing
no other files. `whitespace.json` remains untouched. The joiner reconstructs
from Probe 1, rejecting missing, duplicated, unreviewed, out-of-order, and
unauthorized changes, and writes the final executor-compatible report:

```bash
python /path/to/normalize/join_whitespace.py \
  --baseline review/probe.json --report review/whitespace.json \
  --batches review/batches/outputs \
  --out review/whitespace-reviewed.json \
  --exceptions-out review/whitespace_exceptions.json
```

Then the human can preview or execute:

```bash
python /path/to/normalize/execute_repairs.py \
  --baseline review/probe.json --report review/whitespace-reviewed.json \
  --paddle paddle --out repaired
python /path/to/normalize/execute_repairs.py \
  --baseline review/probe.json --report review/whitespace-reviewed.json \
  --paddle paddle --out repaired --execute
python /path/to/normalize/normalize_probe.py \
  --scans scans --paddle repaired --out review/probe2.json
```

## Locating a finding without original Paddle files

The probe already records `start_byte`/`end_byte` for each finding, and the
extractor copies those fields unchanged. The probe now also supplies `ocr_context`
for every finding that has a Markdown span. It contains a `raw_paddle_markdown`
provenance label, exact original byte offsets for the excerpt, and its unchanged
text: the finding plus up to 160 Unicode characters on each side. Boundaries are
chosen in characters before conversion to byte offsets, so multibyte UTF-8 text
is not split; CRLF and Markdown syntax are preserved.

Finding and context offsets address the same original Markdown bytes. Subtract
`ocr_context.start_byte` from the finding offsets to identify the target within
`ocr_context.text.encode("utf-8")`. This distinguishes the target from nearby
matching strings while giving Codex bounded surrounding text for locating the
passage in the source image. The offsets are not image coordinates. No image
bounding box is fabricated. The excerpt is OCR-derived and can itself contain
errors; it is a locating hint, never independent evidence of correct wording or
spacing. Ambiguous printed occurrences remain unapproved.

The extractor still performs only selection and complete-record copying. It
neither generates context nor changes the original repair span. The executor's
baseline comparison protects the new context fields as well as existing fields.
Regenerate the probe and whitespace reports for this contract; no older-report
compatibility path is provided.

The subagents do not require raw Markdown/JSON, the full probe report, or
tooling in their workspace. The human-run joiner needs untouched Probe 1 and
the extracted report; the executor still requires the original Paddle directory
in its separate environment.
For an actual access restriction, original artifacts and any repository history
containing them must be outside the review process's accessible environment;
these scripts do not configure Codex's filesystem permissions.

## Baseline and execution provenance

`--baseline` is report one, not a backup of the book and not another approval
stage. The joiner and executor require the reconstructed reviewed report to be
the exact extracted subset, with edits limited to `review.status` and `review.note`. This detects
changed proposals, IDs, offsets, paths, or omitted findings. Insertion itself does
not mathematically require a baseline; this implementation requires it to enforce
that report-integrity contract. Only the edited second report supplies approvals.

Before creating output, the executor checks the original Paddle directory's
content hash, exact UTF-8 byte spans, deterministic space-only proposals, and
non-overlapping approved ranges. It then copies the **entire** Paddle directory
into temporary staging outside the source, verifies the copy's content hash,
repairs only copied Markdown, writes the execution log, and publishes the new
output directory. Failed validation/copying does not publish a partial output.
Existing output paths are refused, as are outputs nested inside the original
Paddle directory. The original directory and all reports remain unchanged.

| Artifact | Original input | New output directory |
| --- | --- | --- |
| Paddle `.md` | Unchanged | Approved spaces inserted; unchanged pages copied verbatim |
| Paddle `_res.json` and other JSON | Unchanged | Copied byte-for-byte; still the original machine observations |
| Paddle images/assets and other files | Unchanged | Copied byte-for-byte; original relative paths preserved |
| Source scans | Unchanged | Copied unchanged if inside the Paddle directory; otherwise remain separate |
| Review reports | Unchanged | Not edited or copied by the executor |
| `execution_report.json` | Not present in raw input | Records executed IDs, original offsets, text changes, and input/output hashes |

The copied JSON is **not a corrected structured transcription**. It continues to
record what Paddle observed; only Markdown is a repaired derivative. No human
backup/copy step is required to protect raw artifacts from this executor.

The next probe reads `execution_report.json` automatically. It reconstructs the
pre-whitespace Markdown in memory and verifies page and whole-directory hashes
before using it solely for JSON comparison. Excluded mismatches remain auditable
under `json_markdown_exceptions`; `inputs.json_markdown_comparison` records the
execution provenance. These differ from Codex's non-approved review exceptions.
Approval alone does not suppress a comparison. Invalid provenance stops probing.
Regenerate reports and execution output for this contract; older execution logs
are rejected. See [the process document](docs/process.md) for the exact boundary.

## Multiple repairs on one page

All finding offsets refer to the original page's UTF-8 bytes. The executor first
validates every approved finding against that original page and rejects
overlapping ranges. It applies edits from the highest byte offset toward the
lowest. A space inserted near the end cannot shift an earlier edit's location.
Each page is written once with all its accepted repairs, and the execution log
records the final page hash for each executed finding.

For example, with two approved findings, `one,two three;four` becomes
`one, two three; four` in the copied Markdown. The original remains unchanged.
If more proposals are approved later, rerun the complete edited second report
against the same original Paddle directory into a new output directory. Do not
apply original offsets to an already repaired directory.

## Validation

Run either command from the tooling checkout root:

```bash
python tests/test_whitespace_workflow.py
python -m unittest discover -s tests -v
```

Tests cover the actual directory → probe → copy → status edits → execution
handoff, including abbreviations, lexical overlap, Unicode offsets, multiple
repairs on one page, unchanged JSON/assets/source files, non-approved statuses,
original/context byte-span identity and unchanged extraction, a review handoff
without Paddle files, and refusal of unauthorized report changes or unsafe
output placement.
They also cover reprobe comparison exceptions, unchanged lexical findings,
fresh derived offsets/context, unrelated differences within repaired blocks,
and rejection of altered execution records, artifacts, or scans.
