"""Focused tests for the research-only oracle evaluator."""

from __future__ import annotations

import importlib.util
from pathlib import Path


AUDIT_PATH = Path(__file__).with_name("audit.py")
SPEC = importlib.util.spec_from_file_location("normalize_accuracy_audit", AUDIT_PATH)
assert SPEC and SPEC.loader
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def test_exact_preprocessing_fields_are_scoreable_without_fuzzy_matching():
    expected = {
        "fixture_id": "fixture",
        "spread_reading_order": ["left", "right"],
        "blank_page_sides": [],
        "expected_sequence": [],
        "page_furniture": [],
        "critical_assertions": [],
    }
    production = {
        "status": "success",
        "result": {"output_order": ["left", "right"], "blank_sides": []},
    }

    assertions = audit.classify_oracle(expected, production)

    scoreable = [item for item in assertions if item["status"] == "scoreable_now"]
    assert len(scoreable) == 2
    assert all(item["decision"] == "correct" for item in scoreable)


def test_swapped_preprocessing_order_is_a_silent_wrong_decision():
    expected = {
        "fixture_id": "fixture",
        "spread_reading_order": ["left", "right"],
    }
    production = {
        "status": "success",
        "result": {"output_order": ["right", "left"], "blank_sides": []},
    }

    assertions = audit.classify_oracle(expected, production)

    assert assertions[0]["status"] == "scoreable_now"
    assert assertions[0]["decision"] == "wrong"


def test_structural_sequence_is_not_scored_from_anchor_presence():
    expected = {
        "fixture_id": "fixture",
        "expected_sequence": [
            {"side": "right", "type": "paragraph_start", "raw_anchor": "Same text"}
        ],
    }
    production = {"status": "success", "result": {"output_order": ["left", "right"]}}

    assertions = audit.classify_oracle(expected, production)

    assert assertions[0]["status"] == "not_yet_produced_by_pipeline"
    assert assertions[0]["observed"] is None


def test_geometry_summary_counts_candidate_states():
    geometry = {
        "status": "uncertain",
        "uncertainties": ["ambiguous_line_assignment"],
        "errors": [],
        "pages": [
            {
                "side": "left",
                "status": "uncertain",
                "tokens": [
                    {"candidate_line_ids": ["line-1"], "physical_line_id": "line-1"},
                    {"candidate_line_ids": ["line-1", "line-2"], "physical_line_id": None},
                    {"candidate_line_ids": [], "physical_line_id": None},
                ],
                "physical_lines": [{"line_id": "line-1"}, {"line_id": "line-2"}],
            }
        ],
    }

    summary = audit._geometry_summary(geometry)

    assert summary["admitted_token_count"] == 3
    assert summary["resolved_token_count"] == 1
    assert summary["ambiguous_token_count"] == 1
    assert summary["unassigned_token_count"] == 1
    assert summary["residual_token_count"] == 2
