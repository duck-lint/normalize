# Slice 2 downstream text-repair boundary

This is an architectural assessment, not an implementation proposal. It does
not authorize a library, dependency, schema change, or repair rule.

## Current boundary

Slice 2 supplies token identities, observed OCR token geometry, physical-line
membership when resolved, candidate lines and uncertainty when not resolved,
and measurements used by the geometry stages. Downstream reading-order and
reconstruction stages may use that structure, but the raw/browser text remains
the lexical substrate. OCR text is a locating/alignment observation, not a
replacement source.

## What could move downstream

A separately authorized deterministic repair stage could operate on text spans
whose line membership and reading order are already sufficiently established.
It could normalize a declared lexical defect only when the source authority,
rule, input span, output span, and provenance are explicit. The repair output
would be a derived projection, not a mutation of raw text, and stable token
identity would remain attached to both observed and repaired values.

Examples of questions that might be answerable downstream are bounded,
source-authorized normalization of a known extraction artifact in a confidently
assigned span. Whether any such rule is authorized is a project decision, not
an inference from the current geometry results.

## What remains a geometry problem

Text repair cannot legitimately determine which physical line owns an
ambiguous token, reconstruct unresolved reading order, distinguish a false
merge from a false split, or recover page topology absent from the geometry
record. A dictionary, reference text, external library, or language model
cannot override scan-layout evidence or silently turn an uncertain assignment
into source fact. It also cannot use semantic fluency as proof of a paragraph
or line boundary.

The seven residual identities therefore remain Slice 2 geometry uncertainty,
not candidates for automatic lexical repair merely because a downstream string
would read more smoothly.

## Future decision boundary

Answerable with current evidence: the output fields and provenance boundary
that a repair stage would have to preserve, and the distinction between
confidently assigned spans and unresolved geometry.

Requiring additional validation: representative source-authorized lexical
anomalies, an evaluation protocol that preserves raw text, and tests proving
that repair does not alter geometry, token identity, or uncertainty.

Requiring explicit authorization: selecting a repair library, adding a
production stage or dependency, changing schemas, choosing correction rules,
or allowing any inferred text to override raw source authority.
