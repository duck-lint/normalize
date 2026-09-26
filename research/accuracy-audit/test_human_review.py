"""Synthetic tests for the human physical-line oracle and scorer."""

from __future__ import annotations

import importlib.util
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

import pytest

MODULE_PATH = Path(__file__).with_name("human_review.py")
SPEC = importlib.util.spec_from_file_location("normalize_human_geometry_review", MODULE_PATH)
assert SPEC and SPEC.loader
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)


def fixture(tokens: list[tuple[str, str | None, list[str] | None]], lines: list[tuple[str, list[str]]]):
    token_records = []
    for index, (token_id, line_id, candidates) in enumerate(tokens, start=1):
        token_records.append({
            "token_id": token_id, "source_row": index, "text": "same" if index in {1, 2} else f"word{index}",
            "physical_line_id": line_id, "candidate_line_ids": candidates if candidates is not None else ([line_id] if line_id else []),
            "x_px": index * 10, "y_px": index * 10, "width_px": 8, "height_px": 8,
            "right_px": index * 10 + 8, "bottom_px": index * 10 + 8,
        })
    page = {
        "side": "page", "blank": False, "tokens": token_records,
        "physical_lines": [{"line_id": line_id, "token_ids": members} for line_id, members in lines],
    }
    geometry = {"pages": [page]}
    record = {
        "fixture_id": "synthetic", "side": "page", "review_status": "verified_no_exceptions", "exceptions": [],
    }
    return geometry, {"schema": "normalize-human-geometry-review-v1", "pages": [record]}


def score(geometry, ledger):
    return review.score_review(ledger, {"synthetic": geometry})


def test_perfect_page_has_full_membership_accuracy_and_pairwise_scores():
    geometry, ledger = fixture(
        [("token-1", "line-a", None), ("token-2", "line-a", None), ("token-3", "line-b", None)],
        [("line-a", ["token-1", "token-2"]), ("line-b", ["token-3"])],
    )
    result = score(geometry, ledger)
    assert result["resolved_token_membership"]["accuracy"] == 1.0
    assert result["silent_error_rate"] == 0.0
    assert result["pairwise_grouping"]["precision"] == 1.0
    assert result["pairwise_grouping"]["recall"] == 1.0


def test_false_merge_reduces_pairwise_precision_and_membership_accuracy():
    geometry, ledger = fixture(
        [(f"token-{i}", "line-a", None) for i in range(1, 5)], [("line-a", [f"token-{i}" for i in range(1, 5)])]
    )
    record = ledger["pages"][0]
    record["review_status"] = "verified_with_exceptions"
    record["exceptions"] = [{
        "type": "false_merge", "production_line_id": "line-a",
        "token_ids": [f"token-{i}" for i in range(1, 5)],
        "human_groups": [
            {"human_group_id": "human-a", "token_ids": ["token-1", "token-2"]},
            {"human_group_id": "human-b", "token_ids": ["token-3", "token-4"]},
        ],
    }]
    result = score(geometry, ledger)
    assert result["pairwise_grouping"]["precision"] == pytest.approx(1 / 3)
    assert result["pairwise_grouping"]["recall"] == 1.0
    assert result["resolved_token_membership"]["incorrect_tokens"] == 4
    assert result["exact_physical_lines"]["false_merges"] == 1


def test_false_split_reduces_pairwise_recall():
    geometry, ledger = fixture(
        [("token-1", "line-a", None), ("token-2", "line-b", None)],
        [("line-a", ["token-1"]), ("line-b", ["token-2"])],
    )
    record = ledger["pages"][0]
    record["review_status"] = "verified_with_exceptions"
    record["exceptions"] = [{
        "type": "false_split", "production_line_ids": ["line-a", "line-b"],
        "token_ids": ["token-1", "token-2"], "human_group_id": "human-one-line",
    }]
    result = score(geometry, ledger)
    assert result["pairwise_grouping"]["precision"] is None
    assert result["pairwise_grouping"]["recall"] == 0.0
    assert result["resolved_token_membership"]["incorrect_tokens"] == 2
    assert result["exact_physical_lines"]["false_splits"] == 1


