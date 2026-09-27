from __future__ import annotations

import hashlib
import json
import math
import sys
from fractions import Fraction
from pathlib import Path

import pymupdf
import pytest
from PIL import Image

from normalize.fixtures import FixtureCatalog
from normalize.rendering import (
    FAILURE,
    SUCCESS,
    PreprocessingConfigError,
    _preprocess_image,
    load_preprocessing_config,
    preprocess_fixture,
)


ROOT = Path(__file__).parents[1]
CONFIG_PATH = ROOT / "fixtures" / "preprocessing.json"
BOUNDS_PATH = ROOT / "fixtures" / "page-crop-bounds.json"
MANUAL_CROPS = ROOT / "tests" / "fixtures" / "manual-page-crops"
sys.path.insert(0, str(ROOT / "tests" / "support"))
from crop_recovery import find_exact_subcrop_bounds


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_variant(tmp_path: Path, fixture_id: str, **updates) -> Path:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    config["profiles"][fixture_id].update(updates)
    path = tmp_path / f"{fixture_id}-variant.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def _run(fixture_id: str, config_path: Path, output_dir: Path) -> dict:
    metadata = FixtureCatalog.load(ROOT).get(fixture_id)
    return preprocess_fixture(metadata, config_path, output_dir)


def test_all_twelve_manual_crops_recover_uniquely_from_canonical_source_renders(tmp_path: Path):
    """Regenerate canonical 300-DPI sides from the exact PDFs before matching."""
    bounds_record = json.loads(BOUNDS_PATH.read_text(encoding="utf-8"))
    assert len(bounds_record["records"]) == 12
    config = load_preprocessing_config(CONFIG_PATH)
    catalog = FixtureCatalog.load(ROOT)

    for fixture_id in config.profiles:
        metadata = catalog.get(fixture_id)
        source_hash = _sha256(metadata.source_pdf)
        side_recorded = [
            item for item in bounds_record["records"] if item["fixture_id"] == fixture_id
        ]
        assert {item["side"] for item in side_recorded} == {"left", "right"}
        assert all(item["fixture_pdf_sha256"] == source_hash for item in side_recorded)

        with pymupdf.open(metadata.source_pdf) as document:
            page = document.load_page(metadata.fixture_pdf_page_index_1_based - 1)
            pixmap = page.get_pixmap(
                matrix=pymupdf.Matrix(300 / 72, 300 / 72),
                alpha=False,
                annots=False,
            )
            rendered = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
        transformed, _ = _preprocess_image(rendered, config.profile_for(fixture_id))
        split_x = config.profile_for(fixture_id).split_boundary * 300 // config.dpi
        canonical_sides = {
            "left": transformed.crop((0, 0, split_x, transformed.height)),
            "right": transformed.crop((split_x, 0, transformed.width, transformed.height)),
        }

        for record in side_recorded:
            side = record["side"]
            canonical_path = tmp_path / f"{fixture_id}.{side}.canonical.png"
            canonical_sides[side].save(canonical_path, format="PNG")
            assert _sha256(canonical_path) == record["canonical_sha256"]

            manual_path = MANUAL_CROPS / f"{fixture_id}.{side}.png"
            assert _sha256(manual_path) == record["manual_crop_sha256"]
            with Image.open(manual_path) as manual:
                assert list(manual.size) == record["manual_crop_dimensions_px"]
                assert manual.mode == "RGBA"
                assert manual.getchannel("A").getextrema() == (255, 255)
                # The existing matcher requires RGB. Dropping fully opaque alpha
                # in a temporary copy preserves the user's saved manual raster.
                rgb_path = tmp_path / f"{fixture_id}.{side}.rgb.png"
                manual.convert("RGB").save(rgb_path, format="PNG")

            recovered = find_exact_subcrop_bounds(canonical_path, rgb_path)
            assert recovered == record["recovered_300dpi_bounds_exclusive"]
            assert record["exact_match_status"] == "pass"
            assert record["unique_match_status"] == "pass"


