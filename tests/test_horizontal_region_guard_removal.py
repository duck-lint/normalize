"""Geometry-only regressions for observed horizontal token extents."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import normalize.geometry as geometry


ROOT = Path(__file__).resolve().parents[1]
REGRESSION_PATH = ROOT / "tests/data/horizontal-region-guard-removal-regressions.json"
REGRESSIONS = json.loads(REGRESSION_PATH.read_text(encoding="utf-8"))
GAP_FORMULA = "2 * median(token_width_px); region extent is cumulative from observed token boxes"


def _token(source_row: int, x: int, y: int, width: int, height: int = 10) -> geometry._Token:
    """Build an admitted OCR token from geometry only; text has no role here."""

    return geometry._Token(
        source_row=source_row,
        text="",
        confidence=95.0,
        level=5,
        page_num=1,
        block_num=1,
        par_num=1,
        line_num=1,
        word_num=source_row,
        x=x,
        y=y,
        width=width,
        height=height,
    )


def _regions(tokens: list[geometry._Token], gap_limit: float) -> list[list[int]]:
    result = geometry._split_horizontal_regions([tokens], gap_limit)
    return [
        [token.source_row for token in sorted(region, key=lambda item: (item.x, item.source_row))]
        for region in result
    ]


def _fixture_tokens(case: dict) -> list[geometry._Token]:
    return [
        _token(
            item["source_row"],
            item["bbox_px"][0],
            item["bbox_px"][1],
            item["bbox_px"][2] - item["bbox_px"][0],
            item["bbox_px"][3] - item["bbox_px"][1],
        )
        for item in case["tokens"]
    ]


@pytest.mark.parametrize(
    "case",
    REGRESSIONS["cases"],
    ids=[case["event_id"] for case in REGRESSIONS["cases"]],
)
def test_all_researched_false_split_events_follow_observed_extent(case: dict) -> None:
    assert _regions(_fixture_tokens(case), case["gap_limit_px"]) == case["expected_regions"]


def test_regression_fixture_covers_requested_adjudicated_examples() -> None:
    ids = {case["event_id"] for case in REGRESSIONS["cases"]}
    assert REGRESSIONS["provenance"]["research_commit"] == (
        "b1728222b054e16053b756becd415ea602d2dee7"
    )
    assert {
        "relativity_pdf10_pp26-27.left.event-001",  # Relativity 10 heading row
        "relativity_pdf10_pp26-27.left.event-004",  # embankment locator
        "relativity_pdf17_pp40-41.right.event-009",  # reference-body locator
        "relativity_pdf23_pp52-53.left.event-002",  # x-axis expression
        "relativity_pdf23_pp52-53.left.event-003",  # x' = 0 expression
        "stella_maris_pdf06_dense-dialogue.left.event-001",  # dialogue row
    } <= ids


def test_legitimate_wide_token_contributes_its_actual_right_edge() -> None:
    tokens = [
        _token(1, 0, 20, 5),
        _token(2, 15, 20, 70),
        _token(3, 90, 20, 5),
    ]
    # True gaps are 10 and 5; the former stale-left extent would measure 90.
    assert _regions(tokens, 10) == [[1, 2, 3]]


def test_width_crossing_old_classification_boundary_has_no_partition_jump() -> None:
    partitions = []
    for middle_width in (14, 16):
        tokens = [
            _token(1, 0, 20, 5),
            _token(2, 15, 20, middle_width),
            _token(3, 15 + middle_width + 5, 20, 5),
        ]
        assert geometry._horizontal_gap_limit(tokens) == 10
        partitions.append(_regions(tokens, geometry._horizontal_gap_limit(tokens)))
    # With the former 1.5 * gap-limit boundary these middle widths fell on
    # opposite sides. Both now use the same observed-edge gap rule.
    assert partitions == [[[1, 2, 3]], [[1, 2, 3]]]


@pytest.mark.parametrize(
    ("previous_right", "next_x", "gap_limit"),
    ((84, 202, 77), (129, 383, 77)),
)
def test_researched_genuine_gap_controls_remain_separate(
    previous_right: int, next_x: int, gap_limit: int
) -> None:
    assert _regions(
        [_token(1, 0, 20, previous_right), _token(2, next_x, 20, 10)], gap_limit
    ) == [[1], [2]]


def test_wide_token_followed_by_true_gap_over_limit_still_splits() -> None:
    tokens = [_token(1, 0, 20, 10), _token(2, 20, 20, 100), _token(3, 205, 20, 10)]
    assert _regions(tokens, 77) == [[1, 2], [3]]


def test_cumulative_right_edge_never_moves_left_after_overlap() -> None:
    tokens = [_token(1, 10, 20, 90), _token(2, 20, 20, 10), _token(3, 95, 20, 5)]
    assert _regions(tokens, 10) == [[1, 2, 3]]


def test_same_column_horizontal_safeguard_is_unchanged() -> None:
    upper = _token(1, 25, 20, 10)
    lower = _token(2, 25, 24, 10)
    assert not geometry._horizontally_adjacent(upper, lower, 20)


def test_empty_and_nonempty_measurements_describe_the_same_extent_rule() -> None:
    assert geometry.group_physical_lines([])[2]["horizontal_gap_formula"] == GAP_FORMULA
    tokens = [_token(1, 0, 20, 10), _token(2, 20, 20, 10)]
    assert geometry.group_physical_lines(tokens)[2]["horizontal_gap_formula"] == GAP_FORMULA
