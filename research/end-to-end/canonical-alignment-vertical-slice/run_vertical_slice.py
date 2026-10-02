"""Run production alignment/reconstruction on the six frozen geometry pages.

Geometry and page-span maps are evidence inputs copied from the established
exact-source study. Oracle files are read only after all generated output has
been written.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from normalize.alignment import tokenize_canonical  # noqa: E402
from normalize.markdown import document_record, emit_markdown  # noqa: E402
from normalize.reconstruction import PageSpan, reconstruct_document  # noqa: E402


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _char_offset(raw: bytes, byte_offset: int) -> int:
    return len(raw[:byte_offset].decode("utf-8"))


def _source_tokens(text: str) -> list[str]:
    return [token.text for token in tokenize_canonical(text, "canonical")]


def run() -> dict:
    geometry = json.loads((HERE / "geometry-observations.json").read_text(encoding="utf-8"))
    span_manifest = json.loads((HERE / "page-spans.json").read_text(encoding="utf-8"))
    geometry_by_page = {str(page["printed_page"]): page for page in geometry["pages"]}
    grouped = defaultdict(list)
    for item in span_manifest["pages"]:
        grouped[item["raw_fixture"]].append(item)

    generated_groups = []
    results = {"schema": "canonical-alignment-vertical-slice-v1", "page_order": [26, 27, 40, 41, 52, 53], "sources": {}}
    results["page_acquisition"] = {str(page["printed_page"]): page["acquisition"] for page in geometry["pages"]}
    for raw_relative, spans in grouped.items():
        spans.sort(key=lambda item: item["start_byte"])
        raw_path = ROOT / raw_relative
        raw_bytes = raw_path.read_bytes()
        if _digest(raw_bytes) != spans[0]["raw_fixture_sha256"]:
            raise RuntimeError(f"canonical source hash changed: {raw_relative}")
        raw_text = raw_bytes.decode("utf-8")
        page_inputs = []
        for item in spans:
            start = _char_offset(raw_bytes, item["start_byte"])
            end = _char_offset(raw_bytes, item["end_byte"])
            page_inputs.append(PageSpan(str(item["printed_page"]), start, end, geometry_by_page[str(item["printed_page"])]))
        source_id = raw_relative
        document = reconstruct_document(raw_text, source_id, page_inputs)
        markdown = emit_markdown(document)

        # Verify lexical authority before any fixture oracle is opened.
        expected_words = [word for item in page_inputs for word in _source_tokens(raw_text[item.start:item.end])]
        output_words = [word for block in document.blocks for word in _source_tokens(block.text)]
        lexical_order_preserved = expected_words == output_words
        pair_pages = [item for item in span_manifest["pages"] if item["raw_fixture"] == raw_relative]
        pair_name = "-".join(item["page_id"] for item in pair_pages)
        output_path = HERE / "per-page" / f"{pair_name}.md"
        output_path.write_text(markdown, encoding="utf-8")
        sidecar_path = HERE / "per-page" / f"{pair_name}.json"
        sidecar_path.write_text(json.dumps(document_record(document), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # Single-page projections are review conveniences. The paired output
        # remains the acceptance artifact because it preserves page continuation.
        for page, item in zip(page_inputs, pair_pages, strict=True):
            page_document = reconstruct_document(raw_text, source_id, [page])
            (HERE / "per-page" / f"{item['page_id']}.md").write_text(emit_markdown(page_document), encoding="utf-8")
        page_ids = [item["page_id"] for item in spans]
        generated_groups.append((page_ids, markdown))
        results["sources"][raw_relative] = {
            "source_sha256": _digest(raw_bytes),
            "pages": page_ids,
            "paired_markdown": str(output_path.relative_to(ROOT)),
            "canonical_tokens": len(expected_words),
            "emitted_tokens": len(output_words),
            "lexical_order_preserved": lexical_order_preserved,
            "blocks": dict(Counter(block.kind for block in document.blocks)),
            "alignment": [
                {"page_id": page_ids[index], "canonical_tokens": len(alignment.canonical_tokens),
                 "matched_tokens": sum(len(link.canonical_token_indices) for link in alignment.links),
                 "matched_anchors": sum(len(link.anchor_ids) for link in alignment.links),
                 "unmatched_canonical": len(alignment.unmatched_canonical_indices),
                 "unmatched_ocr": len(alignment.unmatched_anchor_ids),
                 "ambiguous_links": sum(link.ambiguous for link in alignment.links)}
                for index, alignment in enumerate(document.alignments)
            ],
            "diagnostics": list(document.diagnostics),
        }
        if not lexical_order_preserved:
            raise RuntimeError(f"canonical lexical sequence changed during projection: {raw_relative}")

    combined = []
    for page_ids, markdown in generated_groups:
        combined.append(f"<!-- Fixture pages {', '.join(page_ids)} -->\n\n{markdown.rstrip()}")
    combined_path = HERE / "generated.md"
    combined_path.write_text("\n\n".join(combined) + "\n", encoding="utf-8")
    results["combined_markdown"] = str(combined_path.relative_to(ROOT))

    # Reference reading begins only after generated outputs are materialized.
    comparisons = {}
    for spans in grouped.values():
        expected_path = ROOT / "fixtures/einstein" / f"{spans[0]['fixture_id']}.expected.json"
        metadata = json.loads(expected_path.read_text(encoding="utf-8"))
        reference = ROOT / "fixtures/einstein" / metadata["normalized_reference"]
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        comparisons[spans[0]["fixture_id"]] = {
            "normalized_reference": str(reference.relative_to(ROOT)),
            "expected_oracle": str(expected_path.relative_to(ROOT)),
            "expected_sequence_count": len(expected.get("expected_sequence", [])),
            "reference_loaded_after_generation": combined_path.is_file(),
            "comparison_policy": "reference is structural evaluation material only; generated wording remains canonical raw text",
        }
    results["oracle_comparison_inputs"] = comparisons
    (HERE / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return results


if __name__ == "__main__":
    result = run()
    print(json.dumps({"status": "success", "sources": len(result["sources"]), "output": result["combined_markdown"]}, sort_keys=True))
