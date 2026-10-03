"""Deterministic command-line surface for the Normalize project."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from PIL import Image

from .bookrun import run_book
from .calibration import (
    PROPOSED_FIELDS,
    accept_calibration_proposal,
    create_calibration_proposal,
    create_empty_calibration_draft,
    load_calibration_proposal,
    save_acceptance_record,
    save_calibration_proposal,
)
from .books import (
    BOOK_MANIFEST_V2_SCHEMA,
    CALIBRATION_SOURCES,
    BookContractError,
    freeze_profile,
    load_manifest,
    load_profile,
    save_profile,
    sha256_file,
    validate_profile_for_manifest,
)
from .environment import check_tesseract
from .fixtures import FixtureCatalog, MetadataError
from .geometry import run_geometry
from .markdown import document_record, emit_markdown
from .page_interior import PAGE_INTERIOR_METHOD, measure_page_interior
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
    calibrate = commands.add_parser("calibrate", help="propose, accept, validate, or freeze physical calibration")
    calibration_commands = calibrate.add_subparsers(dest="calibration_command", required=True)
    validate_profile = calibration_commands.add_parser("validate", help="validate a profile against its manifest")
    validate_profile.add_argument("--manifest", type=Path, required=True)
    validate_profile.add_argument("--profile", type=Path, required=True)
    measure = calibration_commands.add_parser(
        "measure", help="experimentally measure physical page interiors and write proposal evidence"
    )
    measure.add_argument("--manifest", type=Path, required=True)
    measure.add_argument("--page-id", action="append", dest="page_ids",
                         help="measure this page (repeatable; default: all manifest pages)")
    measure.add_argument("--output", "-o", type=Path, required=True,
                         help="output path for calibration-proposal-v1")
    draft = calibration_commands.add_parser("draft", help="create an unresolved physical BookProfile v2 draft")
    draft.add_argument("--manifest", type=Path, required=True)
    draft.add_argument("--profile-id", required=True)
    draft.add_argument("--output", "-o", type=Path, required=True)
    proposal = calibration_commands.add_parser("proposal", help="create or validate a generic physical calibration proposal")
    proposal_commands = proposal.add_subparsers(dest="proposal_command", required=True)
    proposal_create = proposal_commands.add_parser("create", help="import sparse physical values as a calibration proposal")
    proposal_create.add_argument("--manifest", type=Path, required=True)
    proposal_create.add_argument("--values", type=Path, required=True, help="JSON object containing ordered sparse page values")
    proposal_create.add_argument("--evidence", type=Path, required=True, help="method-specific evidence file; only its SHA-256 is recorded")
    proposal_create.add_argument("--source", choices=sorted(CALIBRATION_SOURCES), required=True)
    proposal_create.add_argument("--method", required=True)
    proposal_create.add_argument("--note", required=True)
    proposal_create.add_argument("--output", type=Path, required=True)
    proposal_validate = proposal_commands.add_parser("validate", help="validate a proposal against BookManifest v2")
    proposal_validate.add_argument("--manifest", type=Path, required=True)
    proposal_validate.add_argument("--proposal", type=Path, required=True)
    accept = calibration_commands.add_parser("accept", help="explicitly accept proposed fields into a draft profile")
    accept.add_argument("--manifest", type=Path, required=True)
    accept.add_argument("--profile", type=Path, required=True, help="mutable BookProfile v2 draft")
    accept.add_argument("--proposal", type=Path, required=True)
    page_selection = accept.add_mutually_exclusive_group(required=True)
    page_selection.add_argument("--page-id", action="append", dest="page_ids")
    page_selection.add_argument("--all", action="store_true", help="select every page present in the proposal")
    field_selection = accept.add_mutually_exclusive_group(required=True)
    field_selection.add_argument("--field", action="append", choices=["content-bounds", "orientation", "deskew"], dest="fields")
    field_selection.add_argument("--all-fields", action="store_true", help="accept every value actually proposed for each selected page")
    accept.add_argument("--output", "-o", type=Path, required=True)
    freeze = calibration_commands.add_parser("freeze", help="freeze an explicitly accepted profile draft")
    freeze.add_argument("--manifest", type=Path, required=True)
    freeze.add_argument("--profile", type=Path, required=True)
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
                          "physical_sha256": manifest.physical_sha256,
                          "schema": manifest.schema,
                          "page_order": [page.page_id for page in manifest.pages],
                          "external_lexical_source": (str(manifest.canonical_source)
                              if manifest.canonical_source else None)}, ensure_ascii=False, sort_keys=True))
        return 0

    if args.command == "calibrate" and args.calibration_command == "validate":
        manifest = load_manifest(args.manifest)
        profile = load_profile(args.profile)
        validate_profile_for_manifest(profile, manifest)
        print(json.dumps({"status": "valid", "profile_id": profile.profile_id,
                          "revision": profile.revision, "state": profile.state,
                          "profile_sha256": profile.sha256}, sort_keys=True))
        return 0

    if args.command == "calibrate" and args.calibration_command == "measure":
        manifest = load_manifest(args.manifest)
        if manifest.schema != BOOK_MANIFEST_V2_SCHEMA:
            raise BookContractError("calibrate measure requires book-manifest-v2")

        evidence_path = args.output.with_suffix(args.output.suffix + ".observations.json")
        protected_inputs = {args.manifest.resolve(), *(page.image.resolve() for page in manifest.pages)}
        if args.output.resolve() in protected_inputs or evidence_path.resolve() in protected_inputs:
            raise BookContractError("calibration outputs must not overwrite the manifest or a source image")
        if args.output.resolve() == evidence_path.resolve():
            raise BookContractError("proposal and evidence outputs must be distinct")
        # Refuse existing outputs so a no-candidate run cannot leave a stale
        # proposal looking like the result of the current measurement.
        if args.output.exists() or evidence_path.exists():
            raise BookContractError("calibration output or evidence path already exists")

        pages_by_id = {page.page_id: page for page in manifest.pages}
        requested_ids = list(args.page_ids) if args.page_ids else list(pages_by_id)
        if len(set(requested_ids)) != len(requested_ids):
            raise BookContractError("--page-id contains a duplicate")
        unknown_ids = sorted(set(requested_ids) - set(pages_by_id))
        if unknown_ids:
            raise BookContractError(f"unknown page IDs: {unknown_ids}")
        selected_ids = [page.page_id for page in manifest.pages if page.page_id in set(requested_ids)]

        observations = []
        proposal_pages = []
        for page_id in selected_ids:
            page = pages_by_id[page_id]
            if not page.image.is_file():
                raise BookContractError(f"page {page_id}: image does not exist: {page.image}")
            actual_hash = sha256_file(page.image)
            if page.source_sha256 != actual_hash:
                raise BookContractError(f"page {page_id}: source SHA-256 does not match manifest")
            try:
                with Image.open(page.image) as image:
                    image.load()
                    observation = measure_page_interior(image, page_id=page_id)
                    source_dimensions = list(image.size)
            except (OSError, ValueError) as exc:
                raise BookContractError(f"page {page_id}: cannot measure source image: {exc}") from exc

            evidence_row = {
                **observation.record(page_id),
                "source_sha256": actual_hash,
                "source_dimensions_px": source_dimensions,
            }
            observations.append(evidence_row)
            values = {}
            # Bounds remain useful candidates even when the observation's
            # method-specific status is partial. Acceptance remains a human act.
            if observation.content_bounds is not None:
                values["content_bounds"] = list(observation.content_bounds)
            if observation.deskew_degrees_clockwise is not None:
                values["deskew_degrees"] = observation.deskew_degrees_clockwise
            if values:
                proposal_pages.append({"page_id": page_id, "values": values})

        evidence_record = {
            "schema": "page-interior-measurements-v1",
            "method": PAGE_INTERIOR_METHOD,
            "physical_manifest_sha256": manifest.physical_sha256,
            "observations": observations,
        }
        evidence_bytes = (
            json.dumps(evidence_record, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_bytes(evidence_bytes)

        counts = {
            "observed_pages": len(observations),
            "proposal_pages": len(proposal_pages),
            "pages_with_candidate_bounds": sum(row["content_bounds"] is not None for row in observations),
            "pages_with_deskew_proposals": sum(row["deskew_degrees_clockwise"] is not None for row in observations),
            "pages_without_generic_proposal_values": len(observations) - len(proposal_pages),
        }
        if not proposal_pages:
            print(json.dumps({"status": "no_candidates", "evidence": str(evidence_path),
                              "proposal": None, **counts}, sort_keys=True))
            return 3

        proposal = create_calibration_proposal(
            manifest,
            {
                "source": "detector",
                "method": PAGE_INTERIOR_METHOD,
                "evidence_sha256": hashlib.sha256(evidence_bytes).hexdigest(),
                "note": "Experimental pixel-only physical acquisition evidence; human review required.",
            },
            proposal_pages,
        )
        save_calibration_proposal(proposal, args.output)
        print(json.dumps({"status": "proposal_created", "proposal_id": proposal.proposal_id,
                          "evidence": str(evidence_path), "proposal": str(args.output),
                          **counts}, sort_keys=True))
        return 0

    if args.command == "calibrate" and args.calibration_command == "draft":
        manifest = load_manifest(args.manifest)
        draft_profile = create_empty_calibration_draft(manifest, profile_id=args.profile_id)
        if draft_profile.schema != "book-profile-v2":
            raise BookContractError("calibrate draft requires book-manifest-v2")
        save_profile(draft_profile, args.output)
        print(json.dumps({"status": "draft_created", "profile_id": draft_profile.profile_id,
                          "profile_state": draft_profile.state, "profile": str(args.output)}, sort_keys=True))
        return 0

    if args.command == "calibrate" and args.calibration_command == "proposal":
        manifest = load_manifest(args.manifest)
        if args.proposal_command == "create":
            if args.output.resolve() in {args.values.resolve(), args.evidence.resolve()}:
                raise BookContractError("proposal output must not overwrite its values or evidence input")
            raw_values = json.loads(args.values.read_text(encoding="utf-8"))
            if not isinstance(raw_values, dict) or set(raw_values) != {"pages"}:
                raise BookContractError("proposal values file must contain exactly a pages array")
            if not isinstance(raw_values["pages"], list):
                raise BookContractError("proposal values.pages must be an array")
            evidence_digest = hashlib.sha256(args.evidence.read_bytes()).hexdigest()
            proposal_artifact = create_calibration_proposal(
                manifest,
                {"source": args.source, "method": args.method,
                 "evidence_sha256": evidence_digest, "note": args.note},
                raw_values["pages"],
            )
            save_calibration_proposal(proposal_artifact, args.output)
            print(json.dumps({"status": "proposal_created", "proposal_id": proposal_artifact.proposal_id,
                              "pages": len(proposal_artifact.pages), "output": str(args.output)}, sort_keys=True))
            return 0
        proposal_artifact = load_calibration_proposal(args.proposal, manifest)
        print(json.dumps({"status": "valid", "proposal_id": proposal_artifact.proposal_id,
                          "book_id": proposal_artifact.book_id,
                          "physical_manifest_sha256": proposal_artifact.physical_manifest_sha256,
                          "pages": len(proposal_artifact.pages)}, sort_keys=True))
        return 0

    if args.command == "calibrate" and args.calibration_command == "accept":
        manifest = load_manifest(args.manifest)
        proposal_artifact = load_calibration_proposal(args.proposal, manifest)
        profile = load_profile(args.profile)
        if args.output.resolve() == args.profile.resolve():
            raise BookContractError("acceptance output must be separate from its input profile")
        if args.output.resolve() == args.proposal.resolve():
            raise BookContractError("acceptance output must be separate from its proposal")
        if args.all:
            selected_page_ids = [page["page_id"] for page in proposal_artifact.pages]
        else:
            selected_page_ids = args.page_ids
        aliases = {"content-bounds": "content_bounds", "orientation": "orientation_degrees",
                   "deskew": "deskew_degrees"}
        selected_fields = [aliases[value] for value in args.fields] if args.fields else None
        proposal_fields = {page["page_id"]: page["values"] for page in proposal_artifact.pages}
        accepted_pages = {
            page_id: (selected_fields if selected_fields is not None
                      else [field for field in PROPOSED_FIELDS if field in proposal_fields[page_id]])
            for page_id in selected_page_ids
        }
        accepted_profile, acceptance = accept_calibration_proposal(
            proposal_artifact, manifest, profile, accepted_pages=accepted_pages,
        )
        save_profile(accepted_profile, args.output)
        acceptance_path = args.output.with_suffix(args.output.suffix + ".acceptance.json")
        save_acceptance_record(acceptance, acceptance_path)
        print(json.dumps({"status": "accepted_to_draft", "profile_id": accepted_profile.profile_id,
                          "profile_state": accepted_profile.state,
                          "accepted_pages": len(acceptance["accepted_pages"]),
                          "profile": str(args.output), "acceptance": str(acceptance_path)}, sort_keys=True))
        return 0

    if args.command == "calibrate" and args.calibration_command == "freeze":
        manifest = load_manifest(args.manifest)
        draft = load_profile(args.profile)
        if args.output.resolve() == args.profile.resolve():
            raise BookContractError("freeze output must be separate from its input draft")
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
