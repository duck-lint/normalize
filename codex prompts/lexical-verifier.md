# Parallel independent lexical verification — printed scans decide

## Parent configuration (fill before running)

```yaml
target_book: "{{BOOK_NAME}}"
# Inclusive 1-based positions in the full source-image sequence:
batches:
  agent1: "{{RANGE_1}}"
  agent2: "{{RANGE_2}}"
  agent3: "{{RANGE_3}}"
  agent4: "{{RANGE_4}}"
```

Example for 181 source scans: `1-45`, `46-91`, `92-137`, `138-181`.
Replace placeholders; remove unused agents. This verifier run must be a
**fresh, separate Codex session** after the complete proposal-stage join,
never a continuation of a proposer worker. The human runs the joiner after
verification and separately conducts vocabulary review and any execution.

## Parent agent — partition and dispatch, not verification

Read `AGENTS.md`. In a scan-only workspace, accept **only** the *frozen full*
`lexical.json` from the completed proposal join and the original
source scans. Do not expose raw Paddle/Markdown, full probe, earlier proposer
threads/batch outputs, segmentation hints, or the writable global lexicon to
workers. Proposal text and notes are claims/hints, not verification evidence.

Resolve configured ranges against the ordered source-image sequence, not
printed page labels or finding positions. Pages without findings still count.
If ordering is ambiguous, stop rather than guess. Validate ranges cover the
source-image sequence without gaps or overlaps; resolve to explicit relative
scan paths and reject traversal outside the scan root. Refuse ambiguous,
missing or unassigned source-image references in findings.

Construct immutable partial inputs from the frozen proposal artifact. Each
preserves its `format`, `inputs`, **entire global `vocabulary` inventory**,
and the assigned findings with all proposal fields in original order.

Use separate exclusive input/output paths, e.g.:

- `lexical_batches/verification/inputs/agent1.json`
- `lexical_batches/verification/outputs/agent1.json`

The output directory must contain only completed agent JSON outputs. Record
ranges with zero assigned findings but do not dispatch empty batches.
Never edit the frozen proposal report.

Spawn identical verifier subagents concurrently up to CLI limits with their
own partial input, original scans and exclusive output path, and the contract
below. Do not verify findings or edit worker decisions as parent. Wait for all,
report actual completion/failure and output paths. Never invoke the joiner,
human lexicon review, or executor. Do not stage, commit, reset or alter unrelated
files.

## Worker contract — include with each subagent assignment

You are the independent, second-pass scan verifier. Inspect **only** your
assigned frozen proposals and corresponding original scan pixels. Treat each
non-null proposed replacement as an unverified claim, even when supported
by plausible words, proposer evidence or a segmentation hypothesis.

**Mandatory image-access gate:** actually open and visually inspect source
images. If image viewing is unavailable, a needed scan is missing/unreadable,
or image access fails, **stop immediately** and publish no completed batch
output. Text excerpts, filenames, file presence and earlier agent assertions
cannot substitute for seeing the pixels.

For every finding, locate the exact printed occurrence using the source image
and OCR context. Check all proposed differences, including glyphs, deletions,
insertions and word boundaries. For a complete proposed replacement supported
unambiguously by printed pixels, set `review.status` to `"approved"` and
write a concise `review.note` explaining independent visual evidence.
Otherwise leave `review.status` null with a nonempty note explaining the
specific contradiction or uncertainty; do not approve part of a replacement.
Never approve a finding with `proposed: null`.

For null proposals, inspect the exact observed spelling too. When direct scan
inspection confirms an **isolated printed irregularity unsuitable for a reusable
lexicon**, preserve null status and use the exact prefix
`SOURCE_FAITHFUL_NONLEXICAL_VERIFIED:` followed by concrete visual
evidence/location (at least twelve substantive nonblank characters).
Do **not** use the prefix merely because OCR matches print: Greek/Latin,
historical and British spellings, proper names, foreign terms and ambiguous
forms still merit human lexicon consideration. For other no-proposal findings,
leave null status and provide a nonempty ordinary note explaining whether
the printed form remains plausible or what could not be resolved. This
classification is **not** lexicon admission, which is human-only.

Preserve **every** finding, its original order, IDs, proposals, evidence,
source paths, context, hashes, inputs and global vocabulary. Write a complete
new batch output at your exclusive assigned path. You may edit **only**
`review.status` and `review.note` (status null or `"approved"`);
every finding in the completed output must have a nonempty review note.
Never overwrite the input or canonical proposals, fabricate printed evidence,
run repairs/joiners/tests/OCR, or access other agents' outputs. If unable
to complete, publish no completed output; report the obstacle accurately.

## Human join — separate, after all verifiers finish

```bash
python /path/to/normalize/join_lexical.py \
  --stage reviewed \
  --baseline review/probe2.json \
  --source review/lexical.json \
  --batches review/lexical_batches/verification/outputs \
  --out review/lexical-reviewed.json
```

The joiner reconstructs the complete verification report from the frozen
proposals, imports only `review.status` and `review.note`, and validates
both handoffs using the existing lexical executor's contract. It verifies
structural integrity, **not** source pixels. The human separately reviews
vocabulary and decides whether to run `execute_lexical_repairs.py`.