def test_recorded_bounds_and_configured_rectangles_are_deterministic():
    record = json.loads(BOUNDS_PATH.read_text(encoding="utf-8"))
    config = load_preprocessing_config(CONFIG_PATH)
    assert record["coordinate_mapping"] == "exact production edge = reference edge * 12/25"
    for item in record["records"]:
        converted = []
        for boundary in item["boundary_conversion"]:
            exact = Fraction(boundary["reference_300dpi_px"] * 12, 25)
            assert boundary["exact_production_144dpi_px"] == f"{exact.numerator}/{exact.denominator}"
            expected = (
                math.floor(exact) if boundary["role"] == "leading" else math.ceil(exact)
            )
            assert boundary["configured_production_px"] == expected
            error = Fraction(boundary["rounding_error_144dpi_px"])
            assert error == expected - exact
            converted.append(expected)
        assert converted == item["configured_production_bounds_px"]
        assert list(config.profile_for(item["fixture_id"]).page_crops[item["side"]]) == converted


def test_containment_rounding_keeps_each_exact_physical_interval_inside():
    record = json.loads(BOUNDS_PATH.read_text(encoding="utf-8"))
    for item in record["records"]:
        edges = item["recovered_300dpi_bounds_exclusive"]
        exact = [Fraction(edge * 12, 25) for edge in edges]
        configured = item["configured_production_bounds_px"]
        assert configured[0] <= exact[0] < configured[0] + 1
        assert configured[1] <= exact[1] < configured[1] + 1
        assert configured[2] - 1 < exact[2] <= configured[2]
        assert configured[3] - 1 < exact[3] <= configured[3]


def test_spread_profiles_require_independent_left_and_right_crop_rectangles():
    config = load_preprocessing_config(CONFIG_PATH)
    profile = config.profile_for("relativity_pdf10_pp26-27")
    assert profile.page_crops == {"left": (96, 231, 641, 1044), "right": (0, 28, 556, 1011)}
    assert profile.page_crops["left"] != profile.page_crops["right"]


def test_different_side_crop_dimensions_and_post_split_provenance_are_supported(tmp_path: Path):
    fixture_id = "relativity_pdf10_pp26-27"
    result = _run(fixture_id, CONFIG_PATH, tmp_path / "run")
    assert result["status"] == SUCCESS
    pages = {page["side"]: page for page in result["pages"]}
    assert (pages["left"]["width_px"], pages["left"]["height_px"]) == (545, 813)
    assert (pages["right"]["width_px"], pages["right"]["height_px"]) == (556, 983)
    assert pages["left"]["pre_page_crop_dimensions_px"] == [792, 1224]
    assert pages["right"]["pre_page_crop_dimensions_px"] == [792, 1224]
    assert pages["left"]["page_crop"] == {
        "operation": "crop",
        "coordinate_system": "post_split_side_local_px",
        "rect_px": [96, 231, 641, 1044],
        "input_dimensions_px": [792, 1224],
        "output_dimensions_px": [545, 813],
    }
    assert result["transforms"]["split"]["parameters"]["left_source_rect_px"] == [0, 0, 792, 1224]
    assert result["transforms"]["split"]["parameters"]["right_source_rect_px"] == [792, 0, 1584, 1224]
    assert pages["left"]["source_rect_px"] == [0, 0, 792, 1224]
    assert pages["left"]["retained_rect_relative_to_side_px"] == [96, 231, 641, 1044]
    assert pages["left"]["source_page_mapping"]["fixture_pdf_page_index_1_based"] == 1


