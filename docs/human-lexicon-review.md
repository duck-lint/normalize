# Human vocabulary review app

This is the separate **human** handoff for two independent judgments:
per-occurrence source-scan OCR repairs and global lexicon entries.
Both can be exported in one hash-bound human approvals JSON. No frozen Codex
proposal or verifier report is modified.
It runs *after* the two Codex sessions and *before* lexical execution.
During the multilingual dictionary cutover, the new Probe 2 has different
candidate provenance and potentially different findings. Archive old English-only
reports/progress, regenerate the lexical extraction and **repeat both Codex
sessions**. Existing frozen agent outputs are reusable only when the underlying
probe and dictionary hashes stay unchanged.

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
### Live scope metrics and faster navigation

The left sidebar now reports **the counts within your active search/filter
combination**, not just the whole book:

- **Showing X / Y lexical forms**: distinct canonical word groups in the
  filtered list versus the total groups in the frozen review report.
- **X / Y occurrences**: actual source findings represented by those groups.
  A single form can represent many occurrences, so these figures differ.
- **Pending / Accepted / Rejected forms**: human *lexicon admission* decisions
  in the filtered list, not occurrence repair decisions.
- **Proposed repair occurrences** versus **Approved repair occurrences**:
  proposed replacements can be rejected/unverified, so these numbers are not
  synonymous. Both count source occurrences, not unique words.
- **Admission-eligible forms**: types with at least one still-unrepaired
  occurrence that could support a human lexicon admission if the source scan
  confirms it, excluding already-known lexicon entries.

These metrics, together with the bulk rejection button's eligible-form count,
refresh immediately when you change a filter, search, save a decision or
complete a batch. The main header continues to show *whole-book* progress,
so there is always a clear distinction between global totals and current scope.

Use **Clear filters** to remove search/status/repair/evidence constraints while
retaining your preferred sort. The current-position indicator shows where the
selected word sits in the filtered forms; arrow buttons or Up/Down navigate
within that list. **Next pending** (or **N** when not typing) jumps to the next
undecided word that matches the current filters, wrapping at the end.

When deciding a word in the **Pending** view, it disappears from that view.
The reviewer automatically advances to the next visible word near that
position, rather than showing a now-hidden entry or returning to the start.
When a filter matches no forms, the interface shows an empty-result message.
All operations remain local and read-only except for the existing explicit
progress/approval writes; counts, sorting and navigation never alter
source scans, OCR proposals, or vocabulary admissions.

The right pane displays original scan pixels, the selected occurrence and its
exact UTF-8-aligned OCR context. The context is a locating hint only.

Select any occurrence and inspect the original scan before admission. Use the
occurrence buttons to compare examples; entries for which Codex proposed a
character/word-boundary repair are visibly marked and **cannot support
admission**. If the same spelling has both repaired and unrepaired occurrences,
a warning appears: only an *unrepaired occurrence* may support an admission.

### Source-faithful printed irregularities: exclude from this lexicon batch

The existing independent lexical verifier now supports an *optional*, strict
tag in its existing review.note for no-repair findings:

    SOURCE_FAITHFUL_NONLEXICAL_VERIFIED: Scan [page/location] prints "[observed]" exactly; this is a localized printed irregularity, not reusable vocabulary.

The prefix is an annotation of a **conservative lexical triage conclusion**,
not proof of universal spelling correctness. The verifier must inspect each
scan occurrence and supply concrete visual evidence in the remainder of its
note. Only apply it when (a) no OCR repair is warranted because the print and
observed bytes match, and (b) the observed form is clearly a printed
irregularity that should *not* be added as a general dictionary word.
Ambiguous cases, legitimate historical/British spelling such as "skilful",
Latin, Greek, foreign vocabulary, technical terms and proper names must
remain for individual lexicon review. A scan match alone is not enough.
A verifier note is not a human vocabulary decision.

No extra field, new report schema, new Codex pass or executor change is needed:
the verifier still leaves review.status null on no-proposal findings. The
current app reads only the frozen reviewed report; it does NOT modify verifier
notes. In the app, use the independent **Source** filter (any / all / mixed /
none) and inspect marked occurrences and verifier evidence. The scope panel
shows marked occurrence counts separately from verified OCR repairs.

For repeated lexical forms, the **Reject source-verified printed
irregularities** batch action includes a form only when **every** occurrence
has a qualifying verifier note, no occurrence has a repair proposal,
the form is not already known, and the human has not previously made a
decision. It previews the exact filtered list and requires explicit
acknowledgment; the server rechecks all keys and source hashes before saving
an atomic batch of ordinary human "rejected" decisions.

This exclusion simply completes the *current human vocabulary-admission
queue*. It does NOT censor the source text, approve or execute an OCR repair,
alter frozen lexical reports, permanently blacklist a spelling, or add a word
to the persistent lexicon. A word with mixed source evidence remains in
individual review.

**Using this with an existing Codex pass:** you may reuse the unchanged
lexical-proposals.json and rerun **only the independent verifier** under the
revised verifier prompt, writing a new lexical-reviewed.json. Changing its
bytes changes the review snapshot hash. Keep the previous review report and
progress as immutable history; launch a fresh human review with a new
--progress and --out. Do not silently transplant previous decisions or edit
the frozen reviewed JSON by hand. Nothing requires rerunning Probe 2, OCR,
the whitespace executor, or the lexical proposer.

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

## Human OCR repair overrides (selected occurrence only)

The source scan is authoritative. At each occurrence the human reviewer may
**create or replace an OCR proposition and approve it**, reject a Codex
proposal, or clear the human override to restore the frozen Codex decision.
An empty replacement deliberately deletes the observed span. Approving or
rejecting an OCR repair requires a nonempty direct-scan evidence note and an
explicit inspection acknowledgment. These are **not vocabulary admissions**.

Occurrence-level human decisions are saved alongside vocabulary decisions in
the same progress JSON, and exported as `repairs` in
`human_lexical_approvals_v2`. Existing `human_lexicon_approvals_v1`
files remain supported for lexicon-only execution, and older progress files
load with no occurrence overrides. The new combined JSON includes hashes of
Probe 2, frozen Codex proposals, frozen independent verification, scans and
the original lexicon; the executor rejects stale or altered sources.

The existing `--lexicon-approvals` argument accepts the combined approval
file. The executor first validates untouched Codex handoffs, then applies
explicit human overrides to an **in-memory** effective review, checks original
byte spans and collisions, and produces the normal new Markdown derivative.
The execution ledger records human decisions and labels the authority for
each executed repair. Rejected Codex repairs are suppressed; untouched
occurrences retain their independent verifier decisions. A human repair
override may make a previously unrepaired occurrence ineligible for vocabulary
admission, while rejecting a Codex proposition can make it eligible if its
observed spelling is a valid word. Existing human vocabulary approvals must
remain supported by an eligible unrepaired occurrence.

Neither saving progress nor exporting the approval file changes OCR text or
the persistent lexicon. The human still dry-runs the executor and explicitly
chooses when to execute. No OCR, probe, agent review, or join must be rerun.
Stop the old local reviewer and launch the updated UI against the **same**
frozen reports and scans; existing v1 progress is retained.

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
