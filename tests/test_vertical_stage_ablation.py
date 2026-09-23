"""Focused checks for stage fidelity and assignment-only perturbation semantics."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "research/geometry/vertical-stage-ablation/stage_ablation.py"
SPEC = importlib.util.spec_from_file_location("vertical_stage_ablation", SCRIPT)
assert SPEC and SPEC.loader
ablation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ablation)


def _continuous_state():
    case = ablation.PRIOR._synthetic_cases()[0]
    tokens = ablation.PRIOR._synthetic_tokens(case["rows"])
    page = {"side": "synthetic"}
    return case, tokens, ablation._direct_production(case["case_id"], page, tokens)["canonical_state"]


def test_fidelity_gate_covers_all_six_fixtures_and_all_pages() -> None:
    results = json.loads((ROOT / "research/geometry/vertical-stage-ablation/results.json").read_text())
    gate = results["fidelity_gate"]
    assert gate["fixture_count"] == 6
    assert gate["page_count"] == 12
    assert gate["all_complete_states_equal"]
    assert gate["all_horizontal_splits_equal"]


def test_fidelity_gate_executes_direct_production_comparison() -> None:
    """Exercise the gate against repository inputs rather than stored flags."""

    gate = ablation._fidelity_gate()
    assert gate["fixture_count"] == 6
    assert gate["page_count"] == 12
    assert gate["all_complete_states_equal"]
    assert gate["all_horizontal_splits_equal"]


def test_fidelity_gate_rejects_an_injected_control_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure a real control-state mismatch fails before results are written."""

    original = ablation._control_pipeline
    injected = False

    def mismatching_control(fixture_id, page, tokens):
        nonlocal injected
        result = copy.deepcopy(original(fixture_id, page, tokens))
        # Change an assignment field, not a derived digest, so the failure is
        # a genuine fidelity mismatch rather than a bookkeeping discrepancy.
        if result["canonical_state"] and not injected:
            result["canonical_state"][0][0][2] = "injected-mismatch-line"
            injected = True
        return result

    monkeypatch.setattr(ablation, "_control_pipeline", mismatching_control)
    with pytest.raises(AssertionError, match="production-fidelity gate"):
        ablation.run(write_manifest=False)


def test_coordinate_change_can_leave_assignment_semantics_stable() -> None:
    case, tokens, before = _continuous_state()
    changed_tokens = [
        ablation.production_geometry._Token(
            token.source_row,
            token.text,
            token.confidence,
            token.level,
            token.page_num,
            token.block_num,
            token.par_num,
            token.line_num,
            token.word_num,
            token.x,
            token.y + (1 if token is tokens[0] else 0),
            token.width,
            token.height,
        )
        for token in tokens
    ]
    after = ablation._direct_production(case["case_id"], {"side": "synthetic"}, changed_tokens)["canonical_state"]
    comparison = ablation.compare_canonical_states(before, after)
    assert comparison["input_coordinates_changed"]
    assert not comparison["assignment_changed"]
    assert comparison["measurement_changed"]


def test_assignment_comparison_detects_membership_and_candidate_changes() -> None:
    _case, _tokens, original = _continuous_state()
    changed_membership = copy.deepcopy(ablation._jsonable(original))
    changed_membership[1][0][1] = []
    assert ablation.compare_canonical_states(original, changed_membership)["assignment_changed"]

    changed_candidates = copy.deepcopy(ablation._jsonable(original))
    changed_candidates[0][0][3] = []
    comparison = ablation.compare_canonical_states(original, changed_candidates)
    assert comparison["assignment_changed"]
    assert not comparison["input_coordinates_changed"]


def test_assignment_comparison_detects_resolved_uncertainty_transition() -> None:
    _case, _tokens, original = _continuous_state()
    changed = copy.deepcopy(ablation._jsonable(original))
    changed[0][0][2] = None
    changed[0][0][3] = ["physical-line-0001", "physical-line-0002"]
    changed[0][0][4] = "ambiguous_line_assignment"
    assert ablation.compare_canonical_states(original, changed)["assignment_changed"]


def test_oracle_canonicalization_ignores_irrelevant_line_id_renaming() -> None:
    case = ablation.PRIOR._synthetic_cases()[0]
    tokens = ablation.PRIOR._synthetic_tokens(case["rows"])
    lines, unresolved, measurements = ablation.production_geometry.group_physical_lines(tokens)
    renamed_lines = [{**line, "line_id": "renamed-generated-id"} for line in lines]
    first = ablation.canonical_geometry_state(case["case_id"], "synthetic", tokens, lines, unresolved, measurements)
    second = ablation.canonical_geometry_state(case["case_id"], "synthetic", tokens, renamed_lines, unresolved, measurements)
    assert ablation.assignment_projection(first) == ablation.assignment_projection(second)
