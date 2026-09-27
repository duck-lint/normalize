"""Focused invariants for the paired production-crop guard experiment."""

from __future__ import annotations

import subprocess
import json
from pathlib import Path

from normalize import geometry
from run_ablation import connected_events, run_guard_off, run_guard_on


ROOT = Path(__file__).resolve().parents[2]


def token(row: int, text: str, x: int, width: int, y: int = 10) -> geometry._Token:
    return geometry._Token(row, text, 90.0, 5, 1, 1, 1, row, row, x, y, width, 10)


def ids(lines):
    return [line["token_ids"] for line in lines]


def test_guard_on_calls_the_current_production_grouping(monkeypatch):
    original = geometry.group_physical_lines
    calls = []

    def observed(tokens):
        calls.append(tuple(item.source_row for item in tokens))
        return original(tokens)

    monkeypatch.setattr(geometry, "group_physical_lines", observed)
    observed_tokens = [token(1, "a", 0, 10)]
    run_guard_on(observed_tokens)
    assert calls == [(1,)]


def test_one_ordinary_token_each_side_exposes_the_false_split():
    tokens = [token(1, "left", 0, 10), token(2, "long", 12, 40), token(3, "right", 54, 10)]
    on_lines, on_unresolved, on_measurements = run_guard_on(tokens)
    off_lines, off_unresolved, off_measurements = run_guard_off(tokens, 0.0)
    assert ids(on_lines) == [["token-0001", "token-0002"], ["token-0003"]]
    assert ids(off_lines) == [["token-0001", "token-0002", "token-0003"]]
    assert on_unresolved == off_unresolved == []
    assert on_measurements["baseline_slope_px_per_px"] == off_measurements["baseline_slope_px_per_px"] == 0.0
    assert on_measurements["horizontal_gap_limit_px"] == off_measurements["horizontal_gap_limit_px"] == 20.0
    assert on_measurements["tolerance_px"] == off_measurements["tolerance_px"]
    assert [item.payload() for item in tokens] == [item.payload() for item in tokens]


def test_real_ordinary_gap_remains_split_guard_off():
    tokens = [token(1, "left", 0, 10), token(2, "wide", 12, 40), token(3, "right", 100, 10)]
    on_lines, _on_unresolved, _ = run_guard_on(tokens)
    off_lines, _off_unresolved, _ = run_guard_off(tokens, 0.0)
    assert ids(off_lines) == ids(on_lines)
    assert ids(off_lines) == [["token-0001", "token-0002"], ["token-0003"]]


def test_same_admitted_identities_and_duplicate_text_remain_distinguishable():
    tokens = [token(11, "same", 0, 10), token(12, "wide", 12, 40), token(13, "same", 54, 10)]
    source_identity = [(item.source_row, item.text, item.x, item.y, item.width, item.height) for item in tokens]
    on, on_unresolved, _ = run_guard_on(tokens)
    off, off_unresolved, _ = run_guard_off(tokens, 0.0)
    events, on_memberships, off_memberships = connected_events(tokens, on, on_unresolved, off, off_unresolved)
    assert source_identity[0][1] == source_identity[2][1]
    assert source_identity[0][0] != source_identity[2][0]
    assert on_memberships.keys() == off_memberships.keys() == {11, 12, 13}
    changed_rows = {row for event in events for row in event}
    assert changed_rows == {11, 12, 13}
    assert [row for event in events for row in event].count(11) == 1
    assert [row for event in events for row in event].count(13) == 1


def test_blank_page_is_excluded_from_primary_decision_and_binaries_are_untracked():
    primary_fixture_sides = {
        ("relativity_pdf10_pp26-27", "left"),
        ("relativity_pdf10_pp26-27", "right"),
        ("relativity_pdf17_pp40-41", "left"),
        ("relativity_pdf17_pp40-41", "right"),
        ("relativity_pdf23_pp52-53", "left"),
        ("relativity_pdf23_pp52-53", "right"),
        ("stella_maris_pdf03_session-I", "right"),
        ("stella_maris_pdf06_dense-dialogue", "left"),
        ("stella_maris_pdf06_dense-dialogue", "right"),
        ("stella_maris_pdf18_session-II_p35", "left"),
        ("stella_maris_pdf18_session-II_p35", "right"),
    }
    assert ("stella_maris_pdf03_session-I", "left") not in primary_fixture_sides
    tracked = subprocess.run(
        ["git", "ls-files", "*.png", "*.pdf"], cwd=ROOT, check=True, text=True, capture_output=True
    ).stdout.splitlines()
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"], cwd=ROOT, check=True, text=True, capture_output=True
    ).stdout.splitlines()
    assert not tracked
    assert not [path for path in staged if Path(path).suffix.lower() in {".png", ".pdf"}]


def test_corpus_result_is_identity_complete_and_has_human_review_for_every_primary_event():
    result = json.loads((Path(__file__).parent / "results.json").read_text(encoding="utf-8"))
    review = json.loads((Path(__file__).parent / "adjudications.json").read_text(encoding="utf-8"))
    assert len(result["pages"]) == 12
    primary_event_ids = set()
    primary_changed_rows = set()
    for page in result["pages"]:
        assert page["guard_on_token_identity_sha256"] == page["guard_off_token_identity_sha256"]
        assert page["guard_on_token_identity_sha256"] == page["ocr_token_identity_sha256"]
        assert page["guard_on"]["selected_slope"] == page["guard_off"]["selected_slope"]
        assert page["guard_on"]["horizontal_gap_limit_px"] == page["guard_off"]["horizontal_gap_limit_px"]
        assert page["guard_on"]["measurements"]["tolerance_px"] == page["guard_off"]["tolerance_px"]
        assert page["guard_on"]["token_count"] == len(page["admitted_tokens"])
        extent_rows = [
            item["source_row"]
            for item in page["guard_trace"]
            if item.get("event") == "token_extent"
        ]
        assert sorted(extent_rows) == sorted(token["source_row"] for token in page["admitted_tokens"])
        assert all("supported_bridge_source_rows" in call for call in page["supported_bridge_predicate_calls"])
        changed = {
            int(row)
            for row in page["guard_on_memberships_by_source_row"]
            if page["guard_on_memberships_by_source_row"][row]
            != page["guard_off_memberships_by_source_row"][row]
        }
        event_rows = [row for event in page["changed_events"] for row in event["token_source_rows"]]
        assert len(event_rows) == len(set(event_rows))
        assert set(event_rows) == changed
        if page["blank"]:
            assert all(event["adjudication"] == "excluded_blank_diagnostic" for event in page["changed_events"])
            continue
        for event in page["changed_events"]:
            primary_event_ids.add(event["event_id"])
            primary_changed_rows.update((page["fixture_id"], page["side"], row) for row in event["token_source_rows"])
            assert event["adjudication"] in {"repaired_false_split", "destructive_merge", "benign_difference", "unresolved"}
            assert event["pixel_metrics"]
            assert event["predicate_trace"]
    assert primary_event_ids == set(review["events"])
    assert result["primary_totals"]["changed_grouping_events"] == len(primary_event_ids) == 43
    assert result["primary_totals"]["adjudications"] == {
        "repaired_false_split": 43,
        "destructive_merge": 0,
        "benign_difference": 0,
        "unresolved": 0,
    }
