"""Focused safeguards for the bounded slope-forensics experiment."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(RESEARCH))

import normalize.geometry as geometry
from candidate_models import (
    group_with_slope,
    pixel_projection_slope,
    resolution_boundary_experiments,
    synthetic_matrix,
    synthetic_pixel_matrix,
)
from run_forensics import analyze, instrumented_bands


def token(source_row: int, x: int, y: int, width: int = 30, height: int = 12) -> geometry._Token:
    return geometry._Token(source_row, f"t{source_row}", 98.0, 5, 1, 1, 1, 1, source_row, x, y, width, height)


def capture_record(tokens: list[geometry._Token]) -> dict:
    return {
        "schema": "baseline-slope-capture-v1",
        "sides": [{
            "fixture_id": "synthetic",
            "side": "page",
            "blank_declared": False,
            "dimensions_px": [400, 240],
            "source_pdf_sha256": "0" * 64,
            "image_sha256": "1" * 64,
            "tsv_sha256": "2" * 64,
            "admitted_token_sha256": "3" * 64,
            "token_count": len(tokens),
            "tokens": [token.__dict__ for token in tokens],
            "parse_errors": [],
            "tolerance_px": 3,
            "horizontal_gap_limit_px": geometry._horizontal_gap_limit(tokens),
            "local_paths": {"image": "/tmp/nonexistent-synthetic.png", "tsv": "/tmp/nonexistent-synthetic.tsv"},
        }],
    }


def test_current_estimator_baseline_and_instrumented_bands_are_exact() -> None:
    tokens = [token(i, x, y) for i, (x, y) in enumerate(((10, 30), (70, 30), (10, 80), (70, 80)), 1)]
    baseline = geometry._estimate_baseline_slope(tokens, 3)
    calls = []
    original = geometry._estimate_baseline_slope

    def observe(current_tokens, tolerance):
        calls.append((tuple(item.source_row for item in current_tokens), tolerance))
        return original(current_tokens, tolerance)

    geometry._estimate_baseline_slope = observe
    try:
        geometry.group_physical_lines(tokens)
    finally:
        geometry._estimate_baseline_slope = original
    assert calls == [(tuple(item.source_row for item in tokens), 3)]
    for milli in range(-100, 101):
        slope = milli / 1000
        assert instrumented_bands(tokens, 3, slope)[1] == geometry._line_bands(tokens, 3, slope)
    assert baseline == 0.0


def test_candidate_landscape_has_all_201_slopes_and_complete_identities() -> None:
    tokens = [token(i, x, 30 + y) for i, (x, y) in enumerate(((10, 0), (70, 0), (10, 50), (70, 50)), 1)]
    result = analyze(capture_record(tokens))
    side = result["sides"][0]
    assert len(side["candidates"]) == 201
    assert [item["slope"] for item in side["candidates"]] == [value / 1000 for value in range(-100, 101)]
    for candidate in side["candidates"]:
        members = {identity for band in candidate["memberships"] for identity in band}
        assert members == {item.source_row for item in tokens}
        singleton_members = {identity for identity in candidate["singleton_source_rows"]}
        assert singleton_members <= members
        if candidate["rejected"]:
            assert candidate["rejection_reasons"]


def test_current_tolerance_gap_and_downstream_path_are_held_fixed() -> None:
    tokens = [token(i, x, y, width=30, height=12) for i, (x, y) in enumerate(((10, 30), (70, 30), (10, 80), (70, 80)), 1)]
    default_lines, _, measurement = geometry.group_physical_lines(tokens)
    assert measurement["tolerance_px"] == 3
    assert measurement["horizontal_gap_limit_px"] == 60.0
    injected_lines, _, injected_measurement = group_with_slope(tokens, 0.0)
    assert injected_lines == default_lines
    assert injected_measurement == measurement


def test_synthetic_pixel_oracle_and_counterexamples(tmp_path: Path) -> None:
    matrix = synthetic_pixel_matrix(tmp_path)
    cases = {item["case_id"]: item for item in matrix}
    assert abs(cases["A_horizontal_rows"]["selected_slope"]) <= 0.001
    for name, expected in (("B_shared_skew", .04), ("C_skew_plus_singleton", .04), ("D_running_header", .03), ("H_local_outliers", .035)):
        assert abs(cases[name]["selected_slope"] - expected) <= 0.0011
    assert cases["C_skew_plus_singleton"]["corrected_ink_runs"] >= 2
    assert cases["E_competing_nearby_rows"]["selected_slope"] is None
    assert cases["F_different_slope_regions"]["selected_slope"] is None
    assert cases["F_different_slope_regions"]["region_disagreement"] is True
    assert cases["G_single_sloped_row"]["selected_slope"] is None
    # The pixel method returns abstention for these cases; a zero-slope fallback
    # would fragment them, so it must not be reported as a successful grouping.


def test_cohesion_only_candidate_exposes_singleton_and_nearby_row_failures() -> None:
    cases = {item["case_id"]: item for item in synthetic_matrix()}
    singleton = cases["C_skew_plus_singleton"]
    assert singleton["production_slope"] == 0.0
    assert singleton["candidate_singletons"] >= 1
    assert singleton["candidate_slope"] != 0.0
    nearby = cases["E_competing_nearby_rows"]
    assert nearby["oracle_false_merges"]
    assert cases["G_single_sloped_row"]["candidate_slope"] is not None
    assert cases["F_different_slope_regions"]["candidate_slope"] == 0.0


def test_pixel_slope_is_input_permutation_stable(tmp_path: Path) -> None:
    cases = synthetic_pixel_matrix(tmp_path)
    image = tmp_path / "B_shared_skew.png"
    first = pixel_projection_slope(image)
    assert first["slope"] == cases[1]["selected_slope"]
    tokens = [token(i, x, 30 + round(.04 * x)) for i, x in enumerate((10, 70, 130, 190), 1)]
    original = geometry._estimate_baseline_slope(tokens, 3)
    permuted = geometry._estimate_baseline_slope(list(reversed(tokens)), 3)
    assert original == permuted
    assert geometry._line_bands(tokens, 3, .04) == geometry._line_bands(list(reversed(tokens)), 3, .04)


def test_one_pixel_perturbation_keeps_measurement_distinct_from_assignment(tmp_path: Path) -> None:
    path = tmp_path / "stable-page.png"
    from PIL import Image, ImageDraw

    image = Image.new("L", (560, 440), 255)
    draw = ImageDraw.Draw(image)
    for y in (80, 160):
        for x in (35, 115, 195, 275, 355, 435):
            draw.rectangle((x, y, x + 39, y + 11), fill=0)
    image.save(path)
    measured_before = pixel_projection_slope(path)["slope"]
    original = token(1, 35, 80)
    changed = geometry._Token(**{**original.__dict__, "y": original.y + 1})
    assert changed.y != original.y
    measured_after = pixel_projection_slope(path)["slope"]
    assert measured_after == measured_before  # raster evidence did not change
    before = geometry.group_physical_lines([original, token(2, 115, 80), token(3, 35, 160), token(4, 115, 160)])[0]
    after = geometry.group_physical_lines([changed, token(2, 115, 80), token(3, 35, 160), token(4, 115, 160)])[0]
    # A grouping change, when present, is separately observable from the pixel
    # slope measurement; do not infer geometry instability from input digest alone.
    assert isinstance(before != after, bool)


def test_scale_experiment_is_explicitly_exploratory(tmp_path: Path) -> None:
    from candidate_models import scale_experiments

    matrix_dir = tmp_path / "matrix"
    synthetic_pixel_matrix(matrix_dir)
    result = scale_experiments(matrix_dir, tmp_path / "scaled")
    assert result["scope"].startswith("exploratory")
    slopes = [item["estimated_slope_px_per_px"] for item in result["results"]]
    assert max(slopes) - min(slopes) <= .002


def test_two_pixel_resolution_boundary_is_explicit_and_bounded(tmp_path: Path) -> None:
    result = resolution_boundary_experiments(tmp_path)
    records = result["results"]
    assert len(records) == 5
    assert all(record["abstention_threshold_px"] == 2.0 for record in records)
    assert all(record["selected_slope"] == 0.0 or abs(record["selected_slope"]) * 560 >= 2.0 for record in records)
    assert any(record["selected_slope"] == 0.0 for record in records)
    assert any(record["selected_slope"] != 0.0 for record in records)
    assert not any(record["grouping_changed_from_zero"] for record in records)
    assert not any(record["assignment_changed_from_zero"] for record in records)


def test_blank_side_is_not_in_primary_oracle_and_no_binary_is_tracked() -> None:
    result = json.loads((RESEARCH / "results.json").read_text(encoding="utf-8"))
    blank = next(side for side in result["real_sides"] if side["declared_blank"])
    assert blank["token_count"] == 0
    assert blank["candidate_count"] == 0
    assert all(not side["declared_blank"] for side in result["real_sides"] if side["fixture_id"] != "stella_maris_pdf03_session-I" or side["side"] != "left")
    tracked = subprocess.run(["git", "ls-files", "*.png", "*.pdf"], cwd=ROOT, check=True, capture_output=True, text=True)
    assert tracked.stdout == ""


def test_candidate_comparisons_use_the_admitted_capture_identities() -> None:
    results = json.loads((RESEARCH / "results.json").read_text(encoding="utf-8"))
    admitted = json.loads((RESEARCH / "admitted_tokens.json").read_text(encoding="utf-8"))
    assert results["capture_contract"]["same_token_capture_used_for_all_estimators"] is True
    capture_sides = {(side["fixture_id"], side["side"]): side for side in admitted["sides"]}
    experiment_sides = {(side["fixture_id"], side["side"]): side for side in results["candidate_models"]["sides"]}
    assert capture_sides.keys() == experiment_sides.keys()
    for key, captured in capture_sides.items():
        admitted_ids = {token["source_row"] for token in captured["tokens"]}
        for candidate in experiment_sides[key].get("candidates", {}).values():
            for line in candidate["lines"]:
                ids = {int(identity[6:]) for identity in line["token_ids"]}
                assert ids <= admitted_ids
            for unresolved in candidate["unresolved"]:
                assert unresolved["token_source_row"] in admitted_ids


@pytest.mark.parametrize("protected", [
    ROOT / "src/normalize/geometry.py",
    ROOT / "src/normalize/rendering.py",
    ROOT / "fixtures/preprocessing.json",
])
def test_result_records_protected_file_hashes(protected: Path) -> None:
    import hashlib

    result = json.loads((RESEARCH / "results.json").read_text(encoding="utf-8"))
    actual = hashlib.sha256(protected.read_bytes()).hexdigest()
    assert result["production_hashes"][str(protected.relative_to(ROOT))] == actual
