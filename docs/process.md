# Current book processing workflow

This document records the independent original punctuation-whitespace stage
through Probe 2. The **subsequent lexical stage** is implemented separately
and documented in [lexical-stage.md](lexical-stage.md). Later structural and
book-reconstruction stages remain out of scope.

## Names and authority

**Probe 1** and **Probe 2** mean successive full probes of different artifact
snapshots. The whitespace-only report is a review handoff between them; it is
not Probe 2. Older documentation's “report two” means that whitespace handoff,
and “report three” means the review exceptions report.

Authority remains: source scan pixels → human-accepted review decisions → raw
Paddle observations → derived repaired Markdown. A new operational baseline
does not replace the scans as evidence or make the derived text infallible.

| Step | Input | Operation and owner | Output |
| --- | --- | --- | --- |
| 1. Paddle scan | Source page images | `paddle_scan.py` runs OCR | Raw Paddle JSON, Markdown, and assets |
| 2. Probe 1 | Source scans + raw Paddle directory | `normalize_probe.py` detects candidates and proposes deterministic punctuation spaces | Full `probe1.json`, untouched thereafter |
| 3. Extract whitespace | Probe 1 | `extract_whitespace.py` selects qualifying findings and copies them intact | `whitespace-only.json` |
| 4. Review proposals | Source scans + whitespace-only report | Codex locates each printed occurrence, edits only `review.status` and `review.note`, and copies non-approved findings into a separate report | Reviewed whitespace report + `whitespace_exceptions.json` |
| 5. Accept and execute | Human-accepted reviewed report + untouched Probe 1 + raw Paddle directory | Human previews/runs `execute_repairs.py`; executor verifies and applies only exact `"approved"` proposals | New whitespace-repaired directory + `execution_report.json` |
| 6. Probe 2 | Same scans + whitespace-repaired directory, including execution report | `normalize_probe.py` detects candidates in the actual repaired Markdown and verifies comparison provenance | Full `probe2.json` + auditable JSON/Markdown comparison exceptions within it |

## Commands

Run from a book workspace with scripts kept in a separate tooling checkout.
Paths below are examples. Inputs are recursive directories; each page stem must
uniquely match across source image, `.md`, and `_res.json`.

```bash
python /path/to/normalize/paddle_scan.py \
  --images scans --out paddle --device gpu:0
python /path/to/normalize/normalize_probe.py \
  --scans scans --paddle paddle --out review/probe1.json
python /path/to/normalize/extract_whitespace.py \
  --report review/probe1.json --out review/whitespace-only.json
```

Codex then uses [the review prompt](../codex/processing-prompts.md) in a separate
review workspace containing the whitespace report and scans. It does not run
execution. The human reviews the resulting decisions before these commands:

```bash
# Preview only; produces no repaired directory or execution report.
python /path/to/normalize/execute_repairs.py \
  --baseline review/probe1.json --report review/whitespace-only.json \
  --paddle paddle --out whitespace-repaired

# Execute into a new directory.
python /path/to/normalize/execute_repairs.py \
  --baseline review/probe1.json --report review/whitespace-only.json \
  --paddle paddle --out whitespace-repaired --execute

# The execution report is read automatically from this directory.
python /path/to/normalize/normalize_probe.py \
  --scans scans --paddle whitespace-repaired --out review/probe2.json
```

Keep reports outside input directories. Existing outputs are refused. Preserve
the full raw directory, Probe 1, reviewed report, review exceptions, repaired
directory, execution report, and Probe 2 as separate stage artifacts.

## Two different meanings of exception

`whitespace_exceptions.json` is **Codex's review exceptions report**: complete
copies of proposals that were not approved, with their review notes. It grants
no execution or comparison authority.

`probe2.json`'s `json_markdown_exceptions` is **the probe's comparison audit**:
JSON blocks absent from the actual repaired Markdown but present in the
mechanically reconstructed, hash-verified pre-whitespace Markdown. Those
blocks are excluded only from `json_markdown_difference:*` candidate findings.
They stay visible in this separate audit array.

Codex does not flip another field when approving a finding. Approval alone
cannot authorize suppression. The executor records comparison semantics only
for validated, executed changes, in `execution_report.json`:

- `execution_format: "punctuation_whitespace_v1"`;
- source scans and Paddle directory hashes;
- executed IDs, paths, triggers, original byte spans, observed/proposed text,
  source and final derived Markdown hashes;
- `json_markdown_comparison: "reverse_executed_punctuation_spaces"` per change;
- hashes of the reviewed report and untouched Probe 1 in CLI executions.

Probe 1 initializes `inputs.json_markdown_comparison` with `mode: "raw"` and a
null execution report hash. Its `json_markdown_exceptions` is empty. The extractor
copies `inputs` and every selected finding unchanged, including this provenance.
There is no reviewer-editable suppression field to propagate.

Probe 2 records `mode: "verified_executed_whitespace"`, the execution report's
hash, the reconstructed source directory hash, and the executed finding count.
Each comparison exception records its page, JSON block ID, rule, content,
artifact paths, source/derived Markdown hashes, and the executed IDs **on that
page**. Those IDs are page-level provenance, not an asserted block alignment.

## What the next probe checks

1. Read actual repaired Markdown for punctuation, lexical, and empty-page
   detections. New candidate offsets, hashes, and OCR context address this exact
   input snapshot. Context is labelled `derived_whitespace_markdown`.
2. When an execution report is present, validate its format, scan identity,
   deterministic space-only changes, unique IDs, non-overlapping ranges,
   replacement bytes, and derived page hashes.
3. Account for cumulative byte shifts and reverse only those changes in memory.
   Verify each reconstructed source page hash, then the entire reconstructed
   source directory hash, excluding only the added execution report. This also
   checks unchanged JSON, assets, and untouched Markdown pages.
4. Compare JSON block content against the actual Markdown first. Only a missing
   block that is present in the verified pre-whitespace comparison view is
   recorded as a comparison exception. All other missing blocks remain findings.

For example, JSON `The cat,sat on the mat.` and raw Markdown
`The cat,sat on the hat.` still produce a discrepancy after an approved space
makes the Markdown `The cat, sat on the hat.`. Reversal restores the spacing,
but the unrelated `mat`/`hat` difference remains; it is not excepted.

The underlying comparison remains whitespace-flattened substring containment,
not occurrence-level JSON/Markdown alignment. This change preserves that rule;
an exception is not certification of a whole page or JSON block. Hashes verify
snapshot consistency, not scan accuracy or a maliciously rewritten ledger's
authenticity. Visual review and human acceptance remain the approval authority.

Invalid execution provenance stops probing before writing a report. It never
silently switches to raw comparison or broadly exempts a repaired page.

## Current boundary and cutover

JSON, assets, and any images within the Paddle directory remain byte-for-byte
copies. Separate source scans remain separate. Copying policy is unchanged;
identifying unnecessary images is a separate decision.

This punctuation executor handles one punctuation-whitespace execution from
raw Paddle input. It remains limited to deterministic punctuation spaces.
The separate lexical executor builds on the **verified Probe 2 derivative**
with its own origin checks, immutable review handoffs, replacement ledger and
lexicon approval contract. The next probe composes that lexical ledger and
this existing whitespace ledger in memory for comparison. Do not pass Probe 1
offsets to the lexical executor, or repaired artifacts to this whitespace
executor. See [lexical-stage.md](lexical-stage.md).

For this contract, regenerate Probe 1 and the extracted report, retain/review
the decisions through the normal handoff, and execute with the updated tooling
into a new directory. Older execution reports are rejected; no legacy fallback
or manual suppression migration is provided.