def test_page_crop_uses_side_local_coordinates_after_split(tmp_path: Path):
    fixture_id = "relativity_pdf10_pp26-27"
    result = _run(fixture_id, CONFIG_PATH, tmp_path / "run")
    left = next(page for page in result["pages"] if page["side"] == "left")
    right = next(page for page in result["pages"] if page["side"] == "right")
    assert left["page_crop"]["coordinate_system"] == "post_split_side_local_px"
    assert left["page_crop"]["rect_px"] == [96, 231, 641, 1044]
    assert right["page_crop"]["rect_px"] == [0, 28, 556, 1011]
    assert result["transforms"]["split"]["parameters"]["split_x"] == 792


def test_changing_left_crop_does_not_change_right_crop_coordinates_or_pixels(tmp_path: Path):
    fixture_id = "relativity_pdf10_pp26-27"
    base_dir = tmp_path / "base"
    base = _run(fixture_id, CONFIG_PATH, base_dir)
    changed_config = _write_variant(
        tmp_path,
        fixture_id,
        page_crops={"left": [10, 20, 300, 500], "right": [0, 28, 556, 1011]},
    )
    changed_dir = tmp_path / "changed"
    changed = _run(fixture_id, changed_config, changed_dir)
    base_right = next(page for page in base["pages"] if page["side"] == "right")
    changed_right = next(page for page in changed["pages"] if page["side"] == "right")
    assert base_right["page_crop"]["rect_px"] == changed_right["page_crop"]["rect_px"]
    assert _sha256(base_dir / base_right["output_path"]) == _sha256(
        changed_dir / changed_right["output_path"]
    )


def test_out_of_bounds_page_crop_is_rejected_after_side_split_and_cleans_outputs(tmp_path: Path):
    fixture_id = "relativity_pdf10_pp26-27"
    output_dir = tmp_path / "out-of-bounds"
    bad_config = _write_variant(
        tmp_path,
        fixture_id,
        page_crops={"left": [0, 0, 793, 20], "right": [0, 0, 556, 1011]},
    )
    result = _run(fixture_id, bad_config, output_dir)
    assert result["status"] == FAILURE
    assert result["error"]["code"] == "invalid_config"
    assert "outside its post-split side raster" in result["error"]["reason"]
    assert not list(output_dir.glob("*.png"))


@pytest.mark.parametrize(
    "rect",
    (
        [0, 0, 0, 2],
        [0, 2, 3, 2],
        [False, 0, 3, 4],
        [0, 0, 3.0, 4],
        "0,0,3,4",
        [0, 0, 3],
    ),
)
def test_zero_area_and_malformed_page_crop_values_are_rejected(tmp_path: Path, rect):
    fixture_id = "relativity_pdf10_pp26-27"
    path = _write_variant(
        tmp_path,
        fixture_id,
        page_crops={"left": rect, "right": None},
    )
    with pytest.raises(PreprocessingConfigError):
        load_preprocessing_config(path)


@pytest.mark.parametrize(
    "page_crops",
    (
        {"left": [0, 0, 10, 10]},
        {"left": [0, 0, 10, 10], "right": None, "page": None},
        {"page": [0, 0, 10, 10], "right": None},
    ),
)
def test_spread_profile_rejects_missing_or_unexpected_page_crop_keys(tmp_path: Path, page_crops):
    fixture_id = "relativity_pdf10_pp26-27"
    path = _write_variant(tmp_path, fixture_id, page_crops=page_crops)
    with pytest.raises(PreprocessingConfigError, match="page_crops must contain exactly"):
        load_preprocessing_config(path)


def test_page_profile_requires_page_key_and_rejects_spread_keys(tmp_path: Path):
    fixture_id = "relativity_pdf10_pp26-27"
    updates = {
        "result_kind": "page",
        "split_boundary": None,
        "output_order": ["page"],
        "blank_sides": [],
        "page_crops": {"page": [0, 0, 500, 500]},
    }
    valid = _write_variant(tmp_path, fixture_id, **updates)
    assert load_preprocessing_config(valid).profile_for(fixture_id).page_crops["page"] == (
        0,
        0,
        500,
        500,
    )
    invalid = _write_variant(
        tmp_path,
        fixture_id,
        **{**updates, "page_crops": {"left": None, "right": None}},
    )
    with pytest.raises(PreprocessingConfigError, match="page_crops must contain exactly"):
        load_preprocessing_config(invalid)


