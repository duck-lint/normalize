import json
from pathlib import Path

from normalize.cli import main
from normalize.markdown import emit_markdown
from normalize.reconstruction import PageSpan, reconstruct_document


def _geometry():
    words = [("Canonical", 10, 1), ("word.", 22, 2)]
    tokens = [{"token_id": f"t{i}", "text": word, "confidence": 91,
               "x_px": x, "y_px": 10, "width_px": 10, "height_px": 10,
               "physical_line_id": "line-1"} for word, x, i in words]
    return {"schema": "geometry-probe-v1", "status": "success", "pages": [{
        "page_id": "printed-1", "width_px": 100, "height_px": 100,
        "tokens": tokens, "physical_lines": [{"line_id": "line-1", "token_ids": ["t1", "t2"],
            "left_px": 10, "right_px": 32, "top_px": 10, "bottom_px": 20,
            "line_height_px": 10, "vertical_gap_to_next_px": None}],
    }]}


def test_ocr_spelling_never_becomes_emitted_canonical_prose():
    source = "Canonical word."
    geometry = _geometry()["pages"][0]
    geometry["tokens"][0]["text"] = "Cannonical"
    document = reconstruct_document(source, "raw", [PageSpan("1", 0, len(source), geometry)])
    output = emit_markdown(document)
    assert output.strip() == source
    assert "Cannonical" not in output


def test_cli_generates_output_with_only_raw_geometry_and_span_inputs(tmp_path):
    raw = tmp_path / "source.raw"
    geo = tmp_path / "geometry.json"
    spans = tmp_path / "page-spans.json"
    output = tmp_path / "generated.md"
    sidecar = tmp_path / "provenance.json"
    raw.write_bytes(b"Canonical word.")
    geo.write_text(json.dumps(_geometry()), encoding="utf-8")
    spans.write_text(json.dumps({"source_id": "source.raw", "pages": [{"page_id": "1", "start": 0, "end": 15}]}), encoding="utf-8")

    exit_code = main(["reconstruct", "--raw", str(raw), "--geometry", str(geo),
                      "--spans", str(spans), "--output", str(output), "--sidecar", str(sidecar)])

    assert exit_code == 0
    assert output.read_text(encoding="utf-8").strip() == "Canonical word."
    assert json.loads(sidecar.read_text(encoding="utf-8"))["blocks"][0]["lexical_spans"]
    # This isolated input directory has no structural reference files. Runtime
    # generation therefore cannot depend on normalized or expected fixtures.
    assert set(path.name for path in tmp_path.iterdir()) == {
        "geometry.json", "generated.md", "page-spans.json", "provenance.json", "source.raw"
    }
