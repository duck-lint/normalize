"""Deterministic command-line surface for the Normalize project."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .environment import check_tesseract
from .fixtures import FixtureCatalog, MetadataError
from .geometry import run_geometry
from .markdown import document_record, emit_markdown
from .reconstruction import PageSpan, reconstruct_document
from .rendering import (
    FAILURE,
    SUCCESS,
    UNCERTAIN,
    PreprocessingConfigError,
    preprocess_fixture,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="normalize")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check-env", help="check Tesseract availability and version")
    fixtures = commands.add_parser("fixtures", help="list validated fixture metadata")
    fixtures.add_argument("--json", action="store_true", dest="as_json")
    preprocess = commands.add_parser("preprocess", help="preprocess one exact local fixture PDF")
    preprocess.add_argument("fixture_id")
    preprocess.add_argument("--config", type=Path, required=True)
    preprocess.add_argument("--output", "-o", type=Path, required=True)
    geometry = commands.add_parser(
        "geometry", help="extract inspectable Tesseract geometry from one preprocessed fixture"
    )
    geometry.add_argument("--preprocessed", type=Path, required=True)
    geometry.add_argument("--output", "-o", type=Path, required=True)
    reconstruct = commands.add_parser("reconstruct", help="align canonical text to geometry and emit normalized Markdown")
    reconstruct.add_argument("--raw", type=Path, required=True)
    reconstruct.add_argument("--geometry", type=Path, required=True)
    reconstruct.add_argument("--spans", type=Path, required=True, help="ordered canonical character ranges for geometry pages")
    reconstruct.add_argument("--output", "-o", type=Path, required=True)
    reconstruct.add_argument("--sidecar", type=Path, required=True)
    return parser


def _run(args: argparse.Namespace) -> int:
    if args.command == "check-env":
        report = check_tesseract()
        stream = sys.stdout if report.tesseract_available else sys.stderr
        print(report.message, file=stream)
        return 0 if report.tesseract_available else 1

    if args.command == "geometry":
        # Geometry consumes a complete preprocessing directory and must not
        # require repository fixture discovery or a repository cwd.
        result = run_geometry(args.preprocessed, args.output)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return {SUCCESS: 0, UNCERTAIN: 3, FAILURE: 2}[result["status"]]

    if args.command == "reconstruct":
        # Reconstruction receives only canonical source, geometry, and explicit
        # page-to-source spans. Fixture references are intentionally absent.
        # Decode bytes directly so CRLF or other source line endings do not
        # shift canonical character offsets through universal-newline handling.
        source = args.raw.read_bytes().decode("utf-8")
        geometry_root = json.loads(args.geometry.read_text(encoding="utf-8"))
        span_root = json.loads(args.spans.read_text(encoding="utf-8"))
        if geometry_root.get("schema") != "geometry-probe-v1":
            raise ValueError("geometry input must use geometry-probe-v1")
        pages = geometry_root.get("pages", [])
        spans = span_root.get("pages", [])
        if len(pages) != len(spans):
            raise ValueError("each geometry page must have one canonical source span")
        page_inputs = []
        for index, (geometry_page, span) in enumerate(zip(pages, spans, strict=True)):
            if span.get("page_index", index) != index:
                raise ValueError("page spans must follow geometry page order")
            page_inputs.append(PageSpan(str(span["page_id"]), int(span["start"]), int(span["end"]), geometry_page))
        document = reconstruct_document(source, str(span_root.get("source_id", args.raw.name)), page_inputs)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.sidecar.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(emit_markdown(document), encoding="utf-8")
        args.sidecar.write_text(json.dumps(document_record(document), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": "success", "blocks": len(document.blocks), "diagnostics": len(document.diagnostics)}, sort_keys=True))
        return 0

    catalog = FixtureCatalog.load()
    if args.command == "fixtures":
        rows = [
            {
                "fixture_id": item.fixture_id,
                "metadata": str(item.metadata_path),
                "source_pdf": str(item.source_pdf),
                "pdf_available": item.pdf_available,
                "fixture_pdf_page_index_1_based": item.fixture_pdf_page_index_1_based,
                "source_pdf_page_index_1_based": item.source_pdf_page_index_1_based,
            }
            for item in catalog
        ]
        if args.as_json:
            print(json.dumps(rows, indent=2))
        else:
            for row in rows:
                state = "available" if row["pdf_available"] else "missing exact PDF"
                print(f"{row['fixture_id']}: {state} — {row['source_pdf']}")
        return 0

    metadata = catalog.get(args.fixture_id)
    result = preprocess_fixture(metadata, args.config, args.output)
    print(json.dumps(result, sort_keys=True))
    return {SUCCESS: 0, UNCERTAIN: 3, FAILURE: 2}[result["status"]]


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return _run(args)
    except (MetadataError, PreprocessingConfigError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"normalize: {exc}", file=sys.stderr)
        return 2
