"""Synthetic checks for causal labels used by the research-only trace."""
from __future__ import annotations

import importlib.util
from pathlib import Path

MODULE = Path(__file__).with_name("investigate.py")
SPEC = importlib.util.spec_from_file_location("normalize_fragmentation_forensics", MODULE)
assert SPEC and SPEC.loader
study = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(study)


def token(row, x, y, width=30, height=10, text="word"):
    return study.geometry._Token(row, text, 95.0, 5, 1, 1, 1, 1, row, x, y, width, height)


def test_vertical_tolerance_is_first_split_predicate():
    left, right = token(1, 0, 0), token(2, 30, 6)
    assert len(study.geometry._line_bands([left, right], tolerance=4, slope=0.0)) == 2
    assert len(study.geometry._line_bands([left, right], tolerance=6, slope=0.0)) == 1
    assert study.diagnose_first_split_predicate(
        tesseract_emitted=True, tsv_admitted=True,
        selected_vertical_delta=6, tolerance=4,
    ) == "vertical_tolerance"


def test_nonzero_slope_would_reunite_a_split_rejected_by_selected_model():
    row = [token(i, x, x * .125) for i, x in enumerate((0, 80, 160, 240), start=1)]
    assert len(study.geometry._line_bands(row, tolerance=4, slope=0.0)) > 1
    assert len(study.geometry._line_bands(row, tolerance=4, slope=.125)) == 1
    assert study.diagnose_first_split_predicate(
        tesseract_emitted=True, tsv_admitted=True,
        selected_vertical_delta=10, tolerance=4, alternative_slope_delta=0,
    ) == "baseline_slope_model"


def test_oversized_bridge_guard_is_distinct_from_the_actual_adjacent_gap():
    band = [token(1, 0, 100, text="left"), token(2, 35, 100, text="left"),
            token(3, 70, 100, text="left"), token(4, 105, 100, text="the"),
            token(5, 141, 100, width=95, text="conclusion"), token(6, 242, 100, text="that"),
            token(7, 277, 100, text="right"), token(8, 312, 100, text="right"),
            token(9, 347, 100, text="right")]
    gap_limit = study.geometry._horizontal_gap_limit(band)
    assert gap_limit == 60
    assert study.geometry._is_oversized(band[4], gap_limit) is True
    assert study.geometry._split_horizontal_regions([band], gap_limit) == [band[:5], band[5:]]
    actual_token_gap, stale_covered_gap = 6, 107
    threshold, width = 90, 95
    assert width > threshold and actual_token_gap <= gap_limit
    assert study.diagnose_first_split_predicate(
        tesseract_emitted=True, tsv_admitted=True,
        horizontal_gap=stale_covered_gap, gap_limit=gap_limit,
        preceding_token_oversized=True, bridge_supported=False,
    ) == "oversized_bridge_guard"


def test_genuine_horizontal_gap_is_not_labeled_as_oversized_guard():
    assert study.diagnose_first_split_predicate(
        tesseract_emitted=True, tsv_admitted=True,
        horizontal_gap=75, gap_limit=60,
        preceding_token_oversized=False,
    ) == "horizontal_gap"


def test_edge_token_removal_alone_does_not_establish_geometry_correctness():
    result = study.edge_removal_claim(pixel_boundary_supported=True, token_removed=True)
    assert result["edge_noise_supported"] is True
    assert result["geometry_correctness"] == "not_established"
    assert study.edge_removal_claim(pixel_boundary_supported=False, token_removed=True)["edge_noise_supported"] is False


def test_ocr_omission_is_distinct_from_geometry_grouping_omission():
    assert study.observation_stage(tesseract_emitted=False, tsv_admitted=False, grouped=False) == "ocr_observation_missing"
    assert study.observation_stage(tesseract_emitted=True, tsv_admitted=False, grouped=False) == "tsv_admission_rejection"
    assert study.observation_stage(tesseract_emitted=True, tsv_admitted=True, grouped=False) == "geometry_grouping_omission"
