"""Focused safeguards for the manual-crop oversized-guard experiment."""
from __future__ import annotations

import gzip
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MODULE = Path(__file__).with_name("run_ablation.py")
SPEC = importlib.util.spec_from_file_location("normalize_cropped_guard_ablation", MODULE)
assert SPEC and SPEC.loader
study = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(study)


def token(row: int, x: int, y: int, width: int = 30, text: str = "word"):
    return study.geometry._Token(row, text, 95.0, 5, 1, 1, 1, 1, row, x, y, width, 12)


def line_membership(grouping):
    return sorted(sorted(line["token_ids"]) for line in grouping[0])


def test_guard_on_reuses_production_result_for_same_cropped_tsv():
    tsv_path = study.OUT / "ocr/relativity_pdf17_pp40-41.right.tsv.gz"
    assert tsv_path.is_file()
    from PIL import Image
    with Image.open(study.OUT / "inputs/relativity_pdf17_pp40-41.right.png") as image:
        width, height = image.size
    raw_tsv = gzip.decompress(tsv_path.read_bytes()).decode("utf-8")
    tokens, errors = study.geometry.parse_tsv_rows(raw_tsv, width, height)
    assert not errors
    original_predicate = study.geometry._is_oversized
    on, _off = study.group_variants(tokens)
    assert on == study.geometry.group_physical_lines(tokens)
    assert study.geometry._is_oversized is original_predicate


def test_guard_off_only_changes_the_oversized_predicate():
    tokens = [token(i, x, 100, width, text) for i, (x, width, text) in enumerate([
        (0,30,"left"),(35,30,"left"),(70,30,"left"),(105,30,"the"),
        (141,95,"conclusion"),(242,30,"that"),(277,30,"right"),(312,30,"right"),(347,30,"right")
    ],1)]
    original_payloads = [item.payload() for item in tokens]
    original_group = study.geometry.group_physical_lines
    original_adjacency = study.geometry._horizontally_adjacent
    original_split = study.geometry._split_horizontal_regions
    on, off = study.group_variants(tokens)
    assert [item.payload() for item in tokens] == original_payloads
    assert study.geometry.group_physical_lines is original_group
    assert study.geometry._horizontally_adjacent is original_adjacency
    assert study.geometry._split_horizontal_regions is original_split
    assert on[2]["horizontal_gap_limit_px"] == off[2]["horizontal_gap_limit_px"]
    assert on[2]["baseline_slope_px_per_px"] == off[2]["baseline_slope_px_per_px"]
    assert len(on[0]) > len(off[0])


def test_conclusion_box_false_split_is_exposed_by_guard_off():
    tokens = [token(i, x, 100, w, text) for i, (x, w, text) in enumerate([
        (0,30,"left"),(35,30,"left"),(70,30,"left"),(105,30,"the"),
        (141,95,"conclusion"),(242,30,"that"),(277,30,"right"),(312,30,"right"),(347,30,"right")
    ],1)]
    on, off = study.group_variants(tokens)
    assert study.geometry._is_oversized(tokens[4], 60)
    assert len(on[0]) == 2
    assert len(off[0]) == 1
    assert set(off[0][0]["token_ids"]) == {f"token-{row:04d}" for row in range(1,10)}


def test_real_horizontal_gap_stays_split_with_guard_off():
    tokens = [token(1,0,100), token(2,35,100), token(3,300,100), token(4,335,100)]
    _on, off = study.group_variants(tokens)
    assert len(study.geometry._split_horizontal_regions([tokens], 60)) == 2
    assert len(off[0]) == 2


def test_changed_group_enumeration_covers_every_token_identity():
    on = {"lines": [{"line_id":"line-1","token_ids":["token-0001"]},
                     {"line_id":"line-2","token_ids":["token-0002"]}], "unresolved": []}
    off = {"lines": [{"line_id":"line-1","token_ids":["token-0001","token-0002"]}], "unresolved": []}
    events = study.grouping_events(on, off)
    changed_ids = set().union(*(set(event["token_ids"]) for event in events))
    assert changed_ids == {"token-0001", "token-0002"}
    assert events[0]["pairs_merged_guard_off"] == [["token-0001", "token-0002"]]


def test_duplicate_ocr_text_keeps_distinct_source_row_identities():
    # Same OCR string remains two boxes with independent source-row identity.
    tokens = [token(1,0,100,text="mark"), token(2,35,100,text="mark"),
              token(3,70,100,text="mark"), token(4,105,100,text="very-wide")]
    assert tokens[0].text == tokens[1].text
    assert tokens[0].source_row != tokens[1].source_row
    events = study.grouping_events(
        {"lines":[{"line_id":"line-1","token_ids":["token-0001","token-0002"]},
                   {"line_id":"line-2","token_ids":["token-0003","token-0004"]}],"unresolved":[]},
        {"lines":[{"line_id":"line-1","token_ids":["token-0001","token-0002","token-0003","token-0004"]}],"unresolved":[]})
    assert {token_id for event in events for token_id in event["token_ids"]} == {
        "token-0001","token-0002","token-0003","token-0004"
    }
    assert sum(event["token_ids"].count("token-0001") for event in events) == 1
    assert sum(event["token_ids"].count("token-0002") for event in events) == 1