def test_wrong_membership_is_counted_in_silent_error_rate():
    geometry, ledger = fixture(
        [("token-1", "line-a", None), ("token-2", "line-b", None)],
        [("line-a", ["token-1"]), ("line-b", ["token-2"])],
    )
    record = ledger["pages"][0]
    record["review_status"] = "verified_with_exceptions"
    record["exceptions"] = [{
        "type": "wrong_membership", "production_line_id": "line-a",
        "token_ids": ["token-1"], "intended_human_group_id": "line-b",
    }]
    result = score(geometry, ledger)
    assert result["resolved_token_membership"]["incorrect_tokens"] == 2
    assert result["silent_error_rate"] == 1.0


def test_residual_assignment_is_separate_from_resolved_accuracy():
    geometry, ledger = fixture(
        [("token-1", "line-a", None), ("token-2", None, ["line-a"])],
        [("line-a", ["token-1"])],
    )
    record = ledger["pages"][0]
    record["review_status"] = "verified_with_exceptions"
    record["exceptions"] = [{
        "type": "residual_expected_membership", "token_ids": ["token-2"], "human_group_id": "line-a",
    }]
    result = score(geometry, ledger)
    assert result["resolved_token_membership"]["accuracy"] == 1.0
    assert result["coverage"] == {"resolved_tokens": 1, "admitted_tokens": 2, "rate": 0.5}
    assert result["residual_review"]["correct_line_among_production_candidates"] == 1
    assert result["residual_review"]["human_review_events"] == 1


def test_scorer_refuses_unreviewed_page_sides():
    geometry, ledger = fixture([("token-1", "line-a", None)], [("line-a", ["token-1"])])
    ledger["pages"][0]["review_status"] = "unreviewed"
    with pytest.raises(ValueError, match="cannot finalize"):
        score(geometry, ledger)


def test_duplicate_ocr_text_uses_token_identity_not_text_keys():
    geometry, ledger = fixture(
        [("token-1", "line-a", None), ("token-2", "line-b", None)],
        [("line-a", ["token-1"]), ("line-b", ["token-2"])],
    )
    assert geometry["pages"][0]["tokens"][0]["text"] == geometry["pages"][0]["tokens"][1]["text"]
    record = ledger["pages"][0]
    record["review_status"] = "verified_with_exceptions"
    record["exceptions"] = [{
        "type": "wrong_membership", "production_line_id": "line-a",
        "token_ids": ["token-2"], "intended_human_group_id": "line-a",
    }]
    with pytest.raises(ValueError, match="does not match current token assignments"):
        score(geometry, ledger)
    record["exceptions"][0].update(production_line_id="line-b", intended_human_group_id="line-a")
    result = score(geometry, ledger)
    assert result["resolved_token_membership"]["incorrect_tokens"] == 2
    assert result["review_burden"]["affected_tokens"] == 1


def test_wrong_order_stays_separate_from_membership_accuracy():
    geometry, ledger = fixture(
        [("token-1", "line-a", None), ("token-2", "line-a", None)],
        [("line-a", ["token-1", "token-2"])],
    )
    record = ledger["pages"][0]
    record["review_status"] = "verified_with_exceptions"
    record["exceptions"] = [{
        "type": "wrong_order", "production_line_id": "line-a",
        "token_ids": ["token-1", "token-2"], "ordered_token_ids": ["token-2", "token-1"],
    }]
    result = score(geometry, ledger)
    assert result["resolved_token_membership"]["accuracy"] == 1.0
    assert result["within_line_order"]["accuracy"] == 0.0
    assert result["exact_physical_lines"]["exact_production_matches"] == 0


class ImageReferenceParser(HTMLParser):
    """Collect image URLs from both linked-image and inline-image markup."""

    def __init__(self):
        super().__init__()
        self.references: list[str] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        for name in (("src",) if tag == "img" else ("href",) if tag == "a" else ()):
            target = attributes.get(name)
            if target and urlsplit(target).path.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                self.references.append(target)


def test_generated_review_image_references_resolve_from_index_directory():
    review_dir = MODULE_PATH.parent / "review"
    page_count = review.generate_index()
    html = (review_dir / "index.html").read_text(encoding="utf-8")
    parser = ImageReferenceParser()
    parser.feed(html)

    resolved_targets = [(review_dir / target).resolve() for target in parser.references]
    unique_targets = set(resolved_targets)
    assert page_count == 11
    assert len(unique_targets) == 22
    assert len(parser.references) == 44
    assert all(target.is_file() for target in resolved_targets)
    assert "README-human-review.md" in html
    assert "README.md" not in html
