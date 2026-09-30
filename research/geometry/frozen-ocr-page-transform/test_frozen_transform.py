"""Synthetic checks for affine semantics and frozen-observation invariants."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

from affine import make_page_affine, transform_box_envelope  # noqa: E402
from normalize.geometry import _Token  # noqa: E402
import run_ablation as ablation  # noqa: E402


@pytest.mark.parametrize(("width", "height", "angle"), [(640, 480, 0), (640, 480, -0.6), (810, 1210, -1.9), (911, 607, 0.8)])
def test_affine_dimensions_and_corner_containment_match_pillow(width: int, height: int, angle: float) -> None:
    affine = make_page_affine(width, height, angle)
    image = Image.new("RGB", (width, height), "white").rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor="white")
    assert (affine.destination_width, affine.destination_height) == image.size
    corners = ((0, 0), (width, 0), (width, height), (0, height))
    transformed = [affine.apply(point) for point in corners]
    assert min(x for x, _ in transformed) >= -1e-9
    assert min(y for _, y in transformed) >= -1e-9
    assert max(x for x, _ in transformed) <= affine.destination_width + 1e-9
    assert max(y for _, y in transformed) <= affine.destination_height + 1e-9


def test_zero_degree_is_exact_identity_and_inverse_round_trips() -> None:
    affine = make_page_affine(1234, 789, 0.0)
    assert affine.matrix == ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    for point in ((0.0, 0.0), (10.25, 33.5), (1234.0, 789.0)):
        assert affine.apply(point) == point
    affine = make_page_affine(1234, 789, -1.9)
    for point in ((0.0, 0.0), (10.25, 33.5), (1234.0, 789.0)):
        recovered = affine.invert(affine.apply(point))
        assert recovered == pytest.approx(point, abs=1e-10)


def test_sign_convention_corrects_rotated_horizontal_rows() -> None:
    # The prior raster study passed the measured image-space row slope directly
    # to Pillow. The equivalent page-coordinate matrix subtracts that angle.
    original_row_angle = -1.9
    affine = make_page_affine(1000, 1400, original_row_angle)
    left_source = (100.0, 400.0)
    right_source = (900.0, 400.0 + math.tan(math.radians(original_row_angle)) * 800.0)
    left = affine.apply(left_source)
    right = affine.apply(right_source)
    transformed_angle = math.degrees(math.atan2(right[1] - left[1], right[0] - left[0]))
    assert transformed_angle == pytest.approx(0.0, abs=1e-10)


def test_aabb_envelope_contains_all_transformed_corners() -> None:
    affine = make_page_affine(500, 700, -1.9)
    x, y, width, height = transform_box_envelope(affine, (45, 62, 110, 24))
    mapped = [affine.apply(point) for point in ((45, 62), (155, 62), (155, 86), (45, 86))]
    assert x <= min(p[0] for p in mapped) and x + width >= max(p[0] for p in mapped)
    assert y <= min(p[1] for p in mapped) and y + height >= max(p[1] for p in mapped)


def test_two_rows_and_header_remain_distinct_under_small_angle_error() -> None:
    source = [
        _Token(i, text, 95.0, 5, 1, 1, 1, i, 1, x, y, w, 18)
        for i, (text, x, y, w) in enumerate([
            ("Header", 80, 60, 70), ("One", 80, 180, 35), ("row", 125, 180, 35),
            ("Two", 80, 220, 35), ("row", 125, 220, 35),
        ], start=1)
    ]
    partitions = []
    for angle in (-0.2, 0.0, 0.2):
        affine = make_page_affine(800, 1000, angle)
        moved, _ = ablation.transformed_tokens(source, affine)
        result = ablation.run_geometry(moved)
        partitions.append({tuple(sorted(int(x.removeprefix("token-")) for x in line["token_ids"])) for line in result["physical_lines"]})
    assert partitions[0] == partitions[1] == partitions[2]
    assert len(partitions[0]) == 3


def test_all_variants_preserve_frozen_ocr_identity() -> None:
    tokens = [_Token(4, "same", 88.0, 5, 1, 2, 3, 4, 5, 100, 200, 45, 20)]
    expected = [ablation.token_identity(token) for token in tokens]
    expected_hash = ablation.frozen_hash(tokens)
    for angle in (-2.1, -1.9, -1.7, 0.0):
        moved, _ = ablation.transformed_tokens(tokens, make_page_affine(1000, 1200, angle))
        assert [ablation.token_identity(token) for token in moved] == expected
        assert ablation.frozen_hash(tokens) == expected_hash


def test_runner_invokes_ocr_once_for_each_input_side(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Exercise the actual runner while replacing only external fixture/OCR
    # inputs. Every perturbation must derive from its one frozen TSV capture.
    monkeypatch.setattr(ablation, "FIXTURE_IDS", ("fixture",))
    monkeypatch.setattr(ablation, "ANGLE_EVIDENCE", {"fixture.left": {"angle_degrees": 0.0}, "fixture.right": {"angle_degrees": -0.2}})

    class FakeCatalog:
        @classmethod
        def load(cls, _root):
            return cls()
        def get(self, fixture_id):
            return fixture_id

    calls = []
    preprocessing_calls = []
    monkeypatch.setattr(ablation, "FixtureCatalog", FakeCatalog)
    def fake_preprocess(_fixture, _config, out_dir):
        preprocessing_calls.append(_fixture)
        out_dir.mkdir(parents=True, exist_ok=True)
        records = []
        for side in ("left", "right"):
            path = out_dir / f"{side}.png"
            Image.new("RGB", (100, 120), "white").save(path)
            records.append({"side": side, "output_path": f"{side}.png"})
        (out_dir / "fixture.preprocess.json").write_text(json.dumps({"pages": records}))
        return {"status": ablation.SUCCESS}

    monkeypatch.setattr(ablation, "preprocess_fixture", fake_preprocess)
    monkeypatch.setattr(ablation, "ROOT", ROOT)
    monkeypatch.setattr(ablation, "_prior_crosswalk", lambda *_args: None)
    monkeypatch.setattr(ablation, "pytesseract", type("OCR", (), {
        "image_to_data": staticmethod(lambda *a, **k: calls.append(1) or "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"),
        "get_tesseract_version": staticmethod(lambda: "5.3.4"),
    })())
    # parse_tsv_rows expects the production 12-column header, supplied above.
    result = ablation.run(tmp_path / "out")
    assert len(calls) == len(result["pages"]) == 2
    assert len(preprocessing_calls) == 1
    assert all(page["ocr_invocations_for_side"] == 1 for page in result["pages"])
    assert all("angle_evidence" in page for page in result["pages"])
    assert result["pages"][0]["zero_degree_output_identical"] is True
    assert all(variant["token_count"] == page["frozen_token_count"] for page in result["pages"] for variant in page["perturbations"])


def test_production_geometry_source_unchanged_from_branch_parent() -> None:
    expected = "0e0c75d1b811388d2fcf9a3051a33680e79d75bbaf309ee2f53f1bd87622ecc1"
    actual = hashlib.sha256((ROOT / "src/normalize/geometry.py").read_bytes()).hexdigest()
    assert actual == expected


def test_changed_event_enumeration_covers_each_membership_change() -> None:
    tokens = [
        _Token(1, "a", 90, 5, 1, 1, 1, 1, 1, 0, 0, 10, 10),
        _Token(2, "b", 90, 5, 1, 1, 1, 1, 2, 12, 0, 10, 10),
        _Token(3, "c", 90, 5, 1, 1, 1, 2, 1, 0, 30, 10, 10),
    ]
    before = {
        "membership_by_source_row": {"1": ["line:1"], "2": ["line:2"], "3": ["line:3"]},
        "physical_lines": [{"token_ids": ["token-0001"]}, {"token_ids": ["token-0002"]}, {"token_ids": ["token-0003"]}],
        "selected_slope_px_per_px": 0.0, "vertical_tolerance_px": 2, "horizontal_gap_limit_px": 20,
    }
    after = {
        "membership_by_source_row": {"1": ["line:1,2"], "2": ["line:1,2"], "3": ["line:3"]},
        "physical_lines": [{"token_ids": ["token-0001", "token-0002"]}, {"token_ids": ["token-0003"]}],
        "selected_slope_px_per_px": 0.0, "vertical_tolerance_px": 2, "horizontal_gap_limit_px": 20,
    }
    events = ablation.changed_events("fixture", "left", before, after, tokens, tokens, 0.0)
    changed_rows = {row for event in events for row in event["source_rows"]}
    assert changed_rows == {1, 2}


def test_no_raster_or_pdf_is_tracked() -> None:
    tracked = subprocess.run(
        ["git", "ls-files", "*.png", "*.pdf"], cwd=ROOT, text=True, capture_output=True, check=True
    ).stdout.splitlines()
    assert tracked == []
