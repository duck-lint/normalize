from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from normalize.fixtures import FixtureCatalog
from normalize.rendering import PreprocessingConfigError, SUCCESS, load_preprocessing_config, preprocess_fixture

ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "fixtures" / "preprocessing.json"
FIXTURE = "relativity_pdf10_pp26-27"


def _variant(tmp_path: Path, **profile_updates) -> Path:
    record = json.loads(CONFIG.read_text())
    record["profiles"][FIXTURE].update(profile_updates)
    path = tmp_path / "variant.json"
    path.write_text(json.dumps(record))
    return path


def _run(config: Path, out: Path) -> dict:
    return preprocess_fixture(FixtureCatalog.load(ROOT).get(FIXTURE), config, out)


def test_rotation_is_after_exact_crop_and_before_downsampling(tmp_path, monkeypatch):
    events = []
    original_crop = Image.Image.crop
    original_rotate = Image.Image.rotate
    original_resize = Image.Image.resize

    def crop(image, box=None):
        events.append(("crop", box))
        return original_crop(image, box)

    def rotate(image, angle, **kwargs):
        events.append(("rotate", angle, kwargs))
        return original_rotate(image, angle, **kwargs)

    def resize(image, size, **kwargs):
        events.append(("resize", size, kwargs))
        return original_resize(image, size, **kwargs)

    monkeypatch.setattr(Image.Image, "crop", crop)
    monkeypatch.setattr(Image.Image, "rotate", rotate)
    monkeypatch.setattr(Image.Image, "resize", resize)
    result = _run(CONFIG, tmp_path / "out")
    assert result["status"] == SUCCESS
    assert max(i for i, item in enumerate(events) if item[0] == "crop") < next(
        i for i, item in enumerate(events) if item[0] == "rotate"
    )
    assert next(i for i, item in enumerate(events) if item[0] == "rotate") < next(
        i for i, item in enumerate(events) if item[0] == "resize"
    )
    rotation = next(item for item in events if item[0] == "rotate")
    assert rotation[1] == -0.6
    assert rotation[2]["resample"] == Image.Resampling.BICUBIC
    assert rotation[2]["expand"] is True
    assert rotation[2]["fillcolor"] == (255, 255, 255)


def test_missing_rotation_and_explicit_zero_are_exact_noop_operations(tmp_path, monkeypatch):
    calls = []
    original_rotate = Image.Image.rotate

    def rotate(image, angle, **kwargs):
        calls.append(angle)
        return original_rotate(image, angle, **kwargs)

    monkeypatch.setattr(Image.Image, "rotate", rotate)
    record = json.loads(CONFIG.read_text())
    record["profiles"][FIXTURE]["page_rotations"] = {"right": 0.0}
    path = tmp_path / "controls.json"
    path.write_text(json.dumps(record))
    result = _run(path, tmp_path / "out")
    pages = {page["side"]: page for page in result["pages"]}
    assert result["status"] == SUCCESS
    assert pages["left"]["rotation_status"] == "not_configured"
    assert pages["left"]["rotation"]["operation"] == "not_configured"
    assert pages["right"]["rotation_status"] == "configured"
    assert pages["right"]["rotation_angle_degrees_counterclockwise"] == 0.0
    assert pages["right"]["rotation"]["operation"] == "none"
    assert calls == []


def test_left_and_right_angles_are_independent_and_metadata_is_auditable(tmp_path):
    result = _run(CONFIG, tmp_path / "out")
    pages = {page["side"]: page for page in result["pages"]}
    assert pages["left"]["rotation_angle_degrees_counterclockwise"] == -0.6
    assert pages["right"]["rotation_angle_degrees_counterclockwise"] == -1.9
    assert pages["left"]["page_crop"]["rect_px"] == [201, 483, 1334, 2175]
    assert pages["right"]["page_crop"]["rect_px"] == [0, 59, 1158, 2106]
    assert pages["left"]["working_render_dpi"] == pages["right"]["working_render_dpi"] == 300
    assert pages["left"]["output_dpi"] == pages["right"]["output_dpi"] == result["dpi"] == 144
    assert pages["left"]["rotation"]["parameters"]["expand"] is True
    assert pages["left"]["rotation"]["parameters"]["fill_rgb"] == [255, 255, 255]
    assert pages["left"]["downsample"]["operation"] == "lanczos"
    assert result["pages"][0]["working_render_dpi"] == 300
    assert [page["side"] for page in result["pages"]] == ["left", "right"]


@pytest.mark.parametrize("angle", [True, "1", float("inf"), float("nan"), 46, -46, 10**1000])
def test_rotation_angle_must_be_finite_numeric_and_bounded(tmp_path, angle):
    path = _variant(tmp_path, page_rotations={"left": angle})
    with pytest.raises(PreprocessingConfigError, match="page_rotations"):
        load_preprocessing_config(path)


def test_invalid_rotation_side_is_rejected(tmp_path):
    path = _variant(tmp_path, page_rotations={"center": 1.0})
    with pytest.raises(PreprocessingConfigError, match="only "):
        load_preprocessing_config(path)


def test_page_profile_applies_its_configured_rotation(tmp_path):
    path = _variant(
        tmp_path,
        result_kind="page",
        split_boundary=None,
        output_order=["page"],
        blank_sides=[],
        page_crops={"page": [0, 0, 1000, 1000]},
        page_rotations={"page": 0.25},
    )
    assert load_preprocessing_config(path).profile_for(FIXTURE).page_rotations == {"page": 0.25}
    result = _run(path, tmp_path / "page-result")
    assert result["status"] == SUCCESS
    assert result["pages"][0]["side"] == "page"
    assert result["pages"][0]["rotation_angle_degrees_counterclockwise"] == 0.25
    assert result["pages"][0]["rotation"]["operation"] == "rotate"


def test_production_geometry_and_source_pdfs_are_unchanged_and_no_binaries_are_tracked(tmp_path):
    geometry_path = ROOT / "src/normalize/geometry.py"
    expected_geometry = subprocess.check_output(
        ["git", "show", "HEAD:src/normalize/geometry.py"], cwd=ROOT
    )
    assert geometry_path.read_bytes() == expected_geometry
    metadata = FixtureCatalog.load(ROOT).get(FIXTURE)
    source_hash_before = hashlib.sha256(metadata.source_pdf.read_bytes()).hexdigest()
    assert _run(CONFIG, tmp_path / "source-integrity")["status"] == SUCCESS
    assert hashlib.sha256(metadata.source_pdf.read_bytes()).hexdigest() == source_hash_before
    tracked = subprocess.check_output(["git", "ls-files", "*.png", "*.pdf"], cwd=ROOT, text=True)
    assert tracked == ""
