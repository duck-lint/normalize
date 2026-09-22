"""Focused tests for the research-only pixel measurement prototype."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "research/geometry/pixel-evidence-prototype/prototype.py"
SPEC = importlib.util.spec_from_file_location("pixel_evidence_prototype", SCRIPT)
assert SPEC and SPEC.loader
prototype = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prototype)


def test_measurement_interface_returns_raw_observations_only():
    image = ROOT / "research/geometry/evidence-corrections/pixel-cases/two_ordinary_tokens_each_side__continuous.png"
    observation = prototype.measure_bridge(
        image,
        [],
        {"x0": 35, "x1": 145, "y0": 20, "y1": 30},
        {"band_y0": 20, "band_y1": 30, "baseline_y": 25.0},
    )

    assert observation["raw_observations"]
    assert "same_line" not in observation
    assert "combined_score" not in observation
    assert "assignment" not in observation


def test_synthetic_controls_and_negative_controls_are_discriminating(tmp_path):
    result = prototype.run_prototype(tmp_path, include_real=False, write_manifest=False)
    synthetic = result["synthetic"]

    assert len(synthetic["adversarial_cases"]) == 7
    assert synthetic["box_only_reference"]["complete_state_equal"]
    assert synthetic["controls"]["corrected_two_sided_pair"]["measurement_comparison"]["any_raw_difference"]
    assert synthetic["controls"]["corrected_one_sided_pair"]["measurement_comparison"]["any_raw_difference"]
    assert synthetic["controls"]["identical_pixel_negative_control"]["rejected_as_distinct"]
    assert not synthetic["controls"]["different_box_input_negative_control"]["rejected_as_same_input"]
    assert not result["geometry_module_used"]
