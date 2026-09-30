"""Focused, research-only contracts for the rigid-rotation ablation."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from PIL import Image

import run_rotation_ablation as ablation
from normalize.geometry import TSV_HEADER


ROOT = Path(__file__).resolve().parents[3]
WORK = Path(__file__).resolve().parent
RESULTS = WORK / "results.json"
ADJUDICATIONS = WORK / "adjudications.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _results() -> dict:
    return json.loads(RESULTS.read_text(encoding="utf-8"))


def test_control_starts_from_current_production_page_side_preprocessing(tmp_path: Path) -> None:
    catalog = ablation.FixtureCatalog.load(ROOT)
    fixture = catalog.get("relativity_pdf10_pp26-27")
    result = ablation.preprocess_fixture(
        fixture, ROOT / "fixtures/preprocessing.json", tmp_path / "control"
    )
    assert result["status"] == "success"
    metadata = json.loads(
        (tmp_path / "control" / "relativity_pdf10_pp26-27.preprocess.json").read_text()
    )
    assert [page["side"] for page in metadata["pages"]] == ["left", "right"]
    assert all(page["source_stage"] == "post_deskew" for page in metadata["pages"])
    assert all((tmp_path / "control" / page["output_path"]).is_file() for page in metadata["pages"])


def test_rotation_is_the_only_change_before_production_ocr_and_geometry(monkeypatch) -> None:
    calls = []
    tsv = "\t".join(TSV_HEADER) + "\n"

    def fake_ocr(image, **kwargs):
        calls.append((image.size, kwargs))
        return tsv

    observed = []

    def fake_group(tokens):
        observed.append(tokens)
        return [], [], {"baseline_slope_px_per_px": 0.0, "horizontal_gap_limit_px": None, "tolerance_px": None}

    monkeypatch.setattr(ablation.pytesseract, "image_to_data", fake_ocr)
    monkeypatch.setattr(ablation, "group_physical_lines", fake_group)
    input_image = Image.new("RGB", (80, 60), (255, 255, 255))
    rotated = ablation.rotate_page_side(input_image, 1.0)
    assert rotated.size != input_image.size
    ablation.capture_geometry(rotated)
    assert calls == [((rotated.width, rotated.height), {
        "lang": "eng", "config": "--psm 6", "output_type": ablation.Output.STRING
    })]
    assert observed == [[]]


def test_angle_authority_covers_twelve_sides_and_marks_blank_unresolved() -> None:
    assert len(ablation.ANGLE_EVIDENCE) == 12
    assert sum(value["angle_degrees"] is not None for value in ablation.ANGLE_EVIDENCE.values()) == 10
    blank = ablation.ANGLE_EVIDENCE["stella_maris_pdf03_session-I.left"]
    assert blank["angle_degrees"] is None
    assert not blank["single_orientation_supported"]
    assert ablation.ANGLE_EVIDENCE["stella_maris_pdf18_session-II_p35.left"]["angle_degrees"] is None
    assert not ablation.ANGLE_EVIDENCE["stella_maris_pdf18_session-II_p35.left"]["single_orientation_supported"]
    assert all(value["regions"] for key, value in ablation.ANGLE_EVIDENCE.items() if value["angle_degrees"] is not None)


def test_checked_in_results_capture_both_paths_and_identity_mapping_completely_where_possible() -> None:
    results = _results()
    assert results["schema"] == "page-side-rigid-rotation-ablation-v1"
    assert results["ocr_configuration"]["language"] == "eng"
    assert results["ocr_configuration"]["config"] == "--psm 6"
    assert len(results["pages"]) == 12
    assert results["production_source_hashes"]["src/normalize/geometry.py"] == _sha(ROOT / "src/normalize/geometry.py")
    for page in results["pages"]:
        assert len(page["control"]["ocr_tsv_sha256"]) == 64
        assert len(page["rotated"]["ocr_tsv_sha256"]) == 64
        assert page["control"]["image_sha256"] == page["rotation"]["input_sha256"]
        assert page["rotated"]["image_sha256"] == page["rotation"]["output_sha256"]
        assert page["identity_alignment"]["matched_token_count"] + len(page["identity_alignment"]["control_unmatched_source_rows"]) == page["control"]["admitted_token_count"]
        assert page["identity_alignment"]["matched_token_count"] + len(page["identity_alignment"]["rotated_unmatched_source_rows"]) == page["rotated"]["admitted_token_count"]
        if page["angle_evidence"]["angle_degrees"] is not None:
            assert len(page["sensitivity"]) == 2
        else:
            assert page["sensitivity"] == []


def test_changed_event_enumeration_has_boxes_for_every_recorded_group_member() -> None:
    results = _results()
    adjudications = json.loads(ADJUDICATIONS.read_text(encoding="utf-8"))
    assert len(results["changed_events"]) == len(adjudications["events"])
    assert len(results["changed_events"]) == 30
    for event in adjudications["events"]:
        assert event["classification"] in {
            "repaired_false_split", "destructive_merge", "new_false_split", "benign_difference", "unresolved"
        }
        for key in ("control", "rotated"):
            boxes = {record["identity"] for record in event[f"{key}_boxes"]}
            for group in event[f"{key}_grouping"]:
                assert set(group) <= boxes
        assert event["control_line_records"] and event["rotated_line_records"]


def test_historical_slope_context_crosswalk_is_complete_and_provenance_qualified() -> None:
    comparison = _results()["prior_slope_context_comparison"]
    assert comparison["source"]["event_count"] == 46
    assert comparison["source"]["prior_capture_script_omitted_explicit_psm"]
    assert sum(comparison["outcome_counts"].values()) == 46
    assert len(comparison["contexts"]) == 46
    assert comparison["outcome_counts"] == {
        "already_one_band_under_fresh_control": 10,
        "remains_multi_band": 9,
        "rotation_groups_to_one_band": 25,
        "unresolved_identity_crosswalk": 2,
    }


def test_adjudicated_changes_and_small_angle_sensitivity_are_explicit() -> None:
    results = _results()
    adjudications = json.loads(ADJUDICATIONS.read_text(encoding="utf-8"))
    assert adjudications["classification_counts"] == {
        "repaired_false_split": 29,
        "destructive_merge": 0,
        "new_false_split": 1,
        "benign_difference": 0,
        "unresolved": 0,
    }
    sensitivity = [item for page in results["pages"] for item in page["sensitivity"]]
    assert len(sensitivity) == 20
    assert sum(item["grouping_stability_vs_chosen"] for item in sensitivity) == 11
    assert sum(item["repaired_event_stability_vs_chosen"] for item in sensitivity) == 9
    unstable_case = next(
        item for page in results["pages"]
        if page["fixture_id"] == "relativity_pdf10_pp26-27" and page["side"] == "right"
        for item in page["sensitivity"] if item["angle_degrees"] == -1.7
    )
    assert unstable_case["token_count"] == 98
    assert unstable_case["line_count"] == 16


def test_synthetic_horizontal_rotation_and_angle_error_controls() -> None:
    synthetic = ablation.run_synthetic_controls()
    assert synthetic["horizontal_identity"]["unchanged_image_pixels"]
    assert synthetic["horizontal_identity"]["unchanged_tsv"]
    assert synthetic["horizontal_identity"]["line_count"] == 4
    assert synthetic["horizontal_identity"]["header_and_body_separated"]
    assert synthetic["horizontal_identity"]["two_distinct_body_rows_remain_separate"]
    assert synthetic["known_rigid_rotation"]["corrected_rows_remain_distinct"]
    assert synthetic["known_rigid_rotation"]["corrected_line_count"] == 4
    assert synthetic["small_angle_error"]["resulting_error_degrees"] == 0.2
    assert not synthetic["small_angle_error"]["catastrophic_change"]


def test_production_files_and_tracked_raster_boundary_are_unchanged() -> None:
    production_diff = subprocess.check_output(
        ["git", "diff", "--name-only", "--", "src/normalize", "fixtures/preprocessing.json", "fixtures/*/*.expected.json"],
        cwd=ROOT,
        text=True,
    ).splitlines()
    assert production_diff == []
    tracked_rasters = subprocess.check_output(
        ["git", "ls-files", "*.png", "*.pdf"], cwd=ROOT, text=True
    ).splitlines()
    assert tracked_rasters == []
    staged = subprocess.check_output(["git", "diff", "--cached", "--name-only"], cwd=ROOT, text=True)
    assert not staged.strip()
