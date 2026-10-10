# Persistent lexical stage, after punctuation repair

This stage implements scan-verified lexical repairs (word-boundary insertion and character substitution, deletion or insertion) plus a human-approved cumulative vocabulary. The existing punctuation-only executor remains unchanged.

## Authority and process boundaries

Source scan pixels establish what is printed. Raw Paddle observations and derived Markdown are fallible. A probe detects unrecognized tokens; a frequency inventory and segmentation model provide hypotheses; session 1 Codex makes *per-occurrence proposals* using scans; a separate session 2 Codex reviews those proposals using scans; the human accepts the reviewed decisions and separately authors any global lexicon admissions; the lexical executor validates and applies exactly the approved changes.

The existence of a plausible word or recurring token is NOT evidence that OCR is wrong. In particular, ambiguous Greek/Latin glyphs and unusual source typography deserve caution. A dictionary entry means only that the form should not produce a dictionary-rejection finding; it does NOT certify each occurrence in future scans.

Two distinct authorizations: review.status = "approved" on a reviewed finding enables the *specific proposed replacement*, once the human explicitly runs the executor. A **separate human-authored approval file** with approved = true authorizes persistent lexicon admission of an *unrepaired observed occurrence*. Codex suggestions are never admissions.

Baseline recognition checks en_US, de_DE, and fr_FR Hunspell (with each
locale's own affix rules), then the separate human-approved lexicon. Every
pair is mandatory; if one is missing the probe stops. The probe records all
six file hashes under inputs.dictionary_sha256[language], preserving the
conditions under which a candidate was detected. A matching word does NOT
prove which language it belongs to or that the OCR matches the scan;
cross-language recognition can hide some OCR mistakes. Greek and historical
spellings can remain unknown.

The persistent lexicon is JSON: lexicon.json is an empty starting template in the tools repo. It may instead live under a shared, long-lived path outside the per-book workspaces. Each entry carries the exact word, a human note, and an approval record linking it to a finding, the unchanged full probe report hash and scan-directory hash. NFC and casefold are used only in membership checks; the OCR text is never normalized. The lexicon file's exact SHA-256 is recorded by probes and required by execution. Changes become visible only when a subsequent probe explicitly reads the updated file.

## Commands for one book

The earlier Paddle and punctuation phases proceed as documented in
process.md. On Ubuntu install:

    sudo apt-get install libhunspell-1.7-0 hunspell-en-us hunspell-de-de hunspell-fr-classical

The default dictionary directory is /usr/share/hunspell. If using another
directory, pass --hunspell-dir to both normalize_probe.py and
suggest_segments.py so their snapshot hashes match.
 Start with an existing **verified whitespace stage** called whitespace-repaired, a scans directory, a shared lexicon, and the Normalize tools directory. Before the next commands, ensure the whitespace executor has completed successfully.

1. Full lexical baseline:
    python /tooling/normalize_probe.py --scans scans --paddle whitespace-repaired --lexicon /shared/lexicon.json --out review/probe2.json

2. Extract only unrecognized_token findings (also retaining combined lower_upper triggers), their exact spans/contexts and frequency inventory:
    python /tooling/extract_lexical.py --report review/probe2.json --out review/lexical-extracted.json

3. Optional **deterministic hint sidecar**; it never edits Markdown or approves a proposal:
    python /tooling/suggest_segments.py --report review/lexical-extracted.json --paddle whitespace-repaired --lexicon /shared/lexicon.json --out review/segmentation-hints.json

4. Session 1 reads codex/lexical-proposer.md and ONLY source images, extracted report and optional hints. It produces a new lexical-proposals.json. Preserve extracted report unchanged.
5. A SEPARATE session 2 reads codex/lexical-verifier.md and ONLY the frozen proposals plus source images. It produces lexical-reviewed.json, changing only review.status/note. Preserve proposals unchanged.
6. **Human lexicon admission:** Launch the [local scan-backed reviewer](human-lexicon-review.md) with the completed \`lexical-reviewed.json\` and the frozen Probe 2/proposal reports. Group repeated vocabulary, inspect source images and explicitly Accept/Reject/Skip lexical types. The application saves review progress and **generates** the executor-compatible \`human-lexicon-approvals.json\` without any hand-authored JSON. Neither Codex review session can admit vocabulary. The human then dry-runs the executor and chooses whether to execute.

Dry-run:
    python /tooling/execute_lexical_repairs.py --baseline review/probe2.json --proposals review/lexical-proposals.json --reviewed review/lexical-reviewed.json --paddle whitespace-repaired --scans scans --lexicon /shared/lexicon.json --lexicon-approvals review/human-lexicon-approvals.json --out lexical-repaired

Execute: same command with --execute. Without admissions, omit the entire --lexicon-approvals argument pair.

7. Fresh subsequent probe:
    python /tooling/normalize_probe.py --scans scans --paddle lexical-repaired --lexicon /shared/lexicon.json --out review/probe3.json

Full probe, extracted inventory, proposer report, independent verifier report, human approvals, previous output directories, and stage execution ledgers must be preserved as **distinct** artifacts. The new executor forbids applying old offsets to its own derived output.

## Human approvals schema

The **local human reviewer** in [human-lexicon-review.md](human-lexicon-review.md) creates this JSON automatically. Its format is:
- format: "human_lexicon_approvals_v1"
- source_report_sha256: SHA-256 of the original, untouched probe2.json file bytes
- lexicon_sha256: SHA-256 of the lexicon file bytes from the probe run
- entries: array of objects with word, finding_id, approved (Boolean true), and note (nonempty human explanation).

Only words actually observed in an unrepaired unrecognized_token finding from that exact probe can be admitted. A separately approved *repair of that same occurrence* prohibits admitting its original spelling from that occurrence. Duplicate words, invented candidates, nontrue approvals, changed lexicon versions, or stale reports are rejected. Without a human approvals file, no words are admitted. Admission is human-authorized; no software can cryptographically prove who typed the file.

## Deterministic segmentation policy

The optional sidecar builds a recognized-word frequency table from the previous derived Markdown, excluding embedded markup; valid segment pieces must be recognized by English, German, or French Hunspell OR the custom human-approved lexicon. It ranks known-word-only partitions deterministically using in-book occurrence frequencies. The scoring is a heuristic and does not establish source correctness. A complete word already recognized by any dictionary or the custom lexicon cannot be segmented just because another dictionary rejects it. The sidecar is NOT consumed by the executor. Session 1 must inspect printed pixels before endorsing any suggestion.

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


## Cutover from the English-only pilot

Keep the original source scans, Paddle output, validated whitespace-derived
directory and its execution ledger unchanged. **Neither OCR nor punctuation
repairs need to be rerun.** Generate a new Probe 2 from the existing
whitespace-repaired directory with the installed three-language dictionaries,
the same persistent lexicon snapshot and a new output filename.

The previous English-only Probe 2, lexical extraction, Codex proposer/verifier
outputs and human review progress belong to the OLD candidate population and
must be archived as immutable history rather than fed into the new lexical
executor. Re-extract the lexical findings, regenerate optional segmentation
hints, repeat the two visual Codex sessions, and begin a fresh human lexicon
review for the newly generated report. Do not copy earlier approvals across
changed finding populations or hashes. The previous review is still useful as
empirical comparison evidence, but cannot authorize new snapshot operations.

Dictionary additions affect lexical *recognition*, not existing repaired
Markdown/JSON. They do not import French or German terms into lexicon.json.
