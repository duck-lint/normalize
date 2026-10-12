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
**fresh, separate Codex session** after all proposer batches have finished,
never a continuation of a proposer worker. **No intermediate join is needed.**
The human runs one join after verification and separately conducts vocabulary
review and any execution.

## Parent agent — partition and dispatch, not verification

Read `AGENTS.md`. In a scan-only workspace, accept the **completed, frozen
per-agent proposer JSON files** and original source scans.

**Workspace boundary:** This is the isolated Codex review workroot, not the
Normalize tooling checkout. Review sessions use only original scan pixels and
restricted batch reports. Paddle JSON/Markdown, full probes, repair executors,
joined reports and the writable lexicon stay in the tooling checkout. The human
copies the extracted `lexical.json` into this workroot before proposal review
and copies the finished batch tree back to tooling after both Codex stages.
Do not access the tooling checkout or run OCR, probes, joins or repairs here. Each verifier sees
only its assigned proposer batch, not proposer conversations, raw Paddle /
Markdown, full probe, segmentation hints, other agents' outputs, or writable
global lexicon. Proposal text and notes are claims, not verification evidence.

Resolve configured ranges against the ordered source-image sequence, not
printed page labels or finding positions. Pages without findings still count.
If ordering is ambiguous, stop rather than guess. Validate ranges cover the
source-image sequence without gaps or overlaps; resolve to explicit relative
scan paths and reject traversal outside the scan root. Refuse ambiguous,
missing or unassigned source-image references in findings.

Use each completed proposer batch as the corresponding immutable verifier
input, with the **same source-image ranges**. Each batch already contains
its `format`, `inputs`, **entire global `vocabulary` inventory**, and
assigned findings with all proposal fields in original order. Do not merge
the proposals before dispatching verification.

**Mandatory pre-dispatch gate (parent only, inside the workroot):** This is a
required command/check, not merely a description. Discover the real per-book
`lexical_batches` path and replace the example below; use the configured agent
IDs (not necessarily four). Run it **before spawning any verifier**:

```bash
batch_root='lexical_reports/About Vision & Color/lexical_batches'  # EXAMPLE: resolve actual path
mkdir -p "$batch_root/verification/inputs"
for n in 1 2 3 4; do  # EXAMPLE: replace with assigned nonempty batch IDs
  original="$batch_root/proposals/inputs/agent$n.json"
  src="$batch_root/proposals/outputs/agent$n.json"
  dst="$batch_root/verification/inputs/agent$n.json"
  [[ -f "$original" && -f "$src" && ! -L "$original" && ! -L "$src" ]] || {
    echo "MISSING or symlinked proposal batch agent$n" >&2; exit 1;
  }
  if cmp -s -- "$original" "$src"; then
    echo "UNREVIEWED proposer output for agent$n; STOP" >&2; exit 1
  fi
  [[ ! -L "$dst" ]] || { echo "Symlinked verifier input agent$n; STOP" >&2; exit 1; }
  if [[ ! -e "$dst" ]]; then
    cp -- "$src" "$dst" || exit 1
  fi
  cmp -s -- "$src" "$dst" || { echo "WRONG verifier input agent$n; STOP" >&2; exit 1; }
  [[ ! -e "$batch_root/verification/outputs/agent$n.json" &&
     ! -L "$batch_root/verification/outputs/agent$n.json" ]] || {
    echo "Existing verifier output agent$n; STOP, preserve run" >&2; exit 1;
  }
  echo "agent$n: completed proposal copied and verified"
done
```

The **only** source for `verification/inputs/agentN.json` is
`proposals/outputs/agentN.json`, NEVER `proposals/inputs/agentN.json` or
a fresh extraction. Matching names, finding counts, hashes embedded in JSON
or parent summaries do not substitute for byte equality. If any input exists
but differs, STOP; do not overwrite it or silently repair a past run.
Do not dispatch ANY verifiers until every configured nonempty batch passes.
Verify that each child receives the corresponding verified
`verification/inputs/agentN.json`, not any other similarly named file.
Use separate exclusive input/output paths, e.g.:

