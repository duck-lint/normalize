# Post-bulk lexical corpus analysis

This read-only diagnostic is designed for the **pause before exhaustive human
lexicon review**. For each book, complete the deterministic Probe 2, the Codex
lexical proposal batch and independent verification batch, then use Review UI
only for the available human-confirmed **bulk exclusions**. Save the Review UI
progress JSON and stop: you do **not** have to decide hundreds of remaining
forms before using this tool.

The question is not merely *how many tokens are unrecognized?* It is: which
recurring sources of review burden might be mitigated by better upstream
recognition, tokenization or OCR routing, and which cases instead need a
better-targeted downstream review step?

## Inputs and snapshot boundary

For **each book**, the tool needs:

1. The **same frozen Probe 2** that generated the lexical batch.
2. The full joined **lexical proposals** JSON.
3. The full joined **independent verification** JSON.
4. The Review UI's **autosaved progress** JSON **after** any bulk exclusions
   you chose to make. This is *not* the exported execution approvals file.

You don't need the original scan directories, edited Markdown, executed
lexical repairs or the mutable current lexicon. The tool checks the complete
proposer/verifier handoff contract, and requires the saved progress hashes for
the **exact bytes** of all three frozen artifacts, plus the probe's recorded
scans and lexicon hashes. A regenerated Probe 2, even with improved
dictionaries, is a **different** review baseline. Its old progress cannot be
attached by matching tokens or IDs.

Place an input manifest anywhere convenient, for example
`analysis/books.json`:

```json
{
  "books": [
    {
      "name": "The First Philosophers",
      "probe2": "../output/The First Philosophers/probes/probe2.json",
      "proposals": "../output/The First Philosophers/lexical_reports/lexical-proposals.json",
      "reviewed": "../output/The First Philosophers/lexical_reports/lexical-reviewed.json",
      "progress": "../output/The First Philosophers/lexical_reports/human-lexicon-approvals.progress.json"
    },
    {
      "name": "About Vision & Color",
      "probe2": "../output/About Vision & Color/probes/probe2.json",
      "proposals": "../output/About Vision & Color/lexical_reports/lexical-proposals.json",
      "reviewed": "../output/About Vision & Color/lexical_reports/lexical-reviewed.json",
      "progress": "../output/About Vision & Color/lexical_reports/human-lexicon-approvals.progress.json"
    }
  ]
}
```

*Paths above are illustrative.* All paths resolve relative to the manifest's
directory (including `..`); substitute real artifact names and directory
depths. Each book needs a unique name and four distinct input paths.

Run from the tooling checkout:

```bash
python analyze_lexical_corpus.py --manifest analysis/books.json \
  --out analysis/post-bulk-corpus.json
```

If a manifest points at an older lexical report or newer re-probe, diagnose
**all books individually** before creating output:

```bash
python analyze_lexical_corpus.py --manifest analysis/books.json --check-only
```

This prints a PASS/FAIL line per book, expected Probe 2 lexical finding counts,
proposal counts, sample missing/extra IDs, and saved progress snapshot hash
mismatches. A nonzero exit status means at least one book failed; no output
file is written. **Do not** filter/rewrite frozen agent findings to match
a new probe. Use the original exact probe snapshot for that lexical batch
or rerun lexical proposal/verification and bulk triage against the new probe.

Omit `--out` to print JSON to stdout. Output files are **new-only**; the
analyzer refuses an existing output or any input path as output. Use
`--top 100 --examples 5` to enlarge the capped ranked lists and per-form
occurrence evidence. All counts use the full corpus, not the ranked-list cap.

## What the output means

`summary` and `books` record **book-form counts**, **corpus-distinct
forms**, **occurrence counts**, post-bulk *pending* forms and occurrences, and
per-occurrence effective repair states. The latter incorporates human repair
overrides without editing the verifier. All input SHA-256 hashes are recorded
for each book.

`form_dispositions` and `occurrence_dispositions` keep separate buckets:

- `pending_human_vocabulary_review`: no saved form-level decision; **the
  remaining active Review UI queue**, even if some occurrences have already
  been verified for repair.
- `bulk_excluded_all_repair_verified`: a human bulk exclusion whose **every
  occurrence** has an independently approved or human-approved replacement.
  This is an exclusion from *vocabulary admission*, **not** evidence that
  OCR output was already corrected.
- `bulk_excluded_source_faithful_nonlexical`: every occurrence has the
  verifier's explicit source-faithful nonlexical annotation and was excluded
  from vocabulary admission by the human.
- `human_accepted_vocabulary`: human vocabulary-admission decision; does
  not imply every occurrence is faithfully transcribed.
- `human_rejected_vocabulary_reason_unclassified`: any ordinary rejection
  not covered by the two verified bulk reasons. **Never count this as an OCR
  error simply because it was rejected.**

`repair_states` separately describe individual occurrences:
`codex_verified_repair`, `human_approved_repair`,
`human_rejected_repair`, `proposed_not_verified`,
`source_faithful_nonlexical`, or `no_verified_repair`.

### Cross-book investigation

- `top_pending_forms`: what actually remains for triage after bulk review.
- `recurring_cross_book_forms`: forms shared by two or more books, including
  mixed decisions and already bulk-excluded cases.
- `top_bulk_excluded_forms`: why apparently removed forms still matter to
  identifying repeatable upstream causes.
- `signals_by_disposition`: counts by **conservative clues**, not verdicts.
  Includes contraction-like spellings (such as `didnt`), adjacent
  apostrophes, mixed Greek/Latin script, Greek script, numeric/letter mixtures,
  Roman-numeral-like words, and forms with no obvious clue.
- `verified_repair_pairs` and `verified_repair_edit_operations`: actual
  **independently or human approved** proposal patterns that might warrant
  source-inspected upstream experiments. Human-rejected or unverified
  proposals are never counted as verified repair pairs.

Each ranked form includes its occurrence count, participating books,
dispositions, repair states, and limited **original finding IDs and reviewer
notes** for targeted scan follow-up. All signal labels are **hypotheses**.
For example, `didnt` being contraction-like does **not** prove its apostrophe
was lost, nor does an adjacent apostrophe prove a tokenizer bug. Mixed scripts
do not by themselves prove a bad transcription.

The diagnostics deliberately **do not** authorize correction, rewrite OCR,
change the persistent lexicon, infer a "correct" string, bypass scan review,
re-run Codex, or decide what is genuinely an OCR error from a rejected
vocabulary form. They help choose the *next* experiment.

## Suggested reading order

First inspect pending-form concentration and cross-book recurrence. Then look
at bulk-excluded categories and verified replacement pairs for patterns the
current workflow already handled one occurrence at a time. Review the
examples against source scans before proposing a new deterministic detector
or an additional targeted Codex stage. What remains unclassified is evidence
of *missing classification*, not proof that more automation is possible.

For technical context see [lexical stage](lexical-stage.md) and
[human review](human-lexicon-review.md).
