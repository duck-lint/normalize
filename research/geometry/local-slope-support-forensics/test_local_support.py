"""Focused contracts for local baseline support research."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
WORK = Path(__file__).resolve().parent
PRIOR = ROOT / "research/geometry/baseline-slope-forensics"
sys.path.insert(0, str(WORK))

import local_support
import run_forensics


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_prior_corpus_is_exact_identity_complete_37_8_1() -> None:
    prior, events, sides = run_forensics.load_inputs()
    assert len(events) == 46
    assert Counter(event["classification"] for event in events) == {
        "repaired_false_split": 37,
        "new_false_split": 8,
        "unresolved": 1,
    }
    assert len(sides) == 12
    assert prior["baseline_commit"] == "473e639b6fe335ffb527d2338234d38e311189ba"
    assert run_forensics.context_inventory(events)["all_source_identities_map_to_one_physical_context"]
    # Two candidate outcomes retain distinct event IDs for the same one physical heading context.
    assert run_forensics.context_inventory(events)["unique_physical_token_context_count"] == 45


def test_prior_adjudications_and_token_capture_are_unchanged() -> None:
    prior_results = json.loads((PRIOR / "results.json").read_text(encoding="utf-8"))
    prior_events = json.loads((PRIOR / "adjudications.json").read_text(encoding="utf-8"))["events"]
    result_events = prior_results["changed_event_summary"]["events"]
    assert prior_events == result_events
    output = json.loads((WORK / "results.json").read_text(encoding="utf-8"))
    assert output["input_contract"]["same_once_captured_tokens_reused"] is True
    assert output["input_contract"]["new_ocr_calls"] == 0
    assert output["input_contract"]["prior_adjudications_sha256"] == _sha(PRIOR / "adjudications.json")


def test_support_api_cannot_read_ocr_lexical_fields() -> None:
    class NoTextRead(dict):
        def __getitem__(self, key: str):
            if key in {"text", "text_locator", "confidence", "line_num", "block_num"}:
                raise AssertionError(f"non-geometric field accessed: {key}")
            return super().__getitem__(key)

    box = local_support.boxes_from_records([NoTextRead({"source_row": 7, "box_px": [10, 20, 30, 12], "text_locator": "ignored"})])
    assert box[0] == local_support.Box(7, 10, 20, 30, 12)
    assert set(local_support.Box.__dataclass_fields__) == {"source_row", "x", "y", "width", "height"}


def test_decision_rule_has_no_fixture_specific_branches() -> None:
    source = Path(local_support.__file__).read_text(encoding="utf-8").lower()
    assert "relativity_pdf" not in source
    assert "stella_maris" not in source
    assert "fixture_id" not in source


def test_synthetic_matrix_covers_and_passes_required_controls() -> None:
    cases = {case["case"]: case for case in run_forensics.synthetic_matrix()}
    expected = {
        "A_long_clean_sloped": "apply_slope",
        "B_short_clean_sloped": "apply_slope",
        "C_sparse_broad_sloped": "apply_slope",
        "D_curved_nonlinear": "abstain",
        "E_two_nearby_rows_same_slope": "abstain",
        "F_two_nearby_rows_different_slopes": "abstain",
        "G_one_token": "abstain",
        "G_two_tokens": "abstain",
        "H_variable_height_glyph_boxes": "apply_slope",
        "I_single_box_outlier": "apply_slope",
        "J_display_like_multiple_baselines": "abstain",
        "K_horizontal_supported_row": "reject_slope",
    }
    assert set(cases) == set(expected)
    assert all(case["decision"]["decision"] == expected[name] for name, case in cases.items())
    assert all(case["oracle_pass"] for case in cases.values())
    assert abs(cases["A_long_clean_sloped"]["decision"]["slope_px_per_px"] - 0.035) < 0.002
    assert abs(cases["C_sparse_broad_sloped"]["decision"]["slope_px_per_px"] + 0.030) < 0.002
    assert abs(cases["H_variable_height_glyph_boxes"]["decision"]["slope_px_per_px"] - 0.035) < 0.003


def test_nearby_rows_remain_distinct_when_support_abstains() -> None:
    case = next(case for case in run_forensics.synthetic_matrix() if case["case"] == "E_two_nearby_rows_same_slope")
    assert case["decision"]["decision"] == "abstain"
    assert case["measured"]["per_token_pixel_lower_envelope_fit"]["median_absolute_residual_px"] > 2.0
    record, _ = run_forensics._synthetic_row(label="nearby", rows=[
        {"xs": [25, 100, 175, 250, 325, 400, 475, 550, 625], "slope": 0.025, "base_y": 105},
        {"xs": [25, 100, 175, 250, 325, 400, 475, 550, 625], "slope": 0.025, "base_y": 132},
    ])
    from normalize.geometry import _Token, _line_bands
    tokens = [
        _Token(box["source_row"], "", 0.0, 5, 1, 1, 1, 1, 1, *box["box_px"])
        for box in record["token_boxes"]
    ]
    groups = _line_bands(tokens, tolerance=4, slope=0.025)
    assert len(groups) == 2


def test_event_artifact_has_leaveouts_scopes_and_physical_pixel_links() -> None:
    result = json.loads((WORK / "results.json").read_text(encoding="utf-8"))
    assert len(result["events"]) == 46
    assert len(result["holdout_evaluation"]["leave_one_event_out"]) == 46
    assert len(result["holdout_evaluation"]["leave_one_page_side_out"]) >= 8
    for item in result["events"]:
        feature = item["features"]
        assert set(feature["scopes"]) == {"event_only", "candidate_band", "local_x_neighborhood", "neighbor_rows"}
        assert feature["prior_page_image_sha256"]
        assert feature["local_support_decision"]["decision"] in {"apply_slope", "reject_slope", "abstain"}
        assert "token_boxes" in item["event"] and "production_grouping" in item["event"]
        assert "prior_pixel_candidate_grouping" in feature


def test_permutation_and_perturbation_semantics_are_separated() -> None:
    result = json.loads((WORK / "results.json").read_text(encoding="utf-8"))
    permutation = result["stability"]["token_permutation"]["summary"]
    assert permutation["events_tested"] == 46
    assert permutation["measurement_changes"] == 0
    assert permutation["decision_changes"] == 0
    assert permutation["grouping_changes"] == 0
    perturb = result["stability"]["one_pixel_coordinate_perturbation"]["summary"]
    assert perturb["events_tested"] == 46
    assert perturb["slope_changes"] >= 1
    assert perturb["support_decision_changes"] >= 1
    assert "assignment_changes" in perturb


def test_no_png_or_pdf_is_tracked() -> None:
    tracked = subprocess.run(
        ["git", "ls-files", "*.png", "*.pdf"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert tracked == ""
    assert not list(WORK.glob("*.png"))
    assert not list(WORK.glob("*.pdf"))


def test_research_wrapper_restores_production_functions() -> None:
    import normalize.geometry as geometry

    old_slope = geometry._estimate_baseline_slope
    old_adjusted = geometry._adjusted_center_y
    event = json.loads((PRIOR / "adjudications.json").read_text(encoding="utf-8"))["events"][0]
    _, _, sides = run_forensics.load_inputs()
    side = sides[(event["fixture_id"], event["side"])]
    run_forensics.group_page_with_local_slope(side["tokens"], set(event["source_rows"]), -0.01)
    assert geometry._estimate_baseline_slope is old_slope
    assert geometry._adjusted_center_y is old_adjusted
