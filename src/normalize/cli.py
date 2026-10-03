"""Deterministic command-line surface for the Normalize project."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .bookrun import run_book
from .books import (
    BookContractError,
    draft_profile_from_record,
    freeze_profile,
    load_manifest,
    load_profile,
    revised_draft_from_record,
    save_profile,
    validate_profile_for_manifest,
)
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
    book = commands.add_parser("book", help="validate an ordered book source manifest")
    book_commands = book.add_subparsers(dest="book_command", required=True)
    validate_manifest = book_commands.add_parser("validate", help="validate a book manifest and its page sources")
    validate_manifest.add_argument("--manifest", type=Path, required=True)
    calibrate = commands.add_parser("calibrate", help="validate or freeze book calibration measurements")
    calibration_commands = calibrate.add_subparsers(dest="calibration_command", required=True)
    validate_profile = calibration_commands.add_parser("validate", help="validate a profile against its manifest")
    validate_profile.add_argument("--manifest", type=Path, required=True)
    validate_profile.add_argument("--profile", type=Path, required=True)
    freeze = calibration_commands.add_parser("freeze", help="validate supplied measurements and freeze profile v1")
    freeze.add_argument("--manifest", type=Path, required=True)
    freeze.add_argument("--measurements", type=Path, required=True)
    freeze.add_argument("--profile-id", required=True)
    freeze.add_argument("--previous-profile", type=Path, help="create the next revision from this frozen profile")
    freeze.add_argument("--output", "-o", type=Path, required=True)
    book_run = commands.add_parser("run", help="process an ordered book with a frozen profile")
    book_run.add_argument("--manifest", type=Path, required=True)
    book_run.add_argument("--profile", type=Path, required=True)
    book_run.add_argument("--output", "-o", type=Path, required=True)
    book_run.add_argument("--no-resume", action="store_true", help="recompute page observations")
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

    if args.command == "book" and args.book_command == "validate":
        manifest = load_manifest(args.manifest)
        print(json.dumps({"status": "valid", "book_id": manifest.book_id,
                          "manifest_sha256": manifest.sha256,
                          "page_order": [page.page_id for page in manifest.pages],
                          "canonical_source": str(manifest.canonical_source)}, ensure_ascii=False, sort_keys=True))
        return 0

    if args.command == "calibrate" and args.calibration_command == "validate":
        manifest = load_manifest(args.manifest)
        profile = load_profile(args.profile)
        validate_profile_for_manifest(profile, manifest)
        print(json.dumps({"status": "valid", "profile_id": profile.profile_id,
                          "revision": profile.revision, "state": profile.state,
                          "profile_sha256": profile.sha256}, sort_keys=True))
        return 0

    if args.command == "calibrate" and args.calibration_command == "freeze":
        manifest = load_manifest(args.manifest)
        measurements = json.loads(args.measurements.read_text(encoding="utf-8"))
        if args.previous_profile:
            previous = load_profile(args.previous_profile)
            if args.profile_id != previous.profile_id:
                raise BookContractError("--profile-id must match --previous-profile.profile_id")
            draft = revised_draft_from_record(measurements, manifest, previous)
        else:
            draft = draft_profile_from_record(measurements, manifest, profile_id=args.profile_id)
        frozen = freeze_profile(draft, manifest)
        save_profile(frozen, args.output)
        print(json.dumps({"status": "frozen", "profile_id": frozen.profile_id,
                          "revision": frozen.revision, "profile_sha256": frozen.sha256,
                          "output": str(args.output)}, sort_keys=True))
        return 0

    if args.command == "run":
        manifest = load_manifest(args.manifest)
        profile = load_profile(args.profile)
        result = run_book(manifest, profile, args.output, resume=not args.no_resume)
        print(json.dumps({"status": result["status"], "run_id": result["run_id"],
                          "pages": len(result["pages"]), "review_diagnostic_count": result["review_diagnostic_count"],
                          "output": str(args.output)}, sort_keys=True))
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
    except (BookContractError, MetadataError, PreprocessingConfigError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"normalize: {exc}", file=sys.stderr)
        return 2
