"""Focused evidence checks for the read-only spineless residual trace."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = Path(__file__).with_name("run_forensics.py")


def load_runner():
    spec = importlib.util.spec_from_file_location("spineless_residual_forensics", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_reproduces_all_six_exact_prior_observations_and_uses_one_ocr_call_each(monkeypatch):
    runner = load_runner()
    calls = []
    original = runner.pytesseract.image_to_data

    def counted(*args, **kwargs):
        calls.append(kwargs.get("config"))
        return original(*args, **kwargs)

    monkeypatch.setattr(runner.pytesseract, "image_to_data", counted)
    results, traces = runner.run()
    assert len(calls) == 6
    assert set(calls) == {"--psm 6"}
    assert results["ocr_invocations"] == 6
    assert all(page["reproduces_prior"] for page in results["pages"].values())
    assert [results["pages"][str(page)]["admitted_tokens"] for page in runner.PAGES] == [202, 264, 139, 307, 148, 221]
    assert [results["pages"][str(page)]["physical_lines"] for page in runner.PAGES] == [36, 46, 23, 34, 26, 33]
    assert [results["pages"][str(page)]["ambiguous"] for page in runner.PAGES] == [0] * 6
    assert [results["pages"][str(page)]["unassigned"] for page in runner.PAGES] == [0] * 6
    assert traces["source_observation_hashes"] == {
        str(page): results["pages"][str(page)]["raw_tsv_sha256"] for page in runner.PAGES
    }


def test_target_identities_and_first_divergence_are_deterministic():
    stage = json.loads((SCRIPT.parent / "stage-traces.json").read_text())
    by_context = {trace["context"]: trace for trace in stage["traces"]}
    expected = {
        "failure_1_changes_embankment_yet": (list(range(69, 77)), "vertical_band_construction"),
        "failure_2_if_k_every_other": (list(range(32, 41)), "vertical_band_construction"),
        "failure_3_affords_missing": ([], "raw_tesseract_observation"),
        "failure_4_greater_velocities_square_root": (list(range(108, 116)), "vertical_band_construction"),
    }
    for context, (source_rows, first_stage) in expected.items():
        trace = by_context[context]
        assert trace["target_source_rows"] == source_rows
        assert trace["first_divergence"] == first_stage
    for context in ("failure_1_changes_embankment_yet", "failure_2_if_k_every_other", "failure_4_greater_velocities_square_root"):
        assert by_context[context]["stage_trace"]["instrumentation_matches_production_memberships"] is True


def test_page_27_missing_row_is_emitted_as_abnormal_word_box_and_admitted():
    stage = json.loads((SCRIPT.parent / "stage-traces.json").read_text())
    trace = next(t for t in stage["traces"] if t["context"] == "failure_3_affords_missing")
    records = {row["source_row"]: row for row in trace["raw_tsv_records_intersecting_context"]}
    assert trace["raw_tsv_row_classification"] == "complete_but_geometrically_abnormal"
    assert records[190]["text"] == "See"
    assert records[190]["box_xyxy"] == [7, 640, 624, 696]
    assert records[190]["confidence"] == 14.663147
    assert records[190]["admission"]["decision"] == "admitted"
    assert records[191]["text"] == "ae"
    assert records[191]["admission"]["decision"] == "admitted"
    assert trace["stage_trace"]["admitted_spatially_intersecting_tokens"]
    assert trace["stage_trace"]["matched_control_inventory"]["following_row"]


def test_matched_controls_share_production_trace_and_no_alternate_ocr_path():
    module_source = SCRIPT.read_text()
    assert 'config="--psm 6"' in module_source
    assert "row_correction_angle" not in module_source
    stage = json.loads((SCRIPT.parent / "stage-traces.json").read_text())
    for trace in stage["traces"]:
        controls = trace["stage_trace"].get("admitted_token_inventory", trace["stage_trace"].get("matched_control_inventory", {}))
        assert len(controls) >= 2
        assert all(rows for rows in controls.values())


def test_production_sources_and_tracked_binary_inventory_are_unchanged():
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", "HEAD", "--", "src/normalize", "fixtures/preprocessing.json", "tests"],
        cwd=ROOT,
        text=True,
    ).splitlines()
    assert changed == []
    tracked = subprocess.check_output(
        ["git", "ls-files", "*.jpg", "*.jpeg", "*.png", "*.pdf"], cwd=ROOT, text=True
    ).splitlines()
    assert tracked == []
