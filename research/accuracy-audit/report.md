# Normalize current accuracy audit

Source revision: `0ad8944f376059454da96a321f479218363535e1`
Audit evaluator: `accuracy-audit-v1` (`ec188d8653efd637ae81d269b6a59badaad97d5a10da22750c1e67bb4bf87863`)

## A. Oracle coverage

The six `expected.json` files contain **186 explicit assertion units** under the documented atomicity rules. **7** are scoreable now: six exact spread-order fields and one exact blank-side field. **154** require output stages that do not exist yet; **25** are outside this audit scope. No fuzzy or semantic structural matching is used.

| Oracle class | Count | Classification |
|---|---:|---|
| expected sequence records | 133 | not_yet_produced_by_pipeline |
| page-furniture records | 12 | not_yet_produced_by_pipeline |
| dialogue-count fields | 3 | not_yet_produced_by_pipeline |
| printed-label fields | 6 | not_yet_produced_by_pipeline |
| spread-order fields | 6 | scoreable_now |
| blank-page fields | 1 | scoreable_now |
| annotation-noise records | 4 | out_of_current_slice_scope |
| critical narrative assertions | 21 | out_of_current_slice_scope |

The schema’s identity/provenance fields are recorded as metadata, not counted as accuracy decisions. The scoreable list fields use exact whole-list equality.

## B. Measured accuracy

- Correct resolved decisions: **7**
- Silent wrong decisions: **0**
- Explicit abstentions among scoreable oracle fields: **0**
- Missing expected structure: **154** assertion units not emitted by the current pipeline
- Extra asserted structure: **0**; current output has no structural assertion records
- Decision precision: **100.00%**
- Oracle coverage: **100.00%** of scoreable oracle fields
- Abstention rate: **0.00%** of scoreable oracle fields
- Silent-error rate: **0.00%** of resolved scoreable oracle fields

All six fixtures are exact on their scoreable subset. This is not end-to-end structural exactness: the structural sequence, furniture, dialogue, and label outputs are absent.

The unchanged geometry run recomputed **2,219 admitted OCR tokens**, **2,212 definite line assignments**, and **7 explicit residuals** (five ambiguous and two unassigned). The fixture oracle validates **0** token-to-line assignments; all 2,212 are unscorable at that granularity.

Token-level accuracy must therefore not be reported as `2,212 / 2,219`. That ratio is resolved-assignment coverage, not accuracy.

## C. Per-fixture results

| Fixture | Admitted | Resolved | Residuals | Scoreable correct/wrong/abstain | Scoreable subset exact |
|---|---:|---:|---:|---:|---|
| `relativity_pdf10_pp26-27` | 483 | 477 | 6 | 1/0/0 | yes |
| `relativity_pdf17_pp40-41` | 473 | 472 | 1 | 1/0/0 | yes |
| `relativity_pdf23_pp52-53` | 419 | 419 | 0 | 1/0/0 | yes |
| `stella_maris_pdf03_session-I` | 133 | 133 | 0 | 2/0/0 | yes |
| `stella_maris_pdf06_dense-dialogue` | 504 | 504 | 0 | 1/0/0 | yes |
| `stella_maris_pdf18_session-II_p35` | 207 | 207 | 0 | 1/0/0 | yes |

## D. Seven residuals

The human oracle cannot establish the correct physical-line answer for any residual. It provides raw anchors and page sides, but no OCR source row, token identity, physical-line identity, or candidate-line choice. Raw lexical occurrence counts are locators only.

| Fixture | Stable identity | OCR token | State | Candidates | Oracle answer available? |
|---|---|---|---|---|---|
| `relativity_pdf10_pp26-27` / left / row 213 | `token-0213` | `system` | `unassigned_line_assignment` | none | no |
| `relativity_pdf10_pp26-27` / left / row 216 | `token-0216` | `that` | `ambiguous_line_assignment` | line-0046, line-0047 | no |
| `relativity_pdf10_pp26-27` / left / row 217 | `token-0217` | `the` | `ambiguous_line_assignment` | line-0046, line-0047 | no |
| `relativity_pdf10_pp26-27` / left / row 226 | `token-0226` | `with` | `ambiguous_line_assignment` | line-0049, line-0050 | no |
| `relativity_pdf10_pp26-27` / left / row 227 | `token-0227` | `respect` | `ambiguous_line_assignment` | line-0049, line-0050 | no |
| `relativity_pdf10_pp26-27` / right / row 246 | `token-0246` | `impossible` | `unassigned_line_assignment` | none | no |
| `relativity_pdf17_pp40-41` / right / row 23 | `token-0023` | `A` | `ambiguous_line_assignment` | line-0003, line-0004 | no |

Because the answer is not encoded, none of the seven can be labeled a useful abstention with a confirmed correct candidate, nor a silent geometry error. They remain genuine review items with oracle-insufficient outcomes.

## E. Limits

- The current production slice emits preprocessing and geometry only; it does not emit lexical alignment, paragraph starts, headings, dialogue turns, furniture labels, or Markdown structure.
- The six-fixture corpus is small and intentionally selected. It supports this corpus-specific measurement, not a general accuracy claim across books or layouts.
- The expected oracle does not encode all 2,212 resolved token-to-line answers, so token-level geometry accuracy is not established.
- No `normalized.md` secondary score is reported because there is no comparable current structural projection.

## F. Operational interpretation

The evidence supports preserving explicit geometry uncertainty for human review rather than forcing the seven residual assignments. That conclusion is about abstention policy, not proof that the 2,212 resolved assignments are correct. The measurable preprocessing fields are currently error-free on this corpus, while structural accuracy remains unmeasured until the corresponding production stages exist.

## G. Scope and provenance

- Source revision: `0ad8944f376059454da96a321f479218363535e1`
- Evaluator hash: `ec188d8653efd637ae81d269b6a59badaad97d5a10da22750c1e67bb4bf87863`
- Production files changed: none
- Fixture source/oracle files changed: none
- Secondary normalized-reference comparison: not available
- Pipeline output hashes are recorded in `results.json`; runtime files were created only in an ephemeral scratch directory and are not authoritative inputs.
