# Persistent lexical stage, after punctuation repair

This stage implements scan-verified lexical repairs (word-boundary insertion and character substitution, deletion or insertion) plus a human-approved cumulative vocabulary. The existing punctuation-only executor remains unchanged.

## Authority and process boundaries

Source scan pixels establish what is printed. Raw Paddle observations and derived Markdown are fallible. A probe detects unrecognized tokens; a frequency inventory and segmentation model provide hypotheses; session 1 Codex makes *per-occurrence proposals* using scans; a separate session 2 Codex reviews those proposals using scans; the human accepts the reviewed decisions and separately authors any global lexicon admissions; the lexical executor validates and applies exactly the approved changes.

The existence of a plausible word or recurring token is NOT evidence that OCR is wrong. In particular, ambiguous Greek/Latin glyphs and unusual source typography deserve caution. A dictionary entry means only that the form should not produce a dictionary-rejection finding; it does NOT certify each occurrence in future scans.

Two distinct authorizations: review.status = "approved" on a reviewed finding enables the *specific proposed replacement*, once the human explicitly runs the executor. A **separate human-authored approval file** with approved = true authorizes persistent lexicon admission of an *unrepaired observed occurrence*. Codex suggestions are never admissions.

The persistent lexicon is JSON: lexicon.json is an empty starting template in the tools repo. It may instead live under a shared, long-lived path outside the per-book workspaces. Each entry carries the exact word, a human note, and an approval record linking it to a finding, the unchanged full probe report hash and scan-directory hash. NFC and casefold are used only in membership checks; the OCR text is never normalized. The lexicon file's exact SHA-256 is recorded by probes and required by execution. Changes become visible only when a subsequent probe explicitly reads the updated file.

## Commands for one book

The earlier Paddle and punctuation phases proceed as documented in process.md. Start with an existing **verified whitespace stage** called whitespace-repaired, a scans directory, a shared lexicon, and the Normalize tools directory. Before the next commands, ensure the whitespace executor has completed successfully.

1. Full lexical baseline:
    python /tooling/normalize_probe.py --scans scans --paddle whitespace-repaired --lexicon /shared/lexicon.json --out review/probe2.json

2. Extract only unrecognized_token findings (also retaining combined lower_upper triggers), their exact spans/contexts and frequency inventory:
    python /tooling/extract_lexical.py --report review/probe2.json --out review/lexical-extracted.json

3. Optional **deterministic hint sidecar**; it never edits Markdown or approves a proposal:
    python /tooling/suggest_segments.py --report review/lexical-extracted.json --paddle whitespace-repaired --lexicon /shared/lexicon.json --out review/segmentation-hints.json

4. Session 1 reads codex/lexical-proposer.md and ONLY source images, extracted report and optional hints. It produces a new lexical-proposals.json. Preserve extracted report unchanged.
5. A SEPARATE session 2 reads codex/lexical-verifier.md and ONLY the frozen proposals plus source images. It produces lexical-reviewed.json, changing only review.status/note. Preserve proposals unchanged.
6. The human inspects the changes, and if desired, authors the human-lexicon-approvals.json file described below. It cannot be produced by either Codex session. The human invokes dry run first and then chooses whether to execute.

Dry-run:
    python /tooling/execute_lexical_repairs.py --baseline review/probe2.json --proposals review/lexical-proposals.json --reviewed review/lexical-reviewed.json --paddle whitespace-repaired --lexicon /shared/lexicon.json --lexicon-approvals review/human-lexicon-approvals.json --out lexical-repaired

Execute: same command with --execute. Without admissions, omit the entire --lexicon-approvals argument pair.

7. Fresh subsequent probe:
    python /tooling/normalize_probe.py --scans scans --paddle lexical-repaired --lexicon /shared/lexicon.json --out review/probe3.json

Full probe, extracted inventory, proposer report, independent verifier report, human approvals, previous output directories, and stage execution ledgers must be preserved as **distinct** artifacts. The new executor forbids applying old offsets to its own derived output.

## Human approvals schema

The human creates a JSON object with fields:
- format: "human_lexicon_approvals_v1"
- source_report_sha256: SHA-256 of the original, untouched probe2.json file bytes
- lexicon_sha256: SHA-256 of the lexicon file bytes from the probe run
- entries: array of objects with word, finding_id, approved (Boolean true), and note (nonempty human explanation).

Only words actually observed in an unrepaired unrecognized_token finding from that exact probe can be admitted. A separately approved *repair of that same occurrence* prohibits admitting its original spelling from that occurrence. Duplicate words, invented candidates, nontrue approvals, changed lexicon versions, or stale reports are rejected. Without a human approvals file, no words are admitted. Admission is human-authorized; no software can cryptographically prove who typed the file.

## Deterministic segmentation policy

The optional sidecar builds a recognized-word frequency table from the previous derived Markdown, excluding embedded markup; valid segment pieces must be recognized by English Hunspell OR the custom human-approved lexicon. It ranks known-word-only partitions deterministically using in-book occurrence frequencies. The scoring is a heuristic and does not establish source correctness. A complete word already recognized by the lexicon cannot be segmented just for being unrecognized by English spellcheck. The sidecar is NOT consumed by the executor. Session 1 must inspect printed pixels before endorsing any suggestion.

## Mechanical and provenance invariants

The lexical executor validates the full source directory hash, the earlier whitespace execution provenance and original probe's comparison metadata. It reconstructs exactly the extracted report from the full baseline and checks that Codex session 1 changed only proposal slots. Then it checks that the independent verifier modified only status/note fields. Only "approved" proposals having direct visual-evidence notes become source-byte-verified, nonoverlapping replacements; proposals are applied right-to-left, to a NEW copied artifact directory. No scan, raw Paddle input, original whitespace derivative, previous ledger, JSON or asset is modified.

It writes lexical_execution_report.json: exact original/replacement bytes and offsets, original/final page hashes, input directory and scan hashes, baseline/proposer/verifier hashes, and old/intended lexicon hashes.

Probe 3 reverses the actually executed lexical replacements in memory and validates the entire reconstructed whitespace-stage snapshot. It then reverses the whitespace repairs in memory and validates the raw Paddle snapshot. Only executed and verified differences are exempted from JSON–Markdown mismatch findings; unrelated differences remain. The current Markdown is always the basis for new findings and offsets. This version composes exactly one lexical stage after exactly one punctuation stage, not an arbitrary number of repair ledgers.

## Two-output publication and recovery

A derivative directory and a shared lexicon file cannot be committed as one universally atomic filesystem operation. The executor first stages and publishes the entire derivative directory INCLUDING a durable record of the intended vocabulary transition, and only afterward atomically replaces the lexicon file (after checking its old hash). If lexicon replacement fails, the directory is already published but the lexicon remains unchanged. The executor exits in error and instructs the operator to rerun with --execute --resume-lexicon. A stale or competing lexicon change is never silently overwritten.

Do not run independent writers against a shared lexicon concurrently. Stale hashes detect many errors, but this mechanism is not a distributed lock or an identity/authorship verification system. Keep persistent lexicon changes in version control if practical.

## Validation

    python -m unittest discover -s tests -v

The regression suite uses a miniature book to test the entire prior punctuation workflow followed by the lexical stage, distinct Codex report authority, human admission file, exact replacements, reprobe and chained mismatch provenance. It also tests stale inputs, tampering and segmentation coupling.
