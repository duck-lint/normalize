"""Small deterministic command-line surface for Slice 0."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .environment import check_tesseract
from .fixtures import FixtureCatalog, MetadataError
from .rendering import FixtureUnavailableError, render_fixture_page


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="normalize")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("check-env", help="check Tesseract availability and version")

    fixtures = commands.add_parser("fixtures", help="list validated fixture metadata")
    fixtures.add_argument("--json", action="store_true", dest="as_json")

    render = commands.add_parser("render", help="render one exact local fixture PDF page")
    render.add_argument("fixture_id")
    render.add_argument("--output", "-o", type=Path, help="optional path for a derived PNG")
    return parser


def _run(args: argparse.Namespace) -> int:
    if args.command == "check-env":
        report = check_tesseract()
        stream = sys.stdout if report.tesseract_available else sys.stderr
        print(report.message, file=stream)
        return 0 if report.tesseract_available else 1

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
    rendered = render_fixture_page(metadata)
    if args.output is None:
        print(
            f"Rendered {rendered.fixture_id}: {rendered.image.width}x{rendered.image.height} "
            f"from local page {rendered.fixture_pdf_page_index_1_based} "
            f"(source page {rendered.source_pdf_page_index_1_based})"
        )
        return 0

    output = args.output.resolve()
    if output.exists() and os.path.samefile(output, metadata.source_pdf):
        raise FixtureUnavailableError("refusing to overwrite the source PDF with derived output")
    output.parent.mkdir(parents=True, exist_ok=True)
    rendered.image.save(output, format="PNG")
    print(f"Rendered {rendered.fixture_id} to {output}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return _run(args)
    except (MetadataError, FixtureUnavailableError, OSError) as exc:
        print(f"normalize: {exc}", file=sys.stderr)
        return 2