- `lexical_batches/verification/inputs/agent1.json`
- `lexical_batches/verification/outputs/agent1.json`

The output directory must contain only completed agent JSON outputs. Record
ranges with zero assigned findings but do not dispatch empty batches.
Never edit the completed proposer batch outputs.

Spawn identical verifier subagents concurrently up to CLI limits with their
own partial input, original scans and exclusive output path, and the contract
below. Do not verify findings or edit worker decisions as parent. Wait for all,
report actual completion/failure and output paths. Never invoke the joiner,
human lexicon review, or executor. Do not stage, commit, reset or alter unrelated
files.

**Mandatory post-dispatch gate (parent only):** Do not report a verifier batch
as complete solely because a child says it finished. After workers return,
compare each new verifier output with its immutable verifier input, ignoring
only the permitted `review` decisions. Run this **read-only** standard-library
check in the workroot with the same resolved `batch_root` variable:

```bash
python3 - "$batch_root" <<'PY'
import copy, json, sys
from pathlib import Path
root = Path(sys.argv[1])
inputs = root / 'verification' / 'inputs'
outputs = root / 'verification' / 'outputs'
names = {p.name for p in inputs.glob('agent*.json')}
if not names or names != {p.name for p in outputs.glob('agent*.json')}:
    raise SystemExit('Missing, extra, or incomplete verifier outputs; STOP')
for name in sorted(names):
    proposal = (root / 'proposals' / 'outputs' / name).read_bytes()
    frozen = (inputs / name).read_bytes()
    if proposal != frozen:
        raise SystemExit(f'{name}: verifier input is not frozen proposal; STOP')
    before = json.loads(frozen)
    after = json.loads((outputs / name).read_bytes())
    if set(before) != set(after) or any(
        before[k] != after[k] for k in before if k != 'findings'
    ) or len(before['findings']) != len(after['findings']):
        raise SystemExit(f'{name}: report structure altered; STOP')
    for i, (a, b) in enumerate(zip(before['findings'], after['findings']), 1):
        review = b.get('review')
        if (not isinstance(review, dict) or set(review) != {'status', 'note'}
                or review['status'] not in (None, 'approved')
                or not isinstance(review['note'], str)
                or not review['note'].strip()
                or (review['status'] == 'approved' and a['proposed'] is None)):
            raise SystemExit(f'{name} finding {i}: invalid review; STOP')
        copy_b = copy.deepcopy(b)
        copy_b['review'] = a['review']
        if copy_b != a:
            raise SystemExit(f'{name} finding {i}: frozen proposal changed; STOP')
    print(f'{name}: complete and immutable outside review fields')
PY
```

On failure, preserve all inputs/outputs and report the exact batch; do not
patch failed verifier files or present them as source-verified. A run that
received unreviewed proposer inputs requires **new independent verification**
from the correct frozen outputs, not a retroactive transfer of proposal fields.
These checks guard data handoffs; only the human's later tooling-checkout join
reconstructs and validates the complete cross-batch reports.

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

## One human-run join after both stages

Once *all* proposer and verifier batch outputs are complete, run this **one**
command in the Normalize tooling checkout, substituting the actual paths:

```bash
python /path/to/normalize/join_lexical.py \
  --baseline review/probe2.json \
  --extracted review/lexical-extracted.json \
  --proposal-batches review/lexical_batches/proposals/outputs \
  --verification-batches review/lexical_batches/verification/outputs \
  --out-dir review
```

The joiner independently reconstructs `review/lexical-proposals.json` and
`review/lexical-reviewed.json` from the untouched lexical extraction and the
two batches of completed outputs. It validates exact-once coverage, both
sets' permissions, and the unchanged lexical executor's handoff contract.
It **does not** certify source pixels. The human then proceeds with normal
lexicon review and chooses whether to invoke `execute_lexical_repairs.py`.
