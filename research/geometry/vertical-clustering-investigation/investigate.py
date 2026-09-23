"""Research-only comparison of greedy and bounded vertical grouping models.

The production baseline is called directly from ``normalize.geometry``.  The
alternative models below are deliberately local to this research directory;
their outputs are observations for comparison and never production inputs.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import subprocess
import sys
from collections import defaultdict
from dataclasses import replace
from pathlib import Path
from statistics import median
from typing import Any, Mapping, Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ROOT = Path(__file__).resolve().parent
BASELINE_COMMIT = "c0f7ea88493a07e6139e9c71d413a2eda130c17b"
GEOMETRY_SHA256 = "15f351c93bf45e95a3d9db136af7415433833d51f9e1d7c1af48b81c6c1e64b5"
ORACLE_SHA256 = "58e47415dc21e285debda2a4d0112d3289ea781387704f04e8d55c2552b2bf44"
RESIDUAL_ROOT = REPOSITORY_ROOT / "research/geometry/residual-forensics"
DIAGNOSTIC_SCRIPT = REPOSITORY_ROOT / "research/geometry/diagnostic-investigation/investigate.py"
RECOVERED_ROOT = ROOT / "recovered-inputs"

sys.path.insert(0, str(REPOSITORY_ROOT))

import normalize.geometry as production_geometry  # noqa: E402
from normalize.geometry import TSV_HEADER, group_physical_lines, parse_tsv_rows  # noqa: E402
from tests.geometry_oracle import canonical_geometry_state, canonical_serialized_page_state  # noqa: E402


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def display_path(path: Path) -> str:
    resolved = path.resolve()
    if resolved.is_relative_to(REPOSITORY_ROOT):
        return str(resolved.relative_to(REPOSITORY_ROOT))
    return str(resolved)


def _jsonable(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


def _digest(value: Any) -> str:
    return _sha256_bytes(json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":")).encode())


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPOSITORY_ROOT, check=True, text=True, capture_output=True
    ).stdout.strip()


def _token_from_record(record: Mapping[str, Any]) -> production_geometry._Token:
    evidence = record["evidence_only"]
    return production_geometry._Token(
        record["source_row"],
        record["text"],
        record["confidence"],
        5,
        1,
        evidence["tesseract_block_num"],
        evidence["tesseract_par_num"],
        evidence["tesseract_line_num"],
        evidence["tesseract_word_num"],
        record["x_px"],
        record["y_px"],
        record["width_px"],
        record["height_px"],
    )


def _load_geometry(fixture_id: str) -> dict[str, Any]:
    return json.loads((RESIDUAL_ROOT / fixture_id / "geometry.json").read_text(encoding="utf-8"))


def _page_tokens(page: Mapping[str, Any]) -> list[production_geometry._Token]:
    return [_token_from_record(record) for record in page["tokens"]]


def _row_state(state: tuple[Any, ...]) -> dict[tuple[str, str, int], dict[str, Any]]:
    return {
        tuple(item[0]): {
            "text": item[1],
            "resolved_assignment": item[2],
            "candidate_lines": list(item[3]),
            "uncertainty": item[4],
            "box": {"x": item[5], "y": item[6], "width": item[7], "height": item[8]},
        }
        for item in state[0]
    }


def _assignment_summary(state: tuple[Any, ...]) -> list[dict[str, Any]]:
    return [
        {"identity": list(identity), **record}
        for identity, record in sorted(_row_state(state).items())
    ]


def _state_differences(left: tuple[Any, ...], right: tuple[Any, ...]) -> dict[str, Any]:
    left_rows = _row_state(left)
    right_rows = _row_state(right)
    identities = sorted(set(left_rows) | set(right_rows))
    differences = []
    for identity in identities:
        if left_rows.get(identity) != right_rows.get(identity):
            differences.append({"identity": list(identity), "left": left_rows.get(identity), "right": right_rows.get(identity)})
    return {
        "different_token_states": len(differences),
        "differences": differences,
        # The oracle's in-memory representation uses tuples while JSON-loaded
        # research results use lists.  Equality here is semantic equality of
        # the canonical state, not an incidental container-type comparison.
        "complete_state_equal": not differences and _jsonable(left[1:]) == _jsonable(right[1:]),
    }


def _canonical_states_equal(left: tuple[Any, ...], right: tuple[Any, ...]) -> bool:
    """Compare oracle states after removing only Python tuple/list variance."""

    return _jsonable(left) == _jsonable(right)


def _production_observation(fixture_id: str, page: Mapping[str, Any]) -> dict[str, Any]:
    tokens = _page_tokens(page)
    result = group_physical_lines(tokens)
    state = canonical_geometry_state(fixture_id, page["side"], tokens, *result)
    serialized = canonical_serialized_page_state(fixture_id, page)
    reversed_tokens = list(reversed(tokens))
    reversed_state = canonical_geometry_state(
        fixture_id,
        page["side"],
        reversed_tokens,
        *group_physical_lines(reversed_tokens),
    )
    return {
        "model": "production-greedy-control",
        "physical_lines": result[0],
        "unresolved": result[1],
        "measurements": result[2],
        "canonical_state": _jsonable(state),
        "canonical_state_sha256": _digest(state),
        "matches_versioned_geometry": state == serialized,
        "permutation_stable": _canonical_states_equal(state, reversed_state),
        "assignments": _assignment_summary(state),
    }


def _adjusted(token: production_geometry._Token, slope: float) -> float:
    return production_geometry._adjusted_center_y(token, slope)


def _model_parameters(tokens: Sequence[production_geometry._Token], slope: float) -> dict[str, Any]:
    height_median = float(median(token.height for token in tokens if token.height > 0))
    tolerance = max(1, math.floor(height_median / 4 + 0.5))
    return {
        "token_height_median_px": height_median,
        "tolerance_px": tolerance,
        "tolerance_formula": "max(1, floor(median(token.height_px) / 4 + 0.5))",
        "horizontal_gap_limit_px": production_geometry._horizontal_gap_limit(tokens),
        "baseline_slope_px_per_px": slope,
        "horizontal_adjacency": "production _horizontally_adjacent predicate, used as evidence only",
    }


def _pair_compatible(left: production_geometry._Token, right: production_geometry._Token, tolerance: int, gap_limit: float, slope: float) -> bool:
    return (
        abs(_adjusted(left, slope) - _adjusted(right, slope)) <= tolerance
        and production_geometry._horizontally_adjacent(left, right, gap_limit)
    )


def _pairwise_components(tokens: Sequence[production_geometry._Token], tolerance: int, gap_limit: float, slope: float) -> list[dict[str, Any]]:
    """Build connected components from all pairwise geometric relationships."""

    parent = {id(token): id(token) for token in tokens}

    def find(item: int) -> int:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for index, left in enumerate(tokens):
        for right in tokens[index + 1 :]:
            if _pair_compatible(left, right, tolerance, gap_limit, slope):
                union(id(left), id(right))
    groups: dict[int, list[production_geometry._Token]] = defaultdict(list)
    for token in tokens:
        groups[find(id(token))].append(token)
    result = []
    for members in groups.values():
        ordered = sorted(members, key=lambda token: (token.x, token.y, token.source_row))
        result.append({
            "source_rows": [token.source_row for token in ordered],
            "members": ordered,
            "anchor_adjusted_center": min(_adjusted(token, slope) for token in members),
            "stable_center": median(_adjusted(token, slope) for token in members),
            "construction": "all pairwise compatible edges, then connected components",
        })
    return sorted(result, key=lambda group: (group["stable_center"], min(group["source_rows"])))


def _stable_anchor_groups(tokens: Sequence[production_geometry._Token], tolerance: int, gap_limit: float, slope: float) -> list[dict[str, Any]]:
    """Group in geometric order against a fixed anchor, never a drifting median."""

    ordered = sorted(tokens, key=lambda token: (_adjusted(token, slope), token.x, token.source_row))
    groups: list[dict[str, Any]] = []
    for token in ordered:
        candidates = [
            group
            for group in groups
            if abs(_adjusted(token, slope) - group["anchor_adjusted_center"]) <= tolerance
        ]
        if len(candidates) == 1:
            candidates[0]["members"].append(token)
        elif not candidates:
            groups.append({
                "source_rows": [],
                "members": [token],
                "anchor_adjusted_center": _adjusted(token, slope),
                "stable_center": _adjusted(token, slope),
                "construction": "geometric-order groups admitted only against fixed first-token anchor",
            })
        else:
            # Keep competing memberships visible rather than using token text
            # or input order to choose a row.  The adapter will expose this as
            # ambiguity when the candidate bands remain compatible.
            groups.append({
                "source_rows": [],
                "members": [token],
                "anchor_adjusted_center": _adjusted(token, slope),
                "stable_center": _adjusted(token, slope),
                "construction": "competing fixed anchors force a separate abstaining group",
            })
    for group in groups:
        group["members"] = sorted(group["members"], key=lambda token: (token.x, token.y, token.source_row))
        group["source_rows"] = [token.source_row for token in group["members"]]
    return sorted(groups, key=lambda group: (group["stable_center"], min(group["source_rows"])))


def _split_research_groups(groups: Sequence[Mapping[str, Any]], gap_limit: float) -> list[dict[str, Any]]:
    """Apply the existing horizontal extent split while retaining model metadata."""

    split: list[dict[str, Any]] = []
    for group in groups:
        ordered = sorted(group["members"], key=lambda token: (token.x, token.source_row))
        current: list[production_geometry._Token] = []
        covered_right: int | None = None
        for token in ordered:
            if current and covered_right is not None and token.x - covered_right > gap_limit:
                split.append({**group, "members": current, "source_rows": [item.source_row for item in current]})
                current = []
                covered_right = None
            current.append(token)
            covered_right = max(covered_right or token.x1, token.x1)
        if current:
            split.append({**group, "members": current, "source_rows": [item.source_row for item in current]})
    return sorted(split, key=lambda group: (group["stable_center"], min(group["source_rows"])))


def _research_model_observation(
    fixture_id: str,
    page: Mapping[str, Any],
    model_name: str,
    group_builder: Any,
    tokens_override: Sequence[production_geometry._Token] | None = None,
) -> dict[str, Any]:
    tokens = list(tokens_override) if tokens_override is not None else _page_tokens(page)
    if not tokens:
        state = canonical_geometry_state(fixture_id, page["side"], [], [], [], {"research_model": model_name})
        return {
            "model": model_name,
            "parameters": {},
            "pre_horizontal_groups": [],
            "post_horizontal_groups": [],
            "horizontal_split_changed_group_count": False,
            "physical_lines": [],
            "unresolved": [],
            "candidate_details": {},
            "canonical_state": _jsonable(state),
            "canonical_state_sha256": _digest(state),
            "permutation_stable": True,
            "assignments": [],
        }
    height_median = float(median(token.height for token in tokens if token.height > 0))
    tolerance = max(1, math.floor(height_median / 4 + 0.5))
    slope = production_geometry._estimate_baseline_slope(tokens, tolerance)
    gap_limit = production_geometry._horizontal_gap_limit(tokens)
    groups = group_builder(tokens, tolerance, gap_limit, slope)
    split_groups = _split_research_groups(groups, gap_limit)
    ordered_groups = sorted(
        enumerate(split_groups),
        key=lambda pair: (pair[1]["stable_center"], min(pair[1]["source_rows"]), pair[0]),
    )
    line_ids = {index: f"research-{model_name}-line-{ordinal:04d}" for ordinal, (index, _group) in enumerate(ordered_groups, start=1)}

    candidates: dict[int, list[str]] = {}
    candidate_details: dict[int, list[dict[str, Any]]] = {}
    for token in tokens:
        token_candidates = []
        details = []
        adjusted = _adjusted(token, slope)
        for index, group in ordered_groups:
            members = group["members"]
            stable_center = float(group["stable_center"])
            delta = abs(adjusted - stable_center)
            in_group = token in members
            median_support = delta <= tolerance
            neighbor_support = any(
                abs(adjusted - _adjusted(item, slope)) <= tolerance
                and production_geometry._horizontally_adjacent(item, token, gap_limit)
                for item in members
                if item is not token
            )
            interval_support = min(item.x for item in members) <= token.x <= max(item.x1 for item in members)
            horizontal_support = production_geometry._horizontal_candidate_supported(members, token, gap_limit)
            accepted = (in_group and (median_support or neighbor_support)) or (median_support and interval_support and horizontal_support)
            details.append({
                "line_id": line_ids[index],
                "source_rows": list(group["source_rows"]),
                "stable_center": stable_center,
                "token_adjusted_center": adjusted,
                "absolute_delta": delta,
                "in_group": in_group,
                "median_support": median_support,
                "neighbor_support": neighbor_support,
                "x_interval_support": interval_support,
                "horizontal_support": horizontal_support,
                "accepted": accepted,
            })
            if accepted:
                token_candidates.append(line_ids[index])
        candidates[id(token)] = token_candidates
        candidate_details[id(token)] = details

    assignments: dict[str, list[production_geometry._Token]] = {line_id: [] for line_id in line_ids.values()}
    unresolved: list[dict[str, Any]] = []
    for token in tokens:
        current = candidates[id(token)]
        if len(current) == 1:
            assignments[current[0]].append(token)
        elif len(current) > 1:
            unresolved.append({"code": "ambiguous_line_assignment", "token_source_row": token.source_row, "candidate_line_ids": current})
        else:
            unresolved.append({"code": "unassigned_line_assignment", "token_source_row": token.source_row, "candidate_line_ids": []})
    unresolved.sort(key=lambda item: item["token_source_row"])
    unresolved_by_line = defaultdict(list)
    for item in unresolved:
        for line_id in item["candidate_line_ids"]:
            unresolved_by_line[line_id].append(item["token_source_row"])

    lines = []
    has_unassigned = any(item["code"] == "unassigned_line_assignment" for item in unresolved)
    for index, group in ordered_groups:
        line_id = line_ids[index]
        assigned = sorted(assignments[line_id], key=lambda token: (token.x, token.y, token.source_row))
        ambiguous = [token for token in tokens if token.source_row in unresolved_by_line[line_id]]
        bounds_tokens = assigned + ambiguous or list(group["members"])
        lines.append({
            "line_id": line_id,
            "token_ids": [f"token-{token.source_row:04d}" for token in assigned],
            "unresolved_token_source_rows": sorted(unresolved_by_line[line_id]),
            "left_px": None if has_unassigned else min(token.x for token in bounds_tokens),
            "top_px": None if has_unassigned else min(token.y for token in bounds_tokens),
            "right_px": None if has_unassigned else max(token.x1 for token in bounds_tokens),
            "bottom_px": None if has_unassigned else max(token.y1 for token in bounds_tokens),
            "line_height_px": None if has_unassigned or ambiguous else max(token.y1 for token in bounds_tokens) - min(token.y for token in bounds_tokens),
            "median_center_y_px": float(median(token.center_y for token in group["members"])),
            "stable_group_center_adjusted_px": group["stable_center"],
        })
    for index, line in enumerate(lines[:-1]):
        line["vertical_gap_to_next_px"] = None if line["line_height_px"] is None or lines[index + 1]["line_height_px"] is None else lines[index + 1]["top_px"] - line["bottom_px"]
    if lines:
        lines[-1]["vertical_gap_to_next_px"] = None

    result = (
        lines,
        unresolved,
        {
            **_model_parameters(tokens, slope),
            "research_model": model_name,
            "grouping_input": "token boxes only; OCR text and generated OCR line labels ignored",
        },
    )
    state = canonical_geometry_state(fixture_id, page["side"], tokens, *result)
    reversed_tokens = list(reversed(tokens))
    reversed_result = _research_model_observation_from_tokens(fixture_id, page, model_name, group_builder, reversed_tokens)
    reversed_state = reversed_result["state"]
    return {
        "model": model_name,
        "parameters": _model_parameters(tokens, slope),
        "pre_horizontal_groups": [{key: value for key, value in group.items() if key not in {"members"}} for group in groups],
        "post_horizontal_groups": [{key: value for key, value in group.items() if key not in {"members"}} for group in split_groups],
        "horizontal_split_changed_group_count": len(groups) != len(split_groups),
        "physical_lines": lines,
        "unresolved": unresolved,
        "candidate_details": {
            str(token.source_row): candidate_details[id(token)] for token in tokens
        },
        "canonical_state": _jsonable(state),
        "canonical_state_sha256": _digest(state),
        "permutation_stable": _canonical_states_equal(state, reversed_state),
        "assignments": _assignment_summary(state),
    }


def _research_model_observation_from_tokens(
    fixture_id: str,
    page: Mapping[str, Any],
    model_name: str,
    group_builder: Any,
    tokens: Sequence[production_geometry._Token],
) -> dict[str, Any]:
    # The adapter mirrors the model's finalization without recursively testing
    # permutation stability.  It exists only to obtain the canonical state.
    if not tokens:
        return {"state": canonical_geometry_state(fixture_id, page["side"], [], [], [], {"research_model": model_name})}
    height_median = float(median(token.height for token in tokens if token.height > 0))
    tolerance = max(1, math.floor(height_median / 4 + 0.5))
    slope = production_geometry._estimate_baseline_slope(tokens, tolerance)
    gap_limit = production_geometry._horizontal_gap_limit(tokens)
    groups = group_builder(tokens, tolerance, gap_limit, slope)
    split_groups = _split_research_groups(groups, gap_limit)
    ordered_groups = sorted(enumerate(split_groups), key=lambda pair: (pair[1]["stable_center"], min(pair[1]["source_rows"]), pair[0]))
    line_ids = {index: f"research-{model_name}-line-{ordinal:04d}" for ordinal, (index, _group) in enumerate(ordered_groups, start=1)}
    candidates: dict[int, list[str]] = {}
    for token in tokens:
        current = []
        adjusted = _adjusted(token, slope)
        for index, group in ordered_groups:
            members = group["members"]
            median_support = abs(adjusted - group["stable_center"]) <= tolerance
            neighbor_support = any(abs(adjusted - _adjusted(item, slope)) <= tolerance and production_geometry._horizontally_adjacent(item, token, gap_limit) for item in members if item is not token)
            interval_support = min(item.x for item in members) <= token.x <= max(item.x1 for item in members)
            horizontal_support = production_geometry._horizontal_candidate_supported(members, token, gap_limit)
            if (token in members and (median_support or neighbor_support)) or (median_support and interval_support and horizontal_support):
                current.append(line_ids[index])
        candidates[id(token)] = current
    assignments = {line_id: [] for line_id in line_ids.values()}
    unresolved = []
    for token in tokens:
        current = candidates[id(token)]
        if len(current) == 1:
            assignments[current[0]].append(token)
        elif len(current) > 1:
            unresolved.append({"code": "ambiguous_line_assignment", "token_source_row": token.source_row, "candidate_line_ids": current})
        else:
            unresolved.append({"code": "unassigned_line_assignment", "token_source_row": token.source_row, "candidate_line_ids": []})
    unresolved.sort(key=lambda item: item["token_source_row"])
    unresolved_by_line = defaultdict(list)
    for item in unresolved:
        for line_id in item["candidate_line_ids"]:
            unresolved_by_line[line_id].append(item["token_source_row"])
    lines = []
    has_unassigned = any(item["code"] == "unassigned_line_assignment" for item in unresolved)
    for index, group in ordered_groups:
        line_id = line_ids[index]
        assigned = sorted(assignments[line_id], key=lambda token: (token.x, token.y, token.source_row))
        ambiguous = [token for token in tokens if token.source_row in unresolved_by_line[line_id]]
        bounds_tokens = assigned + ambiguous or list(group["members"])
        lines.append({
            "line_id": line_id,
            "token_ids": [f"token-{token.source_row:04d}" for token in assigned],
            "unresolved_token_source_rows": sorted(unresolved_by_line[line_id]),
            "left_px": None if has_unassigned else min(token.x for token in bounds_tokens),
            "top_px": None if has_unassigned else min(token.y for token in bounds_tokens),
            "right_px": None if has_unassigned else max(token.x1 for token in bounds_tokens),
            "bottom_px": None if has_unassigned else max(token.y1 for token in bounds_tokens),
            "line_height_px": None if has_unassigned or ambiguous else max(token.y1 for token in bounds_tokens) - min(token.y for token in bounds_tokens),
            "median_center_y_px": float(median(token.center_y for token in group["members"])),
            "vertical_gap_to_next_px": None,
        })
    for index, line in enumerate(lines[:-1]):
        line["vertical_gap_to_next_px"] = (
            None
            if line["line_height_px"] is None or lines[index + 1]["line_height_px"] is None
            else lines[index + 1]["top_px"] - line["bottom_px"]
        )
    result = (
        lines,
        unresolved,
        {
            **_model_parameters(tokens, slope),
            "research_model": model_name,
            "grouping_input": "token boxes only; OCR text and generated OCR line labels ignored",
        },
    )
    return {"state": canonical_geometry_state(fixture_id, page["side"], tokens, *result)}


def _state_projection(result: Mapping[str, Any]) -> tuple[Any, ...]:
    return tuple(tuple(item) if isinstance(item, list) else item for item in result["canonical_state"])


def _synthetic_row(text: str, x: int, y: int, width: int, height: int, word: int) -> str:
    return "\t".join(map(str, (5, 1, 1, 1, 1, word, x, y, width, height, 95, text)))


def _synthetic_tokens(rows: Sequence[str]) -> list[production_geometry._Token]:
    tsv = "\t".join(TSV_HEADER) + "\n" + "\n".join(rows) + "\n"
    tokens, errors = parse_tsv_rows(tsv, 500, 220)
    if errors:
        raise AssertionError(errors)
    return tokens


def _synthetic_cases() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "continuous_varying_heights",
            "physical_interpretation": "one continuous printed row with differing token heights",
            "rows": [_synthetic_row("a", 10, 20, 20, 10, 1), _synthetic_row("b", 50, 18, 20, 14, 2), _synthetic_row("c", 90, 22, 20, 8, 3)],
        },
        {
            "case_id": "center_chain_median_drift",
            "physical_interpretation": "one row represented by a center-coordinate chain; construction tests median drift, not a production truth label",
            "rows": [_synthetic_row("a", 10, 15, 20, 10, 1), _synthetic_row("b", 40, 18, 20, 10, 2), _synthetic_row("c", 70, 21, 20, 10, 3), _synthetic_row("d", 100, 24, 20, 10, 4)],
        },
        {
            "case_id": "horizontal_fragmentation_continuous",
            "physical_interpretation": "one row with large horizontal gaps; continuity is not established by boxes alone",
            "rows": [_synthetic_row("a", 10, 20, 15, 10, 1), _synthetic_row("b", 100, 20, 15, 10, 2), _synthetic_row("c", 190, 20, 15, 10, 3)],
        },
        {
            "case_id": "distinct_nearby_same_column",
            "physical_interpretation": "two distinct nearby rows in one column",
            "rows": [_synthetic_row("a", 10, 20, 25, 10, 1), _synthetic_row("b", 10, 31, 25, 10, 2), _synthetic_row("c", 10, 50, 25, 10, 3)],
        },
        {
            "case_id": "overlapping_separate_rows",
            "physical_interpretation": "two rows whose rectangles overlap vertically while horizontal positions interleave",
            "rows": [_synthetic_row("a", 10, 20, 30, 18, 1), _synthetic_row("b", 55, 20, 30, 18, 2), _synthetic_row("c", 10, 31, 30, 18, 3), _synthetic_row("d", 55, 31, 30, 18, 4)],
        },
        {
            "case_id": "sparse_weak_horizontal_evidence",
            "physical_interpretation": "same-center tokens separated beyond the local horizontal gap evidence",
            "rows": [_synthetic_row("a", 10, 20, 12, 10, 1), _synthetic_row("b", 220, 20, 12, 10, 2)],
        },
        {
            "case_id": "skewed_rows",
            "physical_interpretation": "two continuous rows with a shared page slope",
            "rows": [_synthetic_row("a", 10, 35, 20, 10, 1), _synthetic_row("b", 100, 30, 20, 10, 2), _synthetic_row("c", 190, 25, 20, 10, 3), _synthetic_row("d", 10, 65, 20, 10, 4), _synthetic_row("e", 100, 60, 20, 10, 5), _synthetic_row("f", 190, 55, 20, 10, 6)],
        },
        {
            "case_id": "multiple_row_compatibility",
            "physical_interpretation": "a token lies within geometric tolerance of competing rows; abstention is the admissible outcome",
            "rows": [_synthetic_row("a", 10, 20, 30, 10, 1), _synthetic_row("b", 80, 20, 30, 10, 2), _synthetic_row("c", 10, 26, 30, 10, 3), _synthetic_row("d", 80, 26, 30, 10, 4), _synthetic_row("x", 45, 23, 20, 10, 5)],
        },
    ]


def _model_runs(fixture_id: str, page: Mapping[str, Any]) -> dict[str, Any]:
    builders = {
        "pairwise-components": _pairwise_components,
        "stable-anchor-groups": _stable_anchor_groups,
    }
    outputs = {}
    for name, builder in builders.items():
        outputs[name] = _research_model_observation(fixture_id, page, name, builder)
    return outputs


def _synthetic_results() -> list[dict[str, Any]]:
    results = []
    for case in _synthetic_cases():
        tokens = _synthetic_tokens(case["rows"])
        page = {"side": "synthetic"}
        baseline_result = group_physical_lines(tokens)
        baseline_state = canonical_geometry_state(case["case_id"], "synthetic", tokens, *baseline_result)
        models = {}
        for name, builder in {
            "pairwise-components": _pairwise_components,
            "stable-anchor-groups": _stable_anchor_groups,
        }.items():
            models[name] = _research_model_observation(case["case_id"], page, name, builder, tokens)
            models[name]["difference_from_production"] = _state_differences(baseline_state, _state_projection(models[name]))
        perturbation_tokens = [replace(token, y=token.y + (1 if token.source_row == tokens[0].source_row else 0)) for token in tokens]
        perturbation_page = {"side": "synthetic"}
        perturbations = {}
        for name, builder in {
            "pairwise-components": _pairwise_components,
            "stable-anchor-groups": _stable_anchor_groups,
        }.items():
            perturbed = _research_model_observation_from_tokens(case["case_id"], perturbation_page, name, builder, perturbation_tokens)
            original = _state_projection(models[name])
            perturbations[name] = {"changed_by_one_pixel": original != perturbed["state"], "perturbed_state_sha256": _digest(perturbed["state"])}
        results.append({
            "case_id": case["case_id"],
            "physical_interpretation_by_construction": case["physical_interpretation"],
            "rows": case["rows"],
            "token_identities": [[case["case_id"], "synthetic", token.source_row] for token in tokens],
            "production": {
                "canonical_state": _jsonable(baseline_state),
                "canonical_state_sha256": _digest(baseline_state),
                "assignments": _assignment_summary(baseline_state),
            },
            "models": models,
            "input_permutation_stability": {name: data["permutation_stable"] for name, data in models.items()},
            "one_pixel_perturbation": perturbations,
        })
    return results


def _residual_results() -> dict[str, Any]:
    selected = {
        "relativity_pdf10_pp26-27": {"left": [213, 216, 217, 226, 227], "right": [246]},
        "relativity_pdf17_pp40-41": {"right": [23]},
    }
    results = {}
    for fixture_id, sides in selected.items():
        geometry = _load_geometry(fixture_id)
        fixture_result = {}
        for page in geometry["pages"]:
            if page["side"] not in sides:
                continue
            production = _production_observation(fixture_id, page)
            models = _model_runs(fixture_id, page)
            # Preserve complete assignment states and all groups/line
            # measurements, but retain verbose candidate diagnostics only for
            # the selected residual identities.  The diagnostic details for
            # every other token are redundant with those complete states and
            # made the evidence dump unnecessarily large.
            selected_rows = set(sides[page["side"]])
            for model in models.values():
                model["candidate_details"] = {
                    row: details
                    for row, details in model["candidate_details"].items()
                    if int(row) in selected_rows
                }
            residual = []
            for row in sides[page["side"]]:
                record = next(token for token in page["tokens"] if token["source_row"] == row)
                residual.append({"identity": [fixture_id, page["side"], row], "text": record["text"], "box": {key: record[f"{key}_px"] for key in ("x", "y", "width", "height")}, "production": {"physical_line_id": record["physical_line_id"], "candidate_line_ids": record["candidate_line_ids"]}, "models": {name: next(item for item in model["assignments"] if item["identity"][2] == row) for name, model in models.items()}})
            fixture_result[page["side"]] = {
                "production": production,
                "models": models,
                "residual_token_traces": residual,
            }
        results[fixture_id] = fixture_result
    return results


def _fixture_controls() -> list[dict[str, Any]]:
    controls = []
    for fixture_id in ("relativity_pdf23_pp52-53", "stella_maris_pdf03_session-I", "stella_maris_pdf06_dense-dialogue", "stella_maris_pdf18_session-II_p35"):
        geometry = _load_geometry(fixture_id)
        pages = []
        for page in geometry["pages"]:
            production = _production_observation(fixture_id, page)
            models = _model_runs(fixture_id, page)
            production_state = _state_projection(production)
            pages.append({
                "side": page["side"],
                "token_count": len(page["tokens"]),
                "production_unresolved_count": len(production["unresolved"]),
                "production_state_sha256": production["canonical_state_sha256"],
                "models": {
                    name: {
                        "unresolved_count": len(model["unresolved"]),
                        "state_sha256": model["canonical_state_sha256"],
                        "difference_from_production": _state_differences(production_state, _state_projection(model)),
                        "permutation_stable": model["permutation_stable"],
                    }
                    for name, model in models.items()
                },
            })
        controls.append({"fixture_id": fixture_id, "recorded_status": geometry["status"], "pages": pages})
    return controls


def _production_trace() -> dict[str, Any]:
    spec = importlib.util.spec_from_file_location("prior_vertical_diagnostics", DIAGNOSTIC_SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load preserved diagnostic script: {DIAGNOSTIC_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    traces = {}
    for fixture_id, sides in {
        "relativity_pdf10_pp26-27": {"left": [213, 216, 217, 226, 227], "right": [246]},
        "relativity_pdf17_pp40-41": {"right": [23]},
    }.items():
        geometry = _load_geometry(fixture_id)
        for page in geometry["pages"]:
            if page["side"] not in sides:
                continue
            trace = module._vertical_trace(page, fixture_id)
            traces[f"{fixture_id}/{page['side']}"] = {
                "source_script": display_path(DIAGNOSTIC_SCRIPT),
                "source_script_sha256": sha256(DIAGNOSTIC_SCRIPT),
                "trace": trace,
            }
    return traces


def _recovery_ledger() -> dict[str, Any]:
    records = [
        ("relativity_pdf10_pp26-27", "relativity_pdf10_pp26-27.left.png", "b1e565113b99fe716ec1338868717f11129acb8957417405e3da1a52ad102820", "derived_unannotated_preprocessed_page"),
        ("relativity_pdf10_pp26-27", "relativity_pdf10_pp26-27.right.png", "fa7c69021d1f6c5c269154b1ae53bc602acedd05965beee3f9d480592d997eeb", "derived_unannotated_preprocessed_page"),
        ("relativity_pdf10_pp26-27", "relativity_pdf10_pp26-27.preprocess.json", "ee3365aeb0aecb71569249c088a86572804be277288de1a75500fc63419e81e1", "preprocessing_metadata"),
        ("relativity_pdf17_pp40-41", "relativity_pdf17_pp40-41.right.png", "8c9d22680260bb86d76c06cb134f1383dbffbecc6cdb8a23730823f05b8db80e", "derived_unannotated_preprocessed_page"),
        ("relativity_pdf17_pp40-41", "relativity_pdf17_pp40-41.preprocess.json", "15c977994eb090842321efe38e280c2fa180b064aaf99d4a4f39c2cf227da95b", "preprocessing_metadata"),
    ]
    recovered = []
    for fixture_id, filename, source_hash, kind in records:
        destination = RECOVERED_ROOT / fixture_id / filename
        recovered.append({
            "kind": kind,
            "temporary_source_at_recovery": f"/tmp/normalize-residual-forensics/{fixture_id}/preprocessed/{filename}",
            "source_was_present_at_recovery": True,
            "source_sha256": source_hash,
            "repository_destination": display_path(destination),
            "repository_sha256": sha256(destination),
            "source_pdf_committed": False,
            "permission_basis": "AUTHORITY.md permits derived page rendering/layout evidence; source PDFs remain untracked and are not copied",
        })
    not_recovered = [
        {"artifact_class": "spread PNGs and other preprocessed page sides", "decision": "not imported; not required for the selected residual traces or four geometry regression controls"},
        {"artifact_class": "temporary manifest stdout and disposable intermediates", "decision": "not imported; versioned manifests and repository artifacts are sufficient"},
    ]
    return {
        "recovery_status": "exact files recovered before experiments",
        "recovered": recovered,
        "not_recovered_from_related_temp_tree": not_recovered,
        "missing_expected_files": [],
        "temporary_originals_modified_or_deleted": False,
        "limitation": "The recovered derived images are versioned research evidence; source PDFs remain local inputs referenced only by recorded hashes and metadata.",
    }


def _real_scan_evidence() -> list[dict[str, Any]]:
    """Identify durable pixel evidence without making it grouping authority."""

    records = [
        ("relativity_pdf10_pp26-27", "left", "relativity_pdf10_pp26-27.left.png", [213, 216, 217, 226, 227]),
        ("relativity_pdf10_pp26-27", "right", "relativity_pdf10_pp26-27.right.png", [246]),
        ("relativity_pdf17_pp40-41", "right", "relativity_pdf17_pp40-41.right.png", [23]),
    ]
    evidence = []
    for fixture_id, side, filename, rows in records:
        path = RECOVERED_ROOT / fixture_id / filename
        evidence.append({
            "fixture_id": fixture_id,
            "side": side,
            "token_source_rows": rows,
            "image_path": display_path(path),
            "image_sha256": sha256(path),
            "image_size_bytes": path.stat().st_size,
            "use_in_this_investigation": "provenance-verified unannotated page availability and visual reference",
            "not_used_as": "an input to the box-only grouping models; no pixel-derived assignment was performed",
        })
    return evidence


def _environment() -> dict[str, Any]:
    packages = {}
    for name in ("normalize", "Pillow", "pytest", "numpy", "opencv-python-headless", "PyMuPDF", "pytesseract", "rapidfuzz"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = "not installed"
    return {
        "python": sys.version,
        "python_executable": sys.executable,
        "packages": packages,
        "tesseract": subprocess.run(["tesseract", "--version"], check=True, text=True, capture_output=True).stdout.splitlines()[0],
        "production_geometry_import_path": str(Path(production_geometry.__file__).resolve()),
    }


def _artifact_inventory() -> list[dict[str, Any]]:
    inventory = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.name == "manifest.json" or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        inventory.append({"path": display_path(path), "sha256": sha256(path), "size_bytes": path.stat().st_size})
    return inventory


def run(output: Path = ROOT, *, write_manifest: bool = True) -> dict[str, Any]:
    # The experiment is anchored to the published baseline, but the checked-in
    # reproduction script must remain runnable after this research commit is
    # created.  Source identity is therefore enforced by the production and
    # oracle hashes below; the manifest records the exact generation revision.
    if subprocess.run(
        ["git", "merge-base", "--is-ancestor", BASELINE_COMMIT, "HEAD"],
        cwd=REPOSITORY_ROOT,
    ).returncode != 0:
        raise AssertionError("vertical research must run from the published baseline or a descendant")
    if sha256(REPOSITORY_ROOT / "src/normalize/geometry.py") != GEOMETRY_SHA256:
        raise AssertionError("production geometry differs from the verified baseline")
    if sha256(REPOSITORY_ROOT / "tests/geometry_oracle.py") != ORACLE_SHA256:
        raise AssertionError("identity-complete oracle differs from the verified baseline")
    output.mkdir(parents=True, exist_ok=True)
    result = {
        "schema": "normalize-vertical-clustering-investigation-v1",
        "baseline_commit": BASELINE_COMMIT,
        "production_geometry_sha256": GEOMETRY_SHA256,
        "identity_complete_oracle_sha256": ORACLE_SHA256,
        "recovery": _recovery_ledger(),
        "baseline": {
            "current_residual_counts": {"relativity_pdf10_pp26-27": {"ambiguous": 4, "unassigned": 2}, "relativity_pdf17_pp40-41": {"ambiguous": 1, "unassigned": 0}, "total_unresolved": 7},
            "historical_gh11_twelve_token_result": "preserved as distinct evidence; not regenerated or explained here",
            "production_traces": _production_trace(),
        },
        "real_scan_evidence": _real_scan_evidence(),
        "model_definitions": {
            "production-greedy-control": {
                "evidence": "production group_physical_lines output",
                "predicate": "current greedy adjusted-center admission, horizontal split, and final reconciliation",
                "abstention": "current ambiguity/unassigned uncertainty codes",
            },
            "pairwise-components": {
                "evidence": "all token-pair adjusted-center compatibility plus horizontal adjacency",
                "predicate": "union-find connected components over every compatible pair; no continuously drifting group median",
                "horizontal_treatment": "same bounded research horizontal extent split is applied after component construction",
                "competing_membership": "final candidate adapter evaluates every resulting group; multiple candidates remain ambiguous",
                "abstention": "zero candidates unassigned; multiple candidates ambiguous",
            },
            "stable-anchor-groups": {
                "evidence": "geometric-order tokens evaluated against a fixed first-token adjusted-center anchor",
                "predicate": "admit only when distance to the fixed anchor is within tolerance; anchor never drifts",
                "horizontal_treatment": "same bounded research horizontal extent split is applied after grouping",
                "competing_membership": "candidate adapter evaluates all stable groups; no text or OCR line labels choose",
                "abstention": "zero candidates unassigned; multiple candidates ambiguous",
            },
        },
        "synthetic_cases": _synthetic_results(),
        "real_scan_residuals": _residual_results(),
        "successful_fixture_controls": _fixture_controls(),
        "scope": {
            "production_assignments_modified": False,
            "pixel_evidence_integrated": False,
            "non_greedy_vertical_model_integrated": False,
            "fixture_expectations_modified": False,
        },
    }
    (output / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Keep recovery decisions independently inspectable.  This is a ledger,
    # not a second copy of the page evidence: it records provenance and the
    # decision not to import unrelated temporary material.
    (output / "provenance-ledger.json").write_text(
        json.dumps(
            {
                "schema": "normalize-vertical-clustering-recovery-ledger-v1",
                "baseline_commit": BASELINE_COMMIT,
                "recovery": result["recovery"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    if write_manifest:
        manifest = {
            "schema": "normalize-vertical-clustering-investigation-manifest-v1",
            "generated_at_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            "experiment_start": {"git_commit_sha": BASELINE_COMMIT, "git_branch": "vertical-clustering-investigation", "git_status": "clean (verified before research edits)"},
            "generation_state": {"git_commit_sha": _git("rev-parse", "HEAD"), "git_branch": _git("branch", "--show-current"), "git_status_porcelain": _git("status", "--short")},
            "environment": _environment(),
            "commands": [
                ".venv/bin/python research/geometry/vertical-clustering-investigation/investigate.py",
                ".venv/bin/python -m pytest -q tests/test_vertical_clustering_investigation.py",
                ".venv/bin/python -m pytest -q",
            ],
            "input_hashes": {
                "production_geometry": GEOMETRY_SHA256,
                "identity_complete_oracle": ORACLE_SHA256,
                "versioned_geometry_artifacts": [
                    {"path": display_path(path), "sha256": sha256(path)}
                    for path in sorted(RESIDUAL_ROOT.glob("*/geometry.json"))
                ],
                "recovered_inputs": result["recovery"]["recovered"],
            },
            "model_parameters": {"tolerance_formula": "max(1, floor(median(token.height_px) / 4 + 0.5))", "horizontal_gap_formula": "2 * median(token.width_px)", "source_text_used_for_grouping": False, "ocr_line_ids_used_for_grouping": False},
            "artifact_paths_and_hashes": _artifact_inventory(),
            "restrictions": {"production_geometry_modified": False, "identity_complete_oracle_modified": False, "existing_research_snapshots_modified": False, "fixture_contracts_modified": False, "source_pdfs_committed": False, "dependencies_installed": False, "symphony_modified": False},
        }
        (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT)
    args = parser.parse_args()
    result = run(args.output)
    print(json.dumps({"output": display_path(args.output), "synthetic_cases": len(result["synthetic_cases"]), "residual_fixture_count": len(result["real_scan_residuals"])}, indent=2))


if __name__ == "__main__":
    main()
