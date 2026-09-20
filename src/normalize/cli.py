"""Deterministic command-line surface for the Normalize project."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .environment import check_tesseract
from .fixtures import FixtureCatalog, MetadataError
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
    result = preprocess_fixture(metadata, args.config, args.output)
    print(json.dumps(result, sort_keys=True))
    return {SUCCESS: 0, UNCERTAIN: 3, FAILURE: 2}[result["status"]]


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return _run(args)
    except (MetadataError, PreprocessingConfigError, OSError) as exc:
        print(f"normalize: {exc}", file=sys.stderr)
        return 2
