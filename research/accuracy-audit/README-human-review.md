# Human geometry review

Open [`review/index.html`](review/index.html) in a local browser. The corpus has one entry per nonblank page side. Each entry places the exact preprocessed image supplied to current production geometry beside an overlay. Open either image in a new tab to zoom. The source image is copied byte-for-byte from the current preprocessing output; the overlay only adds visible marks. Existing source colors are preserved.

The authoritative editable record is [`human-review.json`](human-review.json). Review each page visually:

1. Compare the overlay with the source scan.
2. If every production line and token membership is correct, set `review_status` to `verified_no_exceptions`.
3. Otherwise set `review_status` to `verified_with_exceptions` and add only the exceptional line/token relations.
4. Save the JSON. Never treat OCR spelling as a geometry error.

Every page starts `unreviewed`. The generator does not mark human review complete. The scorer refuses to finalize while any required page is unreviewed.

## Stable identities

Use `fixture_id`, `side`, `physical_line_id`, `token_id`, `source_row`, and `bbox_px` from each page record. OCR `text_locator` is for display/search only; duplicate text is expected. The full token identity index is included in each page record so exceptions can refer to tokens unambiguously.

`human_group_id` is a review-local name for a visible line when production did not represent that line, or when a produced line contains multiple visible lines. Reuse the same ID for every token in that one visible line. It does not need to resemble a production line ID.

## Exception records

All exception records have a `type`. `token_ids` always means stable IDs, never OCR text. A page may have multiple non-overlapping exceptions; do not list one token in more than one exception.

### False merge

One production line contains tokens from multiple visible lines. Record every member of that production line and partition the tokens into two or more human groups:

```json
{
  "type": "false_merge",
  "production_line_id": "line-0012",
  "token_ids": ["token-0041", "token-0042", "token-0043"],
  "human_groups": [
    {"human_group_id": "review-line-a", "token_ids": ["token-0041", "token-0042"]},
    {"human_group_id": "review-line-b", "token_ids": ["token-0043"]}
  ]
}
```

### False split

Multiple production lines form one visible line. Record all affected production lines, all their resolved token IDs, and one human group:

```json
{
  "type": "false_split",
  "production_line_ids": ["line-0012", "line-0013"],
  "token_ids": ["token-0041", "token-0042", "token-0043"],
  "human_group_id": "review-line-a"
}
```

### Wrong membership

A resolved token belongs to another visible line. `intended_human_group_id` must match the group ID used for the other line (default groups use the production `physical_line_id`):

```json
{
  "type": "wrong_membership",
  "production_line_id": "line-0012",
  "token_ids": ["token-0043"],
  "intended_human_group_id": "line-0013"
}
```

### Wrong order

Membership is right but within-line physical order is wrong. State the complete expected token sequence for that production line. This is reported separately from membership accuracy:

```json
{
  "type": "wrong_order",
  "production_line_id": "line-0012",
  "token_ids": ["token-0041", "token-0042"],
  "ordered_token_ids": ["token-0042", "token-0041"]
}
```

### Residual expected membership

For each residual token, record the visible line group it belongs to. The overlay marks residuals in magenta; its `R#` labels correspond to the residual table. Candidate line IDs are retained in the ledger:

```json
{
  "type": "residual_expected_membership",
  "token_ids": ["token-0216"],
  "human_group_id": "line-0046"
}
```

Record one event for every residual token. The scorer requires all residuals to have a human answer before it finalizes. This event records the human answer without changing production output or resolved-token accuracy.

### Other geometry error

Use only for a visible geometry error that the other types cannot express. Record affected stable token IDs, the production line ID(s) where applicable, and a short `explanation`.

The ledger is data, not executable code. After human review, calculate metrics with:

```sh
.venv/bin/python research/accuracy-audit/human_review.py score
```

This emits metrics only after every nonblank page-side record has a supported verified state. `coverage` is resolved-token coverage. It is not correctness. The scorer does not consult `.raw.md`, `.normalized.md`, or `*.expected.json` for answers.

## What the scorer measures

Resolved-token membership is strict partition equality. A resolved token gets credit only if its complete produced line contains exactly the resolved tokens in its human line group. Thus a false merge makes the tokens in the merged production line incorrect, and a false split makes the tokens across those production lines incorrect. A wrong-membership event changes the human group for the identified token; the resulting partition comparison determines all affected resolved assignments. Residual tokens do not enter resolved accuracy or pairwise scores.

Pairwise precision compares token pairs production grouped together with pairs the reviewer says share a visible line; false merges add false-positive pairs. Pairwise recall compares human same-line pairs with pairs production grouped together; false splits add false-negative pairs. Precision is `null` when production predicts no same-line pairs, and recall is `null` when the human review contains no same-line pairs.

Exact physical-line matching compares the complete set of admitted token identities in each human line group—including human-assigned residuals—to a produced line's resolved token set. A line with a residual token cannot be an exact production match. Wrong-order and `other_geometry_error` lines are excluded from exact matches and shown in the other-incorrect-groups count. Within-line order has its own metric; it does not change membership accuracy. `other_geometry_error` only affects the membership score when its recorded correction changes line membership through one of the explicit membership exception types.

The review burden counts each exception record as one review event, not each token. Residual burden counts one residual event per human-assigned residual token. Coverage remains a separate abstention/availability measure.
