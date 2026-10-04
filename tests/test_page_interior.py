from __future__ import annotations

import hashlib
import json

import pytest
from PIL import Image, ImageDraw

from normalize import cli
from normalize.books import load_manifest, load_profile
from normalize.calibration import load_calibration_proposal
from normalize.page_interior import measure_page_interior


def _synthetic_scan(
    *,
    background: tuple[int, int, int] = (255, 255, 255),
    angle_degrees: float = 0,
    page_color: tuple[int, int, int] = (247, 242, 228),
    page_box: tuple[int, int, int, int] = (130, 120, 690, 900),
    edge_shadow_px: int = 0,
    content: str = "dense",
    highlighted: bool = False,
) -> Image.Image:
    """Draw page surfaces and marks as pixels, with no OCR-derived labels."""
    canvas_size = (900, 1100)
    page_layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(page_layer)
    draw.rectangle(page_box, fill=(*page_color, 255))
    if edge_shadow_px:
        x0, y0, x1, y1 = page_box
        draw.rectangle(
            (x0, y0, x1, y1),
            outline=(115, 110, 104, 255),
            width=edge_shadow_px,
        )
    if content == "dense":
        for y in range(page_box[1] + 80, page_box[3] - 80, 42):
            draw.line((page_box[0] + 55, y, page_box[2] - 45, y), fill=(35, 35, 35, 255), width=3)
    elif content == "near_edge":
        # A legitimate isolated mark close to (but inside) the sheet edge.
        draw.rectangle((page_box[0] + 18, page_box[1] + 40, page_box[0] + 27, page_box[1] + 62), fill=(20, 20, 20, 255))
    elif content == "sparse":
        draw.rectangle((page_box[0] + 270, page_box[1] + 330, page_box[0] + 282, page_box[1] + 342), fill=(20, 20, 20, 255))
    elif content != "blank":
        raise ValueError(content)
    if highlighted:
        draw.line((page_box[0] + 55, page_box[1] + 80, page_box[2] - 45, page_box[1] + 80), fill=(45, 205, 175, 255), width=13)
    # Rotate the physical sheet layer, leaving scanner context fixed in place.
    page_layer = page_layer.rotate(angle_degrees, resample=Image.Resampling.BICUBIC, fillcolor=(0, 0, 0, 0))
    background_layer = Image.new("RGBA", canvas_size, (*background, 255))
    return Image.alpha_composite(background_layer, page_layer).convert("RGB")


