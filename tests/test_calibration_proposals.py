from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

from normalize.books import (
    BookContractError,
    draft_profile_from_record,
    freeze_profile,
    load_manifest,
    load_profile,
    save_profile,
    validate_profile_for_manifest,
)
from normalize.calibration import (
    accept_calibration_proposal,
    create_calibration_proposal,
    create_empty_calibration_draft,
    load_calibration_proposal,
    proposal_from_record,
    save_calibration_proposal,
    validate_calibration_proposal,
)


def _manifest(root: Path, *, book_id: str = "physical-fixture", pages: int = 3,
              pixel: tuple[int, int, int] = (255, 255, 255)):
    root.mkdir(parents=True, exist_ok=True)
    page_records = []
    for index in range(1, pages + 1):
        image_path = root / f"page-{index:03}.png"
        Image.new("RGB", (200, 250), pixel).save(image_path)
        page_records.append({"page_id": f"page-{index:03}", "image": image_path.name,
                             "source_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest()})
    manifest_path = root / "book.json"
    manifest_path.write_text(json.dumps({"schema": "book-manifest-v2", "book_id": book_id,
        "source_dpi": 300, "pages": page_records}), encoding="utf-8")
    return load_manifest(manifest_path)


def _producer(*, source: str = "detector", method: str = "example-method-v3",
              evidence: str = "a" * 64, note: str = "Synthetic measurement evidence"):
    return {"source": source, "method": method, "evidence_sha256": evidence, "note": note}


def _proposal(manifest, pages):
    return create_calibration_proposal(manifest, _producer(), pages)


def _row(page_id: str, *, bounds=None, orientation=None, deskew=None):
    values = {}
    if bounds is not None:
        values["content_bounds"] = bounds
    if orientation is not None:
        values["orientation_degrees"] = orientation
    if deskew is not None:
        values["deskew_degrees"] = deskew
    return {"page_id": page_id, "values": values}


def _human_profile(manifest):
    records = []
    for page in manifest.pages:
        records.append({"page_id": page.page_id, "content_bounds": [10, 12, 190, 238],
            "content_status": "measured", "orientation_degrees": 0,
            "orientation_status": "no_transform", "deskew_degrees": None,
            "deskew_status": "unresolved", "source": "human", "note": "Reviewed crop"})
    return draft_profile_from_record({"source_dpi": 300,
        "source_dpi_provenance": {"source": "human", "note": "Recorded scanner setting"},
        "calibration_pages": [page.page_id for page in manifest.pages], "pages": records},
        manifest, profile_id="human-draft")


def test_sparse_proposal_is_path_independent_and_valid_without_a_profile(tmp_path):
    manifest = _manifest(tmp_path / "first")
    proposal = _proposal(manifest, [_row("page-001", bounds=[10, 12, 190, 238]),
                                    _row("page-003", deskew=-0.25)])
    validate_calibration_proposal(proposal, manifest)
    record = proposal.record()
    assert record["schema"] == "calibration-proposal-v1"
    assert record["pages"][0]["values"] == {"content_bounds": [10, 12, 190, 238]}
    assert record["pages"][1]["values"] == {"deskew_degrees": -0.25}

    relocated = _manifest(tmp_path / "relocated")
    same = _proposal(relocated, [_row("page-001", bounds=[10, 12, 190, 238]),
                                 _row("page-003", deskew=-0.25)])
    assert same.proposal_id == proposal.proposal_id


def test_empty_profile_draft_note_describes_unresolved_values_without_claiming_measurement(tmp_path):
    manifest = _manifest(tmp_path, pages=1)
    draft = create_empty_calibration_draft(manifest, profile_id="empty-note")
    note = draft.page_calibrations["page-001"].note
    assert "unresolved" in note
    assert "none are accepted" in note
    assert "measured" not in note


@pytest.mark.parametrize(("field", "value"), [
    ("content_bounds", [10, 12, 190, 238]),
    ("deskew_degrees", -0.2),
])
def test_partial_acceptance_replaces_empty_draft_note(tmp_path, field, value):
    manifest = _manifest(tmp_path, pages=1)
    draft = create_empty_calibration_draft(manifest, profile_id=f"accept-{field}")
    proposal = _proposal(manifest, [{"page_id": "page-001", "values": {field: value}}])

    accepted, _ = accept_calibration_proposal(
        proposal, manifest, draft, accepted_pages={"page-001": [field]},
    )

    note = accepted.page_calibrations["page-001"].note
    assert f"Human accepted {field}" in note
    assert proposal.proposal_id in note
    assert "none are accepted" not in note
    assert "all physical calibration values are unresolved" not in note


def test_proposal_round_trip_and_tampering_are_detected(tmp_path):
    manifest = _manifest(tmp_path)
    proposal = _proposal(manifest, [_row("page-001", orientation=90)])
    path = tmp_path / "proposal.json"
    save_calibration_proposal(proposal, path)
    assert load_calibration_proposal(path, manifest).proposal_id == proposal.proposal_id
    record = json.loads(path.read_text())
    record["pages"][0]["values"]["orientation_degrees"] = 180
    with pytest.raises(BookContractError, match="identity digest"):
        proposal_from_record(record, manifest)


@pytest.mark.parametrize("bad_values, message", [
    ({}, "at least one"),
    ({"content_bounds": None}, "null"),
    ({"content_bounds": [1, 2, 3]}, "content_bounds"),
    ({"content_bounds": [0, 0, 201, 200]}, "exceed image dimensions"),
    ({"orientation_degrees": 45}, "one of 0, 90, 180, 270"),
    ({"deskew_degrees": float("nan")}, "finite"),
    ({"deskew_degrees": 45.01}, "magnitude at most 45"),
])
def test_proposal_rejects_empty_null_or_invalid_physical_values(tmp_path, bad_values, message):
    manifest = _manifest(tmp_path)
    with pytest.raises(BookContractError, match=message):
        _proposal(manifest, [{"page_id": "page-001", "values": bad_values}])


def test_proposal_rejects_unknown_duplicate_or_reordered_pages(tmp_path):
    manifest = _manifest(tmp_path)
    with pytest.raises(BookContractError, match="not in BookManifest"):
        _proposal(manifest, [_row("other-page", deskew=0.1)])
    with pytest.raises(BookContractError, match="duplicate"):
        _proposal(manifest, [_row("page-001", deskew=0.1), _row("page-001", orientation=90)])
    with pytest.raises(BookContractError, match="order"):
        _proposal(manifest, [_row("page-002", deskew=0.1), _row("page-001", orientation=90)])


def test_proposal_rejects_manifest_v1_and_mismatched_physical_identity(tmp_path):
    manifest = _manifest(tmp_path / "v2")
    proposal = _proposal(manifest, [_row("page-001", deskew=0.1)])
    other_manifest = _manifest(tmp_path / "other", pixel=(240, 240, 240))
    with pytest.raises(BookContractError, match="physical_manifest_sha256"):
        validate_calibration_proposal(proposal, other_manifest)

    legacy_root = tmp_path / "legacy"
    legacy_root.mkdir()
    legacy_image = legacy_root / "page.png"
    Image.new("RGB", (200, 250), "white").save(legacy_image)
    (legacy_root / "raw.txt").write_text("legacy", encoding="utf-8")
    legacy_path = legacy_root / "book.json"
    legacy_path.write_text(json.dumps({"schema": "book-manifest-v1", "book_id": "legacy",
        "source_dpi": 300, "canonical_source": "raw.txt",
        "pages": [{"page_id": "page-001", "image": "page.png",
                   "canonical_span": {"start": 0, "end": 6}}]}), encoding="utf-8")
    legacy = load_manifest(legacy_path)
    with pytest.raises(BookContractError, match="book-manifest-v2"):
        _proposal(legacy, [_row("page-001", deskew=0.1)])


def test_accept_bounds_only_preserves_other_fields_and_records_authorization(tmp_path):
    manifest = _manifest(tmp_path)
    draft = _human_profile(manifest)
    proposal = _proposal(manifest, [_row("page-001", bounds=[20, 22, 180, 230], deskew=0.5)])
    proposal_before = proposal.record()

    accepted, record = accept_calibration_proposal(
        proposal, manifest, draft,
        accepted_pages={"page-001": ["content_bounds"]},
    )
    page = accepted.page_calibrations["page-001"]
    assert page.content_bounds == (20, 22, 180, 230)
    assert page.content_status == "measured"
    assert page.deskew_degrees is None
    assert page.deskew_status == "unresolved"
    assert page.orientation_degrees == 0
    assert page.source == "human"
    assert proposal.record() == proposal_before
    assert accepted.state == "draft" and accepted.revision == draft.revision
    assert accepted.physical_manifest_sha256 == manifest.physical_sha256
    assert "Human accepted content_bounds" in page.note
    assert "none are accepted" not in page.note
    assert record["schema"] == "calibration-acceptance-v1"
    assert record["input_profile_sha256"] == draft.sha256
    assert record["output_profile_sha256"] == accepted.sha256
    assert record["accepted_pages"] == [{"page_id": "page-001", "fields": ["content_bounds"]}]


def test_accept_deskew_only_preserves_human_bounds_and_is_idempotent(tmp_path):
    manifest = _manifest(tmp_path)
    draft = _human_profile(manifest)
    proposal = _proposal(manifest, [_row("page-001", bounds=[20, 20, 180, 230], deskew=-0.3)])
    accept_args = {"accepted_pages": {"page-001": ["deskew_degrees"]}}
    first, _ = accept_calibration_proposal(proposal, manifest, draft, **accept_args)
    second, _ = accept_calibration_proposal(proposal, manifest, first, **accept_args)
    page = first.page_calibrations["page-001"]
    assert page.content_bounds == draft.page_calibrations["page-001"].content_bounds
    assert page.content_status == "measured"
    assert page.deskew_degrees == pytest.approx(-0.3)
    assert page.deskew_status == "measured"
    assert page.source == "human"
    assert "deskew_degrees" in page.note
    assert "none are accepted" not in page.note
    assert first.sha256 == second.sha256


def test_later_proposal_acceptance_preserves_prior_acceptance_history(tmp_path):
    manifest = _manifest(tmp_path, pages=1)
    draft = create_empty_calibration_draft(manifest, profile_id="history")
    first_proposal = create_calibration_proposal(
        manifest, _producer(method="first-method-v1", evidence="c" * 64),
        [_row("page-001", bounds=[10, 10, 180, 220])],
    )
    first_draft, _ = accept_calibration_proposal(
        first_proposal, manifest, draft,
        accepted_pages={"page-001": ["content_bounds"]},
    )

    second_proposal = create_calibration_proposal(
        manifest, _producer(method="second-method-v1", evidence="d" * 64),
        [_row("page-001", deskew=0.2)],
    )
    second_draft, _ = accept_calibration_proposal(
        second_proposal, manifest, first_draft,
        accepted_pages={"page-001": ["deskew_degrees"]},
    )

    note = second_draft.page_calibrations["page-001"].note
    assert first_proposal.proposal_id in note
    assert second_proposal.proposal_id in note
    assert "first-method-v1" in note
    assert "second-method-v1" in note
    assert "none are accepted" not in note


def test_accept_orientation_only_and_all_proposed_fields_for_selected_pages(tmp_path):
    manifest = _manifest(tmp_path)
    draft = create_empty_calibration_draft(manifest, profile_id="empty")
    proposal = _proposal(manifest, [
        _row("page-001", bounds=[10, 10, 190, 240], orientation=0, deskew=0),
        _row("page-002", orientation=90),
    ])
    orientation_only, _ = accept_calibration_proposal(
        proposal, manifest, draft, accepted_pages={"page-002": ["orientation_degrees"]})
    page = orientation_only.page_calibrations["page-002"]
    assert page.orientation_degrees == 90 and page.orientation_status == "measured"
    assert page.content_bounds is None and page.deskew_degrees is None

    all_fields, _ = accept_calibration_proposal(proposal, manifest, draft,
        accepted_pages={"page-001": ["content_bounds", "orientation_degrees", "deskew_degrees"],
                        "page-002": ["orientation_degrees"]})
    first_page = all_fields.page_calibrations["page-001"]
    assert first_page.content_bounds == (10, 10, 190, 240)
    assert first_page.orientation_status == "no_transform"
    assert first_page.deskew_status == "no_transform"
    assert all_fields.page_calibrations["page-003"] == draft.page_calibrations["page-003"]


def test_acceptance_rejects_absent_fields_frozen_or_v1_profiles(tmp_path):
    manifest = _manifest(tmp_path / "v2")
    draft = create_empty_calibration_draft(manifest, profile_id="draft")
    proposal = _proposal(manifest, [_row("page-001", deskew=0.2)])
    with pytest.raises(BookContractError, match="no values for requested fields"):
        accept_calibration_proposal(proposal, manifest, draft,
                                    accepted_pages={"page-001": ["content_bounds"]})
    frozen = freeze_profile(draft, manifest)
    with pytest.raises(BookContractError, match="draft profile"):
        accept_calibration_proposal(proposal, manifest, frozen,
                                    accepted_pages={"page-001": ["deskew_degrees"]})

    legacy_root = tmp_path / "v1"
    legacy_root.mkdir()
    legacy_image = legacy_root / "page.png"
    Image.new("RGB", (200, 250), "white").save(legacy_image)
    (legacy_root / "raw.txt").write_text("legacy", encoding="utf-8")
    manifest_path = legacy_root / "book.json"
    manifest_path.write_text(json.dumps({"schema": "book-manifest-v1", "book_id": "legacy",
        "source_dpi": 300, "canonical_source": "raw.txt",
        "pages": [{"page_id": "page-001", "image": "page.png",
                   "canonical_span": {"start": 0, "end": 6}}]}), encoding="utf-8")
    legacy_manifest = load_manifest(manifest_path)
    measurements = {"source_dpi": 300,
        "source_dpi_provenance": {"source": "human", "note": "test"},
        "calibration_pages": [], "pages": [{"page_id": "page-001", "content_bounds": None,
            "content_status": "unresolved", "orientation_degrees": None, "orientation_status": "unresolved",
            "deskew_degrees": None, "deskew_status": "unresolved", "source": "human", "note": "test"}]}
    legacy_profile = draft_profile_from_record(measurements, legacy_manifest, profile_id="legacy")
    with pytest.raises(BookContractError, match="book-manifest-v2"):
        accept_calibration_proposal(proposal, legacy_manifest, legacy_profile,
                                    accepted_pages={"page-001": ["deskew_degrees"]})


def test_partial_evidence_can_be_accepted_without_interpreting_its_method(tmp_path):
    manifest = _manifest(tmp_path, pages=1)
    draft = create_empty_calibration_draft(manifest, profile_id="partial")
    proposal = create_calibration_proposal(manifest, _producer(
        method="edge-meter-v9", evidence="b" * 64,
        note="Evidence records two clipped edges and a partial boundary."),
        [_row("page-001", bounds=[0, 10, 200, 240])])
    before = proposal.record()

    accepted, _ = accept_calibration_proposal(proposal, manifest, draft,
        accepted_pages={"page-001": ["content_bounds"]})

    page = accepted.page_calibrations["page-001"]
    assert page.content_bounds == (0, 10, 200, 240)
    assert page.content_status == "measured"
    assert "edge-meter-v9" in page.note and "b" * 64 in page.note
    assert "partial boundary" in page.note
    assert proposal.record() == before


def test_freeze_accepts_accepted_draft_and_keeps_provenance(tmp_path):
    manifest = _manifest(tmp_path, pages=1)
    draft = create_empty_calibration_draft(manifest, profile_id="ready")
    proposal = _proposal(manifest, [_row("page-001", bounds=[10, 10, 190, 240], deskew=0.25)])
    accepted, _ = accept_calibration_proposal(proposal, manifest, draft,
        accepted_pages={"page-001": ["content_bounds", "deskew_degrees"]})

    frozen = freeze_profile(accepted, manifest)
    validate_profile_for_manifest(frozen, manifest, require_frozen=True)
    page = frozen.page_calibrations["page-001"]
    assert page.content_bounds == (10, 10, 190, 240)
    assert page.deskew_degrees == pytest.approx(0.25)
    assert page.source == "human" and proposal.proposal_id in page.note
    assert frozen.state == "frozen"


def test_cli_proposal_validation_acceptance_and_freeze_form_separate_steps(tmp_path, monkeypatch):
    from normalize import cli
    from normalize.bookrun import run_book
    from normalize.engine import BookEngine

    manifest = _manifest(tmp_path, pages=1)
    draft = create_empty_calibration_draft(manifest, profile_id="cli-flow")
    draft_path = tmp_path / "draft.json"
    save_profile(draft, draft_path)
    values_path = tmp_path / "values.json"
    values_path.write_text(json.dumps({"pages": [{"page_id": "page-001", "values": {
        "content_bounds": [10, 10, 190, 240], "deskew_degrees": 0.0}}]}), encoding="utf-8")
    evidence_path = tmp_path / "method-evidence.json"
    evidence_path.write_text('{"partial": true}', encoding="utf-8")
    proposal_path = tmp_path / "proposal.json"
    assert cli.main(["calibrate", "proposal", "create", "--manifest", str(manifest.path),
        "--values", str(values_path), "--evidence", str(evidence_path), "--source", "detector",
        "--method", "generic-edge-method-v1", "--note", "Synthetic partial edge evidence",
        "--output", str(proposal_path)]) == 0
    proposal_bytes = proposal_path.read_bytes()
    assert cli.main(["calibrate", "proposal", "validate", "--manifest", str(manifest.path),
                     "--proposal", str(proposal_path)]) == 0
    accepted_path = tmp_path / "accepted.json"
    assert cli.main(["calibrate", "accept", "--manifest", str(manifest.path),
        "--profile", str(draft_path), "--proposal", str(proposal_path),
        "--page-id", "page-001", "--field", "deskew", "--output", str(accepted_path)]) == 0
    assert proposal_path.read_bytes() == proposal_bytes
    accepted = load_profile(accepted_path)
    row = accepted.page_calibrations["page-001"]
    assert row.content_bounds is None
    assert row.deskew_degrees == 0.0 and row.deskew_status == "no_transform"
    assert row.source == "human"
    acceptance_path = accepted_path.with_suffix(".json.acceptance.json")
    acceptance = json.loads(acceptance_path.read_text())
    assert acceptance["accepted_pages"] == [{"page_id": "page-001", "fields": ["deskew_degrees"]}]

    frozen_path = tmp_path / "frozen.json"
    assert cli.main(["calibrate", "freeze", "--manifest", str(manifest.path),
                     "--profile", str(accepted_path), "--output", str(frozen_path)]) == 0
    frozen = load_profile(frozen_path)
    monkeypatch.setattr("normalize.engine.pytesseract.image_to_data",
        lambda *args, **kwargs: "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n")
    output = tmp_path / "run"
    run = run_book(manifest, frozen, output, engine=BookEngine(), resume=False)
    assert run["schema"] == "normalize-book-run-v2"
    assert (output / "normalized.md").exists()


def test_cli_requires_explicit_page_and_field_selection(tmp_path):
    from normalize import cli

    manifest = _manifest(tmp_path, pages=1)
    draft_path = tmp_path / "draft.json"
    save_profile(create_empty_calibration_draft(manifest, profile_id="selection"), draft_path)
    proposal_path = tmp_path / "proposal.json"
    save_calibration_proposal(_proposal(manifest, [_row("page-001", deskew=0.2)]), proposal_path)
    base = ["calibrate", "accept", "--manifest", str(manifest.path), "--profile", str(draft_path),
            "--proposal", str(proposal_path), "--output", str(tmp_path / "out.json")]
    with pytest.raises(SystemExit):
        cli.main(base)
    with pytest.raises(SystemExit):
        cli.main([*base, "--all"])


def test_cli_all_and_all_fields_are_explicit_and_accept_only_present_values(tmp_path):
    from normalize import cli

    manifest = _manifest(tmp_path, pages=2)
    draft_path = tmp_path / "draft.json"
    save_profile(create_empty_calibration_draft(manifest, profile_id="all-selection"), draft_path)
    proposal_path = tmp_path / "proposal.json"
    proposal = _proposal(manifest, [_row("page-001", bounds=[10, 10, 190, 240]),
                                    _row("page-002", deskew=0.0)])
    save_calibration_proposal(proposal, proposal_path)
    output = tmp_path / "all.json"
    assert cli.main(["calibrate", "accept", "--manifest", str(manifest.path),
        "--profile", str(draft_path), "--proposal", str(proposal_path), "--all", "--all-fields",
        "--output", str(output)]) == 0
    profile = load_profile(output)
    assert profile.page_calibrations["page-001"].content_status == "measured"
    assert profile.page_calibrations["page-002"].deskew_status == "no_transform"
