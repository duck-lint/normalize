from __future__ import annotations

import hashlib
import json

import pytest
from PIL import Image, ImageDraw

from normalize import cli
from normalize.books import load_manifest, load_profile, validate_profile_for_manifest
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


def test_measure_command_writes_mutable_profile_and_preserves_human_rows_by_default(tmp_path):
    source_path = tmp_path / "page.jpg"
    _synthetic_scan().save(source_path, quality=95)
    source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({
        "schema": "book-manifest-v2",
        "book_id": "synthetic-loose-page",
        "source_dpi": 300,
        "pages": [{
            "page_id": "page-001",
            "image": source_path.name,
            "source_sha256": source_hash,
        }],
    }), encoding="utf-8")
    profile_path = tmp_path / "profile.json"

    assert cli.main([
        "calibrate", "measure", "--manifest", str(manifest_path),
        "--output", str(profile_path),
    ]) == 0
    manifest = load_manifest(manifest_path, validate_sources=False)
    profile = load_profile(profile_path)
    validate_profile_for_manifest(profile, manifest)
    assert profile.state == "draft"
    assert profile.schema == "book-profile-v2"
    assert profile.physical_manifest_sha256 == manifest.physical_sha256
    assert profile.pages[0].source == "detector"
    evidence_path = profile_path.with_suffix(".json.observations.json")
    assert evidence_path.is_file()
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["physical_manifest_sha256"] == manifest.physical_sha256
    assert evidence["observations"][0]["method"] == "lab-paper-chroma-largest-component-v1"
    assert not (tmp_path / "canonical-source-required.txt").exists()
    assert not (tmp_path / "transcript.json").exists()

    record = json.loads(profile_path.read_text(encoding="utf-8"))
    record["pages"][0]["source"] = "human"
    record["pages"][0]["note"] = "Human-reviewed crop."
    profile_path.write_text(json.dumps(record), encoding="utf-8")

    assert cli.main([
        "calibrate", "measure", "--manifest", str(manifest_path),
        "--profile", str(profile_path), "--output", str(profile_path),
    ]) == 0
    retained_human_row = load_profile(profile_path).pages[0]
    assert retained_human_row.source == "human"
    assert retained_human_row.note == "Human-reviewed crop."
    assert retained_human_row.content_bounds == profile.pages[0].content_bounds

    assert cli.main([
        "calibrate", "measure", "--manifest", str(manifest_path),
        "--profile", str(profile_path), "--replace-human", "--output", str(profile_path),
    ]) == 0
    assert load_profile(profile_path).pages[0].source == "detector"


def test_partial_measurement_keeps_bounds_in_evidence_not_profile(tmp_path):
    source_path = tmp_path / "clipped.png"
    _synthetic_scan(page_box=(0, 120, 690, 900)).save(source_path)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({
        "schema": "book-manifest-v2", "book_id": "synthetic-clipped", "source_dpi": 300,
        "pages": [{"page_id": "page-1", "image": source_path.name,
                   "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest()}],
    }), encoding="utf-8")
    profile_path = tmp_path / "profile.json"

    assert cli.main(["calibrate", "measure", "--manifest", str(manifest_path),
                     "--output", str(profile_path)]) == 0
    manifest = load_manifest(manifest_path)
    profile = load_profile(profile_path)
    evidence = json.loads(profile_path.with_suffix(".json.observations.json").read_text())
    assert evidence["observations"][0]["status"] == "partial"
    assert evidence["observations"][0]["content_bounds"] is not None
    assert profile.pages[0].content_bounds is None
    assert profile.pages[0].content_status == "unresolved"
    validate_profile_for_manifest(profile, manifest)


def test_measure_command_rejects_legacy_manifest_profile_contract(tmp_path):
    source_path = tmp_path / "scan.png"
    _synthetic_scan().save(source_path)
    manifest_path = tmp_path / "manifest-v1.json"
    manifest_path.write_text(json.dumps({
        "schema": "book-manifest-v1", "book_id": "legacy", "source_dpi": 300,
        "canonical_source": "raw.txt",
        "pages": [{"page_id": "page-1", "image": source_path.name,
                   "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest()}],
    }), encoding="utf-8")
    assert cli.main(["calibrate", "measure", "--manifest", str(manifest_path),
                     "--output", str(tmp_path / "profile.json")]) == 2