def test_page_crop_none_is_an_explicit_no_crop_operation(tmp_path: Path):
    fixture_id = "relativity_pdf10_pp26-27"
    config = _write_variant(
        tmp_path,
        fixture_id,
        page_crops={"left": None, "right": None},
    )
    result = _run(fixture_id, config, tmp_path / "none")
    assert result["status"] == SUCCESS
    for page in result["pages"]:
        assert page["page_crop"]["operation"] == "none"
        assert page["page_crop"]["rect_px"] is None
        assert page["retained_rect_relative_to_side_px"] == [0, 0, 792, 1224]


def test_page_result_configuration_and_metadata_use_page_key(tmp_path: Path):
    fixture_id = "relativity_pdf10_pp26-27"
    config = _write_variant(
        tmp_path,
        fixture_id,
        result_kind="page",
        spread_crop=None,
        page_crops={"page": [10, 20, 800, 1000]},
        split_boundary=None,
        output_order=["page"],
        blank_sides=[],
    )
    result = _run(fixture_id, config, tmp_path / "page")
    assert result["status"] == SUCCESS
    assert result["pages"][0]["side"] == "page"
    assert result["pages"][0]["page_crop"]["rect_px"] == [10, 20, 800, 1000]
    assert result["output_files"]["page"].endswith(".page.png")


def test_blank_left_identity_survives_its_human_crop(tmp_path: Path):
    fixture_id = "stella_maris_pdf03_session-I"
    result = _run(fixture_id, CONFIG_PATH, tmp_path / "blank")
    left = next(page for page in result["pages"] if page["side"] == "left")
    assert left["blank"] is True
    assert left["page_crop"]["rect_px"] == [26, 77, 672, 1068]
    assert left["page_crop"]["operation"] == "crop"


@pytest.mark.parametrize(
    "fixture_id",
    (
        "relativity_pdf10_pp26-27",
        "relativity_pdf17_pp40-41",
        "relativity_pdf23_pp52-53",
        "stella_maris_pdf03_session-I",
        "stella_maris_pdf06_dense-dialogue",
        "stella_maris_pdf18_session-II_p35",
    ),
)
def test_output_order_and_crop_outputs_are_deterministic(tmp_path: Path, fixture_id: str):
    first_dir, second_dir = tmp_path / "first", tmp_path / "second"
    first = _run(fixture_id, CONFIG_PATH, first_dir)
    second = _run(fixture_id, CONFIG_PATH, second_dir)
    assert [page["side"] for page in first["pages"]] == ["left", "right"]
    assert [page["side"] for page in second["pages"]] == ["left", "right"]
    for side in ("left", "right", "spread"):
        name = first["output_files"][side]
        assert _sha256(first_dir / name) == _sha256(second_dir / name)
    assert _sha256(first_dir / f"{fixture_id}.preprocess.json") == _sha256(
        second_dir / f"{fixture_id}.preprocess.json"
    )


def test_success_then_bad_page_crop_rerun_removes_stale_outputs(tmp_path: Path):
    fixture_id = "relativity_pdf10_pp26-27"
    output_dir = tmp_path / "rerun"
    assert _run(fixture_id, CONFIG_PATH, output_dir)["status"] == SUCCESS
    bad_config = _write_variant(
        tmp_path,
        fixture_id,
        page_crops={"left": [0, 0, 900, 20], "right": [0, 0, 556, 1011]},
    )
    failed = _run(fixture_id, bad_config, output_dir)
    assert failed["status"] == FAILURE
    assert all(not (output_dir / f"{fixture_id}.{kind}.png").exists() for kind in ("left", "right", "spread"))