def _write_manifest(root, images, *, schema="book-manifest-v2", book_id="synthetic-pages"):
    root.mkdir(parents=True, exist_ok=True)
    pages = []
    for page_id, image in images:
        image_path = root / f"{page_id}.png"
        image.save(image_path)
        pages.append({"page_id": page_id, "image": image_path.name,
                      "source_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest()})
    record = {"schema": schema, "book_id": book_id, "source_dpi": 300, "pages": pages}
    if schema == "book-manifest-v1":
        (root / "raw.txt").write_text("fixture", encoding="utf-8")
        record["canonical_source"] = "raw.txt"
        for page in record["pages"]:
            page["canonical_span"] = {"start": 0, "end": 7}
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(record), encoding="utf-8")
    return manifest_path


def _run_measure(manifest_path, proposal_path, *page_ids):
    arguments = ["calibrate", "measure", "--manifest", str(manifest_path), "--output", str(proposal_path)]
    for page_id in page_ids:
        arguments.extend(["--page-id", page_id])
    return cli.main(arguments)


@pytest.mark.parametrize("background", [(255, 255, 255), (0, 0, 0), (250, 250, 250)])
def test_translated_page_is_measured_against_light_and_dark_scanner_beds(background):
    result = measure_page_interior(_synthetic_scan(background=background, page_box=(170, 155, 670, 855)))

    assert result.status == "measured"
    assert result.content_bounds is not None
    x0, y0, x1, y1 = result.content_bounds
    assert 165 <= x0 <= 180
    assert 150 <= y0 <= 165
    assert 660 <= x1 <= 680
    assert 845 <= y1 <= 865
    assert set(result.edges) == {"top", "bottom", "left", "right"}
    assert all(edge["status"] == "supported" for edge in result.edges.values())


@pytest.mark.parametrize("source_rotation", [-1.2, 1.2])
def test_small_rigid_rotation_uses_page_edges_with_correct_correction_sign(source_rotation):
    result = measure_page_interior(_synthetic_scan(angle_degrees=source_rotation))

    assert result.status == "measured"
    # PIL's positive rotation is counter-clockwise; the profile stores the
    # clockwise correction needed to return the page to its raster frame.
    assert result.deskew_degrees_clockwise == pytest.approx(source_rotation, abs=0.16)
    assert result.uncertainty["edge_orientation_spread_degrees"] < 0.20


def test_edge_shadow_and_near_edge_printed_mark_remain_measurable():
    result = measure_page_interior(_synthetic_scan(edge_shadow_px=10, content="near_edge"))

    assert result.content_bounds is not None
    left, top, right, bottom = result.content_bounds
    assert left >= 0 and top >= 0
    assert right <= 900 and bottom <= 1100
    # A near-edge printed mark remains within the proposed crop.
    assert left < 130 + 18
    assert top < 120 + 40


def test_raster_clipped_sheet_edge_is_reported_as_partial_evidence():
    result = measure_page_interior(_synthetic_scan(page_box=(0, 120, 690, 900)))

    assert result.status == "partial"
    assert result.content_bounds is not None
    assert result.edges["left"]["status"] == "unobserved_raster_clip"
    assert "page_edge_not_visible" in result.failures


def test_non_rectangular_edge_evidence_leaves_rigid_orientation_unresolved():
    image = Image.new("RGB", (900, 1100), "black")
    ImageDraw.Draw(image).polygon(
        [(130, 120), (690, 120), (620, 900), (180, 900)],
        fill=(247, 242, 228),
    )

    result = measure_page_interior(image)

    assert result.deskew_degrees_clockwise is None
    assert "orientation_unresolved" in result.failures
    assert result.status == "partial"


def test_sparse_and_large_internal_blank_pages_use_the_page_surface_not_ink_bounds():
    sparse = measure_page_interior(_synthetic_scan(content="sparse"))
    blank = measure_page_interior(_synthetic_scan(content="blank"))

    assert sparse.content_bounds is not None
    assert blank.content_bounds is not None
    for bounds in (sparse.content_bounds, blank.content_bounds):
        assert bounds[0] < 150
        assert bounds[1] < 140
        assert bounds[2] > 680
        assert bounds[3] > 890


def test_highlighting_does_not_materially_move_the_measured_sheet_boundary():
    plain = measure_page_interior(_synthetic_scan())
    highlighted = measure_page_interior(_synthetic_scan(highlighted=True))

    assert plain.content_bounds is not None and highlighted.content_bounds is not None
    assert all(abs(a - b) <= 2 for a, b in zip(plain.content_bounds, highlighted.content_bounds, strict=True))


def test_page_with_no_visible_boundary_is_explicitly_unresolved():
    image = Image.new("RGB", (900, 1100), (247, 242, 228))

    result = measure_page_interior(image)

    assert result.status == "unresolved"
    assert result.content_bounds is None
    assert "background_indistinguishable" in result.failures


def test_white_page_on_indistinguishable_white_bed_is_unresolved_without_a_guessed_crop():
    image = Image.new("RGB", (900, 1100), (255, 255, 255))

    result = measure_page_interior(image)

    assert result.status == "unresolved"
    assert result.content_bounds is None
    assert "background_indistinguishable" in result.failures


def test_neutral_white_page_on_dark_bed_is_unresolved_by_current_chroma_method():
    image = Image.new("RGB", (900, 1100), (0, 0, 0))
    ImageDraw.Draw(image).rectangle((130, 120, 690, 900), fill=(255, 255, 255))

    result = measure_page_interior(image)

    assert result.status == "unresolved"
    assert result.content_bounds is None
    assert "background_indistinguishable" in result.failures


def test_measure_emits_core_proposal_and_exact_evidence_digest_then_accepts_and_freezes(tmp_path):
    manifest_path = _write_manifest(tmp_path / "book", [("page-001", _synthetic_scan(angle_degrees=0.7))])
    proposal_path = tmp_path / "proposal.json"
    assert _run_measure(manifest_path, proposal_path) == 0
    evidence_path = proposal_path.with_suffix(".json.observations.json")
    proposal_bytes = proposal_path.read_bytes()
    evidence_bytes = evidence_path.read_bytes()
    manifest = load_manifest(manifest_path)
    proposal = load_calibration_proposal(proposal_path, manifest)
    values = proposal.pages[0]["values"]

    assert proposal.producer["source"] == "detector"
    assert proposal.producer["method"] == "lab-paper-chroma-largest-component-v1"
    assert proposal.producer["evidence_sha256"] == hashlib.sha256(evidence_bytes).hexdigest()
    assert "human review" in proposal.producer["note"]
    assert "content_bounds" in values and "deskew_degrees" in values
    assert "orientation_degrees" not in values
    assert not (tmp_path / "profile.json").exists()

    draft_path = tmp_path / "draft.json"
    assert cli.main(["calibrate", "draft", "--manifest", str(manifest_path),
                     "--profile-id", "synthetic", "--output", str(draft_path)]) == 0
    accepted_path = tmp_path / "accepted.json"
    assert cli.main(["calibrate", "accept", "--manifest", str(manifest_path),
        "--profile", str(draft_path), "--proposal", str(proposal_path),
        "--all", "--all-fields", "--output", str(accepted_path)]) == 0
    acceptance = json.loads(accepted_path.with_suffix(".json.acceptance.json").read_text())
    profile = load_profile(accepted_path)
    accepted_page = profile.page_calibrations["page-001"]
    assert accepted_page.content_bounds == tuple(values["content_bounds"])
    assert accepted_page.source == "human"
    assert proposal.proposal_id in accepted_page.note
    assert proposal.producer["method"] in accepted_page.note
    assert proposal.producer["evidence_sha256"] in accepted_page.note
    assert acceptance["proposal_id"] == proposal.proposal_id

    frozen_path = tmp_path / "frozen.json"
    assert cli.main(["calibrate", "freeze", "--manifest", str(manifest_path),
                     "--profile", str(accepted_path), "--output", str(frozen_path)]) == 0
    assert load_profile(frozen_path).state == "frozen"
    assert proposal_path.read_bytes() == proposal_bytes
    assert evidence_path.read_bytes() == evidence_bytes


def test_partial_bounds_remain_proposable_and_acceptance_does_not_change_evidence(tmp_path):
    manifest_path = _write_manifest(
        tmp_path / "clipped", [("page-clipped", _synthetic_scan(page_box=(0, 120, 690, 900)))],
    )
    proposal_path = tmp_path / "partial-proposal.json"
    assert _run_measure(manifest_path, proposal_path) == 0
    evidence_path = proposal_path.with_suffix(".json.observations.json")
    evidence_before = evidence_path.read_bytes()
    proposal_before = proposal_path.read_bytes()
    evidence = json.loads(evidence_before)
    manifest = load_manifest(manifest_path)
    proposal = load_calibration_proposal(proposal_path, manifest)

    observation = evidence["observations"][0]
    assert observation["status"] == "partial"
    assert observation["edges"]["left"]["status"] == "unobserved_raster_clip"
    assert observation["content_bounds"] is not None
    assert proposal.pages[0]["values"]["content_bounds"] == observation["content_bounds"]

    draft_path = tmp_path / "partial-draft.json"
    cli.main(["calibrate", "draft", "--manifest", str(manifest_path),
              "--profile-id", "partial", "--output", str(draft_path)])
    accepted_path = tmp_path / "partial-accepted.json"
    assert cli.main(["calibrate", "accept", "--manifest", str(manifest_path),
        "--profile", str(draft_path), "--proposal", str(proposal_path),
        "--page-id", "page-clipped", "--field", "content-bounds",
        "--output", str(accepted_path)]) == 0
    accepted = load_profile(accepted_path).page_calibrations["page-clipped"]
    assert accepted.content_bounds == tuple(observation["content_bounds"])
    assert accepted.content_status == "measured"
    assert accepted.source == "human"
    assert proposal.proposal_id in accepted.note
    assert evidence_path.read_bytes() == evidence_before
    assert proposal_path.read_bytes() == proposal_before
    assert json.loads(evidence_path.read_bytes())["observations"][0]["status"] == "partial"


def test_unresolved_deskew_is_omitted_and_all_fields_accepts_only_bounds(tmp_path):
    image = Image.new("RGB", (900, 1100), "black")
    ImageDraw.Draw(image).polygon(
        [(130, 120), (690, 120), (620, 900), (180, 900)], fill=(247, 242, 228),
    )
    manifest_path = _write_manifest(tmp_path / "unresolved", [("page-skew", image)])
    proposal_path = tmp_path / "unresolved-proposal.json"
    assert _run_measure(manifest_path, proposal_path) == 0
    evidence_path = proposal_path.with_suffix(".json.observations.json")
    evidence = json.loads(evidence_path.read_text())
    proposal = load_calibration_proposal(proposal_path, load_manifest(manifest_path))
    observation = evidence["observations"][0]

    assert observation["status"] == "partial"
    assert "orientation_unresolved" in observation["failures"]
    assert "content_bounds" in proposal.pages[0]["values"]
    assert "deskew_degrees" not in proposal.pages[0]["values"]
    assert "orientation_degrees" not in proposal.pages[0]["values"]

    draft_path = tmp_path / "unresolved-draft.json"
    cli.main(["calibrate", "draft", "--manifest", str(manifest_path),
              "--profile-id", "unresolved", "--output", str(draft_path)])
    accepted_path = tmp_path / "unresolved-accepted.json"
    assert cli.main(["calibrate", "accept", "--manifest", str(manifest_path),
        "--profile", str(draft_path), "--proposal", str(proposal_path),
        "--all", "--all-fields", "--output", str(accepted_path)]) == 0
    accepted = load_profile(accepted_path).page_calibrations["page-skew"]
    assert accepted.content_bounds == tuple(observation["content_bounds"])
    assert accepted.deskew_degrees is None and accepted.deskew_status == "unresolved"
    assert accepted.orientation_degrees is None and accepted.orientation_status == "unresolved"


def test_no_candidate_writes_evidence_returns_review_status_without_proposal(tmp_path, capsys):
    white_page_on_black = Image.new("RGB", (900, 1100), "black")
    ImageDraw.Draw(white_page_on_black).rectangle((130, 120, 690, 900), fill="white")
    manifest_path = _write_manifest(tmp_path / "no-candidate", [("page-white", white_page_on_black)])
    proposal_path = tmp_path / "no-candidates.json"

    assert _run_measure(manifest_path, proposal_path) == 3
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "no_candidates"
    assert result["proposal"] is None
    assert result["pages_without_generic_proposal_values"] == 1
    assert proposal_path.with_suffix(".json.observations.json").is_file()
    assert not proposal_path.exists()


def test_selected_page_order_follows_manifest_and_duplicate_ids_are_rejected(tmp_path):
    manifest_path = _write_manifest(tmp_path / "ordered", [
        ("page-a", _synthetic_scan()), ("page-b", _synthetic_scan(page_box=(150, 130, 700, 890))),
    ])
    proposal_path = tmp_path / "ordered-proposal.json"
    assert _run_measure(manifest_path, proposal_path, "page-b", "page-a") == 0
    evidence = json.loads(proposal_path.with_suffix(".json.observations.json").read_text())
    proposal = load_calibration_proposal(proposal_path, load_manifest(manifest_path))
    assert [row["page_id"] for row in evidence["observations"]] == ["page-a", "page-b"]
    assert [row["page_id"] for row in proposal.pages] == ["page-a", "page-b"]

    assert _run_measure(manifest_path, tmp_path / "duplicate.json", "page-a", "page-a") == 2


def test_measure_rejects_v1_manifest_and_hash_mismatch(tmp_path):
    image = _synthetic_scan()
    legacy_path = _write_manifest(tmp_path / "legacy", [("page-old", image)], schema="book-manifest-v1")
    assert _run_measure(legacy_path, tmp_path / "legacy-proposal.json") == 2

    current_path = _write_manifest(tmp_path / "hash", [("page-hash", image)])
    changed = tmp_path / "hash" / "page-hash.png"
    changed.write_bytes(b"changed source bytes")
    assert _run_measure(current_path, tmp_path / "hash-proposal.json") == 2
