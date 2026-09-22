"""Executable checks for the corrected, source-independent pixel evidence."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "research/geometry/evidence-corrections/pixel_experiments.py"
SPEC = importlib.util.spec_from_file_location("pixel_experiments", SCRIPT)
assert SPEC and SPEC.loader
pixel_experiments = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pixel_experiments)


def test_corrected_pairs_have_identical_boxes_and_distinct_pixel_evidence(tmp_path):
    result = pixel_experiments.run_experiment(tmp_path, write_manifest=False)

    assert len(result["pairs"]) == 2
    for pair in result["pairs"]:
        assert pair["checks"]["identical_box_input_payload"]
        assert pair["checks"]["source_pixel_arrays_differ"]
        assert pair["checks"]["bridge_roi_measurements_differ"]
        assert pair["checks"]["disconnected_case_has_empty_bridge_interval"]
        assert pair["checks"]["box_only_complete_assignment_state_equivalent"]
        assert pair["checks"]["box_only_reversed_input_stable"]
        assert pair["continuous"]["box_only_output"]["identity_complete_assignments"]


def test_identical_pixel_pair_is_rejected_by_the_discrimination_checks(tmp_path):
    result = pixel_experiments.run_experiment(tmp_path, write_manifest=False)

    rejected = result["deliberately_identical_pair_rejected"]
    assert rejected == {
        "source_pixel_arrays_differ": False,
        "bridge_roi_measurements_differ": False,
    }
