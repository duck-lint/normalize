# Normalize: punctuation-space repairs

The current process inserts ASCII spaces after punctuation. There is one review
handoff and one executor; other repairs are out of scope.

1. `paddle_scan.py` processes page scans into raw PaddleOCR JSON and Markdown.
2. `normalize_probe.py` reads that output and writes the full candidate report.
   It supplies deterministic space proposals for `punctuation_letter`
   (`,;:!?` followed by an ASCII letter) and `period_capital` (a period followed
   by an ASCII capital). Lexical and structural candidates can appear in this
   full report but have no repair proposals. Punctuation findings stay separate
   from overlapping lexical findings so extraction does not lose them.
3. `extract_whitespace.py` copies findings whose nonempty trigger set contains
   only `punctuation_letter` and/or `period_capital` into report two. Each finding
   is copied intact, including its proposal and `review` object. The extractor
   does not calculate, alter, approve, or repair anything.
4. Codex runs in a **book workspace repository**, using the
   [review prompt](codex/processing-prompts.md). It compares proposals to scans,
   sets accepted findings to `review.status: "approved"` in report two, leaves
   exception statuses unchanged, and optionally adds `review.note`. It writes
   complete copies of non-approved findings into report three.
5. The human runs `execute_repairs.py` over the edited report two. Only exact
   `"approved"` statuses enable insertion. Report three is for exceptions, not
   execution. There is no separate authorization or merge-back stage.

## Files and commands

Keep Normalize scripts in a tooling checkout. Run these commands from a separate
book workspace. Replace `/path/to/normalize` with the tooling checkout path.
Page image stems must match their Paddle `.md` and `_res.json` stems.

PaddleOCR and its matching PaddlePaddle runtime must already be installed for
step one. The probe requires `libhunspell-1.7` and the English dictionary files
`/usr/share/hunspell/en_US.aff` and `en_US.dic`. On Ubuntu these are supplied by
`libhunspell-1.7-0` and `hunspell-en-us`. Extraction and execution use the Python
standard library only and do not instantiate Hunspell or PaddleOCR.

```bash
python /path/to/normalize/paddle_scan.py --images scans --out paddle --device gpu:0
```

Create ZIPs once, preserving relative paths that Codex can also use in the
extracted `scans/` and `paddle/` directories. Probe and executor both use the same
unchanged Paddle ZIP.

```bash
python -m zipfile -c scans.zip scans/
python -m zipfile -c paddle.zip paddle/
python /path/to/normalize/normalize_probe.py \
  --scans scans.zip --paddle paddle.zip --out review/probe.json
python /path/to/normalize/extract_whitespace.py \
  --report review/probe.json --out review/whitespace.json
```

These ZIP commands retain the `scans/` and `paddle/` prefixes. Accordingly,
resolve the report's paths relative to the book workspace root when giving
Codex the prompt. For ZIPs without those prefixes, use the appropriate extracted
artifact directories as the roots instead. `review/probe.json` is report one and
stays untouched. Report two initially looks like this (illustrative values):

```json
{
  "inputs": {"paddle_zip_sha256": "...", "source_zip_sha256": "...", "dictionary_sha256": {}},
  "findings": [
    {
      "id": "page001:punctuation_letter:11",
      "page": "page001",
      "rule": "punctuation_letter",
      "triggers": ["punctuation_letter"],
      "source_image": "scans/page001.jpg",
      "paddle_markdown": "paddle/page001.md",
      "paddle_json": "paddle/page001_res.json",
      "source_md_sha256": "...",
      "start_byte": 11,
      "end_byte": 16,
      "json_block_id": null,
      "observed": ",word",
      "proposed": ", word",
      "proposal_source": "deterministic_whitespace",
      "evidence": null,
      "review": {"status": null, "note": null}
    }
  ]
}
```

Give Codex the prompt and report two in the book workspace. For `U.S.A`, the probe
will propose spaces, the extractor will carry that finding unchanged, and Codex
should leave its status `null` and copy it into
`review/whitespace_exceptions.json`. Accepted proposals get `"approved"` in report
two. Codex never edits the raw text or runs the executor.

Then the human can preview or execute:

```bash
python /path/to/normalize/execute_repairs.py \
  --baseline review/probe.json --report review/whitespace.json \
  --paddle paddle.zip --out repaired
python /path/to/normalize/execute_repairs.py \
  --baseline review/probe.json --report review/whitespace.json \
  --paddle paddle.zip --out repaired --execute
```

The baseline is used only to verify that report two still contains the exact
copied findings, with changes limited to status/note. It is never edited or used
as the execution report. The executor verifies original hashes, exact UTF-8 byte
spans, deterministic space-only proposals, and non-overlapping approved ranges
before writing. It applies proposals exactly, supports no replacement overrides,
and preserves raw scans, Paddle artifacts, and reports. Output contains all
per-page Markdown (unchanged pages copied verbatim) and an execution log.
Existing output paths are not overwritten.

## Validation

```bash
python -m unittest discover -s tests -v
```

Tests cover the actual ZIP → probe → copy → status edits → execution handoff,
including abbreviations, lexical overlap, Unicode offsets, unchanged pages,
non-approved statuses, and refusal of unauthorized report changes.
