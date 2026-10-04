"""Deterministic Markdown projection of reconstructed transcript blocks."""

from __future__ import annotations

from typing import Mapping

from .reconstruction import NormalizedDocument


def emit_markdown(document: NormalizedDocument) -> str:
    """Emit structure while sourcing every visible word from lexical input."""
    output = []
    blocks = document.blocks
    index = 0
    while index < len(blocks):
        block = blocks[index]
        if (block.kind == "paragraph" and index + 2 < len(blocks)
                and blocks[index + 1].kind == "figure"
                and blocks[index + 1].evidence.get("embedded_in_prose_continuity")
                and blocks[index + 2].kind == "paragraph"):
            # Keep the logical prose paragraph intact while exposing the
            # non-prose figure as an inline structural marker at its location.
            output.append(f"{block.text} [Figure: {blocks[index + 1].text}] {blocks[index + 2].text}")
            index += 3
            continue
        if block.kind == "heading":
            output.append(f"# {block.text}")
        elif block.kind == "display_math":
            output.append(f"$$\n{block.text}\n$$")
        elif block.kind == "figure":
            output.append(f"[Figure: {block.text}]")
        else:
            output.append(block.text)
        index += 1
    return "\n\n".join(output).rstrip() + ("\n" if output else "")


def document_record(document: NormalizedDocument) -> Mapping[str, object]:
    """Machine-readable sidecar retaining links from blocks to source and geometry."""
    return {
        "schema": "normalized-document-v2",
        "source_id": document.source_id,
        "blocks": [
            {
                "kind": block.kind,
                "text": block.text,
                "lexical_spans": [list(span) for span in block.canonical_spans],
                "page_ids": list(block.page_ids),
                "physical_line_ids": list(block.physical_line_ids),
                "anchor_ids": list(block.anchor_ids),
                "confidence": block.confidence,
                "evidence": dict(block.evidence),
            }
            for block in document.blocks
        ],
        "alignments": [
            {
                "lexical_tokens": [
                    {"source_id": t.source_id, "start": t.start, "end": t.end, "text": t.text, "match_form": t.match_form}
                    for t in result.canonical_tokens
                ],
                "links": [
                    {"canonical_token_indices": list(link.canonical_token_indices), "anchor_ids": list(link.anchor_ids),
                     "physical_line_ids": list(link.physical_line_ids), "relation": link.relation,
                     "cost": link.cost, "ambiguous": link.ambiguous}
                    for link in result.links
                ],
                "unmatched_lexical_indices": list(result.unmatched_canonical_indices),
                "unmatched_anchor_ids": list(result.unmatched_anchor_ids),
                "diagnostics": list(result.diagnostics),
            }
            for result in document.alignments
        ],
        "diagnostics": [dict(item) for item in document.diagnostics],
    }
