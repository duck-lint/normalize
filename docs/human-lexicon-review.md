# Human vocabulary review app

This is the separate **human** acceptance handoff for global lexicon entries.
It runs *after* the two Codex sessions and *before* lexical execution. You can
use your already-completed `lexical-reviewed.json`; do not rerun either agent.

## Launch

Run in your book workspace, with the Normalize tooling checkout available:

```bash
python /path/to/normalize/review_lexicon.py \
  --baseline review/probe2.json \
  --proposals review/lexical-proposals.json \
  --reviewed review/lexical-reviewed.json \
  --scans scans \
  --lexicon /shared/lexicon.json \
  --out review/human-lexicon-approvals.json
```

Replace the paths above with the files actually created in your book workspace.
The app opens a browser on `127.0.0.1` at a randomly selected available port;
you can add `--no-browser` to print the URL without opening a tab.
It uses Python's standard-library local HTTP server and adds **no web-app
dependencies** or external network service.

The local process must remain running while you review. Use Ctrl+C in the
terminal to stop it. Progress automatically saves beside the output path as
`human-lexicon-approvals.progress.json`, unless you specify `--progress`.
Re-run the same command to continue from saved progress.

## How the decisions work

The left pane groups **all unrecognized lexical forms**, including ones
Codex did *not* suggest, by NFC/casefold. It sorts by frequency by default;
filter independently by **lexicon decision status** (Pending, Accepted, Rejected),
**repair proposal evidence** (any proposed repair, all proposed, all independently
approved, mixed, or none), and **Codex suggestion / admission eligibility**.
These filters compose, so you can isolate pending forms with proposed repairs,
inspect their occurrence chips and original scans, then filter remaining pending
vocabulary without reopening anything already decided.
The right pane displays original scan pixels, the selected occurrence and its
exact UTF-8-aligned OCR context. The context is a locating hint only.

Select any occurrence and inspect the original scan before admission. Use the
occurrence buttons to compare examples; entries for which Codex proposed a
character/word-boundary repair are visibly marked and **cannot support
admission**. If the same spelling has both repaired and unrepaired occurrences,
a warning appears: only an *unrepaired occurrence* may support an admission.

### Batch rejection of repair-only lexical candidates

Choose **Pending** under status, then choose **All independently approved**
under repair proposals. Browse the grouped lexical forms and their full
occurrence list as needed. Click **Bulk reject** for a preview showing the exact
number of *visible pending lexical types* to be affected. A separate explicit
checkbox and confirmation are required. Search and all active filters define
the visible subset; accepted or previously rejected decisions are not changed.

**Safety boundary:** bulk rejection only acts on a lexical form if *every*
occurrence has a proposed OCR change **and** the independent verifier set
`review.status: "approved"` for every one of those changes. Mixed forms,
unverified repairs, unrepaired occurrences, already-known vocabulary and
previously decided forms are excluded, even if they appear in the filtered list.
A mixed form can be a genuine printed word despite a different occurrence being
wrong; review those individually. The whole submitted batch is validated before
any decision is written. Invalid or stale inputs refuse the entire batch.

This bulk command changes **only** the human vocabulary review progress:
`decision: "rejected"` for the selected lexical types. It does NOT modify
`lexical-reviewed.json`, change a spacing/character replacement, approve any
unverified OCR repair, or add words to the shared lexicon. Review rejection is
not a permanent blacklist; it excludes admission from this particular batch.
The review decisions remain resumable and can be cleared individually later.

**Accept** requires you to check that you personally inspected the exact scan,
choose an admissible occurrence, and enter a nonempty evidence note.
**Reject** saves your decision without global admission.
**Skip / clear** leaves the type undecided.
No candidate is automatically accepted; frequency, Codex's Boolean suggestion
and review.status do not authorize global admission.

Keyboard commands (when not typing in a field): Up/Down switch words;
Left/Right switch occurrences; A accepts, R rejects, K clears; / focuses search.
The original scan can be enlarged or opened in a separate browser tab.

## Export and execute

When ready, click **Export approved JSON**. This produces the executor's
existing `human_lexicon_approvals_v1` format with source finding IDs, human
notes and exact report/lexicon hashes. Only accepted distinct lexical types
become entries; one occurrence is enough to support each type. Rejected and
undecided types are never in the approval file.

The exporter calls the actual executor's admission validator before writing.
It also rehashes scans and reports to reject stale inputs. Existing approvals
files are **never overwritten**. To change the decisions after exporting,
choose a fresh `--out` filename and optionally keep the same progress file.

It does **not** change `lexicon.json`, change scanned/OCR text or run
`execute_lexical_repairs.py`. You still review and invoke the lexical executor
yourself, with `--lexicon-approvals review/human-lexicon-approvals.json` and
your earlier `--baseline`, `--proposals` and `--reviewed` arguments.

**Occurrence repair approvals** in lexical-reviewed.json and **global
vocabulary admissions** in this approval file remain independent. Do not edit
the frozen reports to record lexicon decisions.

## Snapshot and local security

Startup validates the proposer/verifier handoffs, source scan directory hash,
exact lexicon hash, and each finding's UTF-8 OCR-context span. Saved progress is
bound to all four input-file hashes and the scan-directory hash, so a different
book/probe/lexicon cannot silently inherit earlier decisions.

The server binds to loopback only, serves only the indexed source images and
bundled interface files, and requires a per-process random token on writes.
Do not expose the port through public tunnels or reverse proxies.
Progress is an operator's saved intent, not cryptographic proof of identity
or of scan accuracy. Review remains your responsibility.
