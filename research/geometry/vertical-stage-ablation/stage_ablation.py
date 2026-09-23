"""Research-only stage-isolated vertical grouping ablation.

The production API exposes the full geometry pipeline as one function.  This
module therefore copies only the small vertical pre-split loop and final
reconciliation needed to expose stage boundaries, while calling the actual
production horizontal splitter and support predicates.  The copied control is
admissible only when its complete identity-level state matches direct
production execution.
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
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Callable, Mapping, Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ROOT = Path(__file__).resolve().parent
GEOMETRY_ROOT = REPOSITORY_ROOT / "research/geometry/residual-forensics"
PRIOR_INVESTIGATION = REPOSITORY_ROOT / "research/geometry/vertical-clustering-investigation/investigate.py"
BASELINE_COMMIT = "dfa6cd1ef2387364dded5ba86f92635d94875b4d"
GEOMETRY_SHA256 = "15f351c93bf45e95a3d9db136af7415433833d51f9e1d7c1af48b81c6c1e64b5"
ORACLE_SHA256 = "58e47415dc21e285debda2a4d0112d3289ea781387704f04e8d55c2552b2bf44"

sys.path.insert(0, str(REPOSITORY_ROOT))

import normalize.geometry as production_geometry  # noqa: E402
from tests.geometry_oracle import canonical_geometry_state  # noqa: E402


def _load_prior_module() -> Any:
    spec = importlib.util.spec_from_file_location("prior_vertical_investigation", PRIOR_INVESTIGATION)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load prior investigation: {PRIOR_INVESTIGATION}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PRIOR = _load_prior_module()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPOSITORY_ROOT, check=True, text=True, capture_output=True
    ).stdout.strip()


def _is_ancestor(ancestor: str, revision: str) -> bool:
    return subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, revision],
        cwd=REPOSITORY_ROOT,
    ).returncode == 0


def _jsonable(value: Any) -> Any:
    if isinstance(value, float) and value.is_integer():
        # Direct production and the copied control can obtain the same
        # measurement as int versus float (for example 22 and 22.0).  They
        # are semantically equal, so digesting must not turn that container
        # representation detail into a false stage difference.
        return int(value)
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _source_rows(groups: Sequence[Sequence[Any]]) -> list[list[int]]:
    return [
        [token.source_row for token in sorted(group, key=lambda item: (item.x, item.y, item.source_row))]
        for group in groups
    ]


def _shared_parameters(tokens: Sequence[Any]) -> dict[str, Any]:
    if not tokens:
        return {
            "token_height_median_px": None,
            "tolerance_px": None,
            "baseline_slope_px_per_px": 0.0,
            "horizontal_gap_limit_px": None,
        }
    height_median = float(median(token.height for token in tokens if token.height > 0))
    tolerance = max(1, math.floor(height_median / 4 + 0.5))
    slope = production_geometry._estimate_baseline_slope(tokens, tolerance)
    return {
        "token_height_median_px": height_median,
        "tolerance_px": tolerance,
        "tolerance_formula": "max(1, floor(median(token.height_px) / 4 + 0.5))",
        "baseline_slope_px_per_px": slope,
        "horizontal_gap_limit_px": production_geometry._horizontal_gap_limit(tokens),
        "horizontal_gap_formula": "2 * median(token.width_px)",
    }


def _adjusted(token: Any, slope: float) -> float:
    return production_geometry._adjusted_center_y(token, slope)


def _production_vertical_groups(
    tokens: Sequence[Any], tolerance: int, slope: float
) -> list[list[Any]]:
    """Exact pre-split loop from production ``_line_bands``."""

    ordered = sorted(
        tokens,
        key=lambda token: (_adjusted(token, slope), token.x, token.source_row),
    )
    groups: list[list[Any]] = []
    gap_limit = production_geometry._horizontal_gap_limit(tokens)
    for token in ordered:
        if groups:
            current_median = median(_adjusted(item, slope) for item in groups[-1])
            median_support = abs(_adjusted(token, slope) - current_median) <= tolerance
            neighbor_support = any(
                abs(_adjusted(token, slope) - _adjusted(item, slope)) <= tolerance
                and production_geometry._horizontally_adjacent(item, token, gap_limit)
                for item in groups[-1]
            )
            if median_support or neighbor_support:
                groups[-1].append(token)
                continue
        groups.append([token])
    return groups


def _pairwise_vertical_groups(
    tokens: Sequence[Any], tolerance: int, gap_limit: float, slope: float
) -> list[list[Any]]:
    """Research alternative: all compatible vertical/horizontal pair edges."""

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
            if (
                abs(_adjusted(left, slope) - _adjusted(right, slope)) <= tolerance
                and production_geometry._horizontally_adjacent(left, right, gap_limit)
            ):
                union(id(left), id(right))
    grouped: dict[int, list[Any]] = defaultdict(list)
    for token in tokens:
        grouped[find(id(token))].append(token)
    return sorted(
        [
            sorted(group, key=lambda item: (item.x, item.y, item.source_row))
            for group in grouped.values()
        ],
        key=lambda group: (median(_adjusted(item, slope) for item in group), min(item.source_row for item in group)),
    )


def _fixed_anchor_vertical_groups(
    tokens: Sequence[Any], tolerance: int, _gap_limit: float, slope: float
) -> list[list[Any]]:
    """Research alternative: geometric-order groups with a non-drifting anchor."""

    ordered = sorted(tokens, key=lambda token: (_adjusted(token, slope), token.x, token.source_row))
    groups: list[dict[str, Any]] = []
    for token in ordered:
        compatible = [
            group
            for group in groups
            if abs(_adjusted(token, slope) - group["anchor"]) <= tolerance
        ]
        if len(compatible) == 1:
            compatible[0]["members"].append(token)
        else:
            # Zero or competing anchors are kept separate.  Later unchanged
            # reconciliation can expose ambiguity instead of selecting one.
            groups.append({"anchor": _adjusted(token, slope), "members": [token]})
    return [
        sorted(group["members"], key=lambda item: (item.x, item.y, item.source_row))
        for group in sorted(groups, key=lambda group: (group["anchor"], min(item.source_row for item in group["members"])))
    ]


def _ordered_groups(groups: Sequence[Sequence[Any]], slope: float) -> list[tuple[int, list[Any]]]:
    return sorted(
        enumerate(groups),
        key=lambda pair: (
            median(_adjusted(item, slope) for item in pair[1]),
            min(item.x for item in pair[1]),
            pair[0],
        ),
    )


def _reconcile(
    tokens: Sequence[Any], bands: Sequence[Sequence[Any]], tolerance: int, slope: float, gap_limit: float
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Exact final candidate/reconciliation logic from production."""

    ordered_bands = _ordered_groups(bands, slope)
    line_ids = {
        band_index: f"line-{ordinal:04d}"
        for ordinal, (band_index, _band) in enumerate(ordered_bands, start=1)
    }
    candidates: dict[int, list[str]] = {}
    for token in tokens:
        candidates[id(token)] = [
            line_ids[band_index]
            for band_index, band in ordered_bands
            if (
                (
                    token in band
                    and (
                        abs(
                            _adjusted(token, slope)
                            - median(_adjusted(item, slope) for item in band)
                        )
                        <= tolerance
                        or any(
                            abs(_adjusted(token, slope) - _adjusted(item, slope)) <= tolerance
                            and production_geometry._horizontally_adjacent(item, token, gap_limit)
                            for item in band
                            if item is not token
                        )
                    )
                )
                or (
                    abs(
                        _adjusted(token, slope)
                        - median(_adjusted(item, slope) for item in band)
                    )
                    <= tolerance
                    and min(item.x for item in band) <= token.x <= max(item.x1 for item in band)
                    and production_geometry._horizontal_candidate_supported(band, token, gap_limit)
                )
            )
        ]
    assignments: dict[str, list[Any]] = {line_id: [] for line_id in line_ids.values()}
    unresolved: list[dict[str, Any]] = []
    for token in tokens:
        token_candidates = candidates[id(token)]
        if len(token_candidates) == 1:
            assignments[token_candidates[0]].append(token)
        elif len(token_candidates) > 1:
            unresolved.append({"code": "ambiguous_line_assignment", "token_source_row": token.source_row, "candidate_line_ids": token_candidates})
        else:
            unresolved.append({"code": "unassigned_line_assignment", "token_source_row": token.source_row, "candidate_line_ids": []})
    unresolved.sort(key=lambda item: item["token_source_row"])
    ambiguous_tokens_by_line: dict[str, list[Any]] = {line_id: [] for line_id in line_ids.values()}
    has_unassigned_token = False
    for token in tokens:
        token_candidates = candidates[id(token)]
        if len(token_candidates) > 1:
            for candidate_line_id in token_candidates:
                ambiguous_tokens_by_line[candidate_line_id].append(token)
        elif not token_candidates:
            has_unassigned_token = True
    affected_line_ids = {
        line_id
        for line_id, unresolved_tokens in ambiguous_tokens_by_line.items()
        if unresolved_tokens
    }
    lines: list[dict[str, Any]] = []
    for band_index, band in ordered_bands:
        line_id = line_ids[band_index]
        assigned = sorted(assignments[line_id], key=lambda token: (token.x, token.y, token.source_row))
        bounds_tokens = assigned + ambiguous_tokens_by_line[line_id]
        numeric_bounds_tokens = bounds_tokens or band
        bounds = {
            "left_px": min(token.x for token in numeric_bounds_tokens),
            "right_px": max(token.x1 for token in numeric_bounds_tokens),
            "top_px": min(token.y for token in numeric_bounds_tokens),
            "bottom_px": max(token.y1 for token in numeric_bounds_tokens),
        }
        if has_unassigned_token:
            bounds = {key: None for key in bounds}
        line_height = None if has_unassigned_token or line_id in affected_line_ids else bounds["bottom_px"] - bounds["top_px"]
        lines.append({
            "line_id": line_id,
            "token_ids": [f"token-{token.source_row:04d}" for token in assigned],
            "unresolved_token_source_rows": [item["token_source_row"] for item in unresolved if line_id in item["candidate_line_ids"]],
            **bounds,
            "line_height_px": line_height,
            "median_center_y_px": float(median(token.center_y for token in band)),
        })
    for index, line in enumerate(lines):
        next_line = lines[index + 1] if index + 1 < len(lines) else None
        line["vertical_gap_to_next_px"] = (
            None
            if next_line is None
            or has_unassigned_token
            or line["line_id"] in affected_line_ids
            or next_line["line_id"] in affected_line_ids
            else next_line["top_px"] - line["bottom_px"]
        )
    line_heights = [line["line_height_px"] for line in lines]
    measurements = {
        "token_height_median_px": float(median(token.height for token in tokens if token.height > 0)) if tokens else None,
        "tolerance_formula": "max(1, floor(token_height_median_px / 4 + 0.5))",
        "tolerance_px": tolerance,
        "horizontal_gap_formula": "2 * median(token_width_px); region extent is cumulative and unsupported oversized bridge boxes split",
        "horizontal_gap_limit_px": gap_limit,
        "baseline_slope_formula": "bounded coordinate cohesion search from -0.100 to 0.100 px/px in 0.001 px/px steps; nonzero candidates require >=2 multi-token continuous bands and improved cohesion",
        "baseline_slope_px_per_px": slope,
        "line_height_median_px": None if has_unassigned_token or affected_line_ids else (median(line_heights) if line_heights else None),
        "line_gaps": [
            {
                "line_id": line["line_id"],
                "next_line_id": lines[index + 1]["line_id"],
                "signed_vertical_gap_px": (
                    None
                    if has_unassigned_token
                    or line["line_id"] in affected_line_ids
                    or lines[index + 1]["line_id"] in affected_line_ids
                    else line["vertical_gap_to_next_px"]
                ),
            }
            for index, line in enumerate(lines[:-1])
        ],
    }
    return lines, unresolved, measurements


def assignment_projection(state: Sequence[Any]) -> dict[str, Any]:
    """Extract assignment semantics, excluding coordinates and measurements."""

    token_state = {
        tuple(item[0]): {
            "assignment": item[2],
            "candidate_lines": tuple(item[3]),
            "uncertainty": item[4],
        }
        for item in state[0]
    }
    line_partition = tuple(
        sorted(
            (
                line[0],
                tuple(sorted(tuple(member) for member in line[1])),
                tuple(sorted(tuple(member) for member in line[2])),
            )
            for line in state[1]
        )
    )
    return {
        "admitted_identities": tuple(sorted(token_state)),
        "tokens": token_state,
        "line_partition": line_partition,
    }


def coordinate_projection(state: Sequence[Any]) -> dict[tuple[str, str, int], tuple[Any, ...]]:
    return {tuple(item[0]): tuple(item[5:9]) for item in state[0]}


def measurement_projection(state: Sequence[Any]) -> dict[str, Any]:
    return {
        "line_measurements": tuple(
            (line[0], line[3]) for line in state[1]
        ),
        "page_measurements": state[2],
    }


def compare_canonical_states(before: Sequence[Any], after: Sequence[Any]) -> dict[str, Any]:
    """Separate coordinate/input, assignment, and geometric-measurement changes."""

    before_coordinates = coordinate_projection(before)
    after_coordinates = coordinate_projection(after)
    before_assignments = assignment_projection(before)
    after_assignments = assignment_projection(after)
    before_measurements = measurement_projection(before)
    after_measurements = measurement_projection(after)
    changed_assignment_identities = {
        identity
        for identity in set(before_assignments["tokens"]) | set(after_assignments["tokens"])
        if before_assignments["tokens"].get(identity) != after_assignments["tokens"].get(identity)
    }
    return {
        "input_coordinates_changed": before_coordinates != after_coordinates,
        "assignment_changed": before_assignments != after_assignments,
        "measurement_changed": before_measurements != after_measurements,
        "assignment_changed_identities": [list(identity) for identity in sorted(changed_assignment_identities)],
        "line_partition_changed": before_assignments["line_partition"] != after_assignments["line_partition"],
        "coordinate_changes": {
            str(identity): {"before": before_coordinates.get(identity), "after": after_coordinates.get(identity)}
            for identity in sorted(set(before_coordinates) | set(after_coordinates))
            if before_coordinates.get(identity) != after_coordinates.get(identity)
        },
    }


def _canonical_state(
    fixture_id: str,
    page: Mapping[str, Any],
    tokens: Sequence[Any],
    lines: Sequence[Mapping[str, Any]],
    unresolved: Sequence[Mapping[str, Any]],
    measurements: Mapping[str, Any],
) -> tuple[Any, ...]:
    return canonical_geometry_state(fixture_id, page["side"], tokens, lines, unresolved, measurements)


def _pipeline(
    fixture_id: str,
    page: Mapping[str, Any],
    tokens: Sequence[Any],
    model_name: str,
    grouping: Callable[..., list[list[Any]]],
    *,
    grouping_uses_gap: bool = True,
) -> dict[str, Any]:
    parameters = _shared_parameters(tokens)
    if not tokens:
        empty_measurements = production_geometry.group_physical_lines([])[2]
        empty_state = _canonical_state(fixture_id, page, tokens, [], [], empty_measurements)
        return {
            "model": model_name,
            "parameters": _shared_parameters(tokens),
            "stages": {
                "vertical_grouping": {"groups": [], "group_count": 0},
                "horizontal_splitting": {"groups": [], "group_count": 0, "predicate": "production _split_horizontal_regions"},
                "reconciliation": {"unresolved": [], "line_count": 0, "predicate": "research copy of production group_physical_lines final reconciliation"},
            },
            "canonical_state": _jsonable(empty_state),
            "canonical_state_sha256": _digest(empty_state),
            "assignment_projection": assignment_projection(empty_state),
            "unresolved": [],
            "physical_lines": [],
        }
    tolerance = parameters["tolerance_px"]
    slope = parameters["baseline_slope_px_per_px"]
    gap_limit = parameters["horizontal_gap_limit_px"]
    raw_groups = grouping(tokens, tolerance, gap_limit, slope) if grouping_uses_gap else grouping(tokens, tolerance, slope)
    split_groups = production_geometry._split_horizontal_regions(raw_groups, gap_limit)
    lines, unresolved, measurements = _reconcile(tokens, split_groups, tolerance, slope, gap_limit)
    state = _canonical_state(fixture_id, page, tokens, lines, unresolved, measurements)
    return {
        "model": model_name,
        "parameters": parameters,
        "stages": {
            "vertical_grouping": {"groups": _source_rows(raw_groups), "group_count": len(raw_groups)},
            "horizontal_splitting": {"groups": _source_rows(split_groups), "group_count": len(split_groups), "predicate": "production _split_horizontal_regions"},
            "reconciliation": {"unresolved": unresolved, "line_count": len(lines), "predicate": "research copy of production group_physical_lines final reconciliation"},
        },
        "physical_lines": lines,
        "unresolved": unresolved,
        "canonical_state": _jsonable(state),
        "canonical_state_sha256": _digest(state),
        "assignment_projection": assignment_projection(state),
    }


def _direct_production(fixture_id: str, page: Mapping[str, Any], tokens: Sequence[Any]) -> dict[str, Any]:
    lines, unresolved, measurements = production_geometry.group_physical_lines(tokens)
    state = _canonical_state(fixture_id, page, tokens, lines, unresolved, measurements)
    return {
        "physical_lines": lines,
        "unresolved": unresolved,
        "measurements": measurements,
        "canonical_state": state,
        "canonical_state_sha256": _digest(state),
        "assignment_projection": assignment_projection(state),
    }


def _one_pixel_perturbation(
    fixture_id: str,
    page: Mapping[str, Any],
    tokens: Sequence[Any],
    direct_state: Sequence[Any],
) -> dict[str, Any] | None:
    """Compare a coordinate perturbation through assignment semantics only."""

    if not tokens:
        return None
    first = tokens[0]
    changed_tokens = _perturbed_tokens(tokens)
    changed_state = _direct_production(fixture_id, page, changed_tokens)["canonical_state"]
    comparison = compare_canonical_states(direct_state, changed_state)
    return {
        "perturbed_source_row": first.source_row,
        "input_coordinates_changed": comparison["input_coordinates_changed"],
        "assignment_changed": comparison["assignment_changed"],
        "measurement_changed": comparison["measurement_changed"],
        "coordinate_changes": comparison["coordinate_changes"],
    }


def _perturbed_tokens(tokens: Sequence[Any]) -> list[Any]:
    if not tokens:
        return []
    first = tokens[0]
    return [
        production_geometry._Token(
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
            token.y + (1 if token is first else 0),
            token.width,
            token.height,
        )
        for token in tokens
    ]


def _control_pipeline(fixture_id: str, page: Mapping[str, Any], tokens: Sequence[Any]) -> dict[str, Any]:
    return _pipeline(fixture_id, page, tokens, "production-greedy-control", _production_vertical_groups, grouping_uses_gap=False)


def _alternative_pipelines(fixture_id: str, page: Mapping[str, Any], tokens: Sequence[Any]) -> dict[str, dict[str, Any]]:
    builders = {
        "pairwise-components": _pairwise_vertical_groups,
        "fixed-anchor-groups": _fixed_anchor_vertical_groups,
    }
    results = {
        "pairwise-components": _pipeline(fixture_id, page, tokens, "pairwise-components", _pairwise_vertical_groups),
        "fixed-anchor-groups": _pipeline(fixture_id, page, tokens, "fixed-anchor-groups", _fixed_anchor_vertical_groups),
    }
    for name, result in results.items():
        reversed_result = _pipeline(fixture_id, page, list(reversed(tokens)), name, builders[name])
        result["permutation_stable"] = _state_equal(result["canonical_state"], reversed_result["canonical_state"])
    return results


def _state_equal(left: Sequence[Any], right: Sequence[Any]) -> bool:
    return _jsonable(left) == _jsonable(right)


def _fidelity_page(fixture_id: str, page: Mapping[str, Any]) -> dict[str, Any]:
    tokens = [PRIOR._token_from_record(record) for record in page["tokens"]]
    direct = _direct_production(fixture_id, page, tokens)
    control = _control_pipeline(fixture_id, page, tokens)
    actual_split = production_geometry._line_bands(
        tokens,
        control["parameters"]["tolerance_px"],
        control["parameters"]["baseline_slope_px_per_px"],
    )
    return {
        "side": page["side"],
        "token_count": len(tokens),
        "complete_state_equal": _state_equal(direct["canonical_state"], control["canonical_state"]),
        "direct_state_sha256": direct["canonical_state_sha256"],
        "control_state_sha256": control["canonical_state_sha256"],
        "vertical_grouping_equivalence_basis": "the pre-split loop is copied from production _line_bands at the recorded source revision; equivalence is established through complete final state plus actual horizontal-split comparison",
        "horizontal_split_equal_to_actual": _source_rows(actual_split) == control["stages"]["horizontal_splitting"]["groups"],
        "direct_assignment_projection": direct["assignment_projection"],
        "control_assignment_projection": control["assignment_projection"],
    }


def _fixture_ids() -> tuple[str, ...]:
    return (
        "relativity_pdf10_pp26-27",
        "relativity_pdf17_pp40-41",
        "relativity_pdf23_pp52-53",
        "stella_maris_pdf03_session-I",
        "stella_maris_pdf06_dense-dialogue",
        "stella_maris_pdf18_session-II_p35",
    )


def _fidelity_gate() -> dict[str, Any]:
    pages: dict[str, list[dict[str, Any]]] = {}
    for fixture_id in _fixture_ids():
        geometry = json.loads((GEOMETRY_ROOT / fixture_id / "geometry.json").read_text(encoding="utf-8"))
        pages[fixture_id] = [_fidelity_page(fixture_id, page) for page in geometry["pages"]]
    records = [record for fixture_pages in pages.values() for record in fixture_pages]
    return {
        "fixture_count": len(pages),
        "page_count": len(records),
        "all_complete_states_equal": all(record["complete_state_equal"] for record in records),
        "all_horizontal_splits_equal": all(record["horizontal_split_equal_to_actual"] for record in records),
        "pages": pages,
    }


def _residual_cases() -> dict[str, dict[str, list[int]]]:
    return {
        "relativity_pdf10_pp26-27": {"left": [213, 216, 217, 226, 227], "right": [246]},
        "relativity_pdf17_pp40-41": {"right": [23]},
    }


def _compare_page(fixture_id: str, page: Mapping[str, Any], *, residual_rows: Sequence[int] = ()) -> dict[str, Any]:
    tokens = [PRIOR._token_from_record(record) for record in page["tokens"]]
    direct = _direct_production(fixture_id, page, tokens)
    control = _control_pipeline(fixture_id, page, tokens)
    alternatives = _alternative_pipelines(fixture_id, page, tokens)
    perturb_token = tokens[0] if tokens else None
    perturbation = None
    if perturb_token is not None:
        changed = [
            production_geometry._Token(
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
                token.y + (1 if token is perturb_token else 0),
                token.width,
                token.height,
            )
            for token in tokens
        ]
        changed_state = _direct_production(fixture_id, page, changed)["canonical_state"]
        perturbation = compare_canonical_states(direct["canonical_state"], changed_state)
    model_differences = {}
    model_perturbations = {}
    builders = {
        "pairwise-components": _pairwise_vertical_groups,
        "fixed-anchor-groups": _fixed_anchor_vertical_groups,
    }
    for name, result in alternatives.items():
        comparison = compare_canonical_states(direct["canonical_state"], result["canonical_state"])
        comparison["stage_difference"] = {
            "vertical_grouping": result["stages"]["vertical_grouping"]["groups"] != control["stages"]["vertical_grouping"]["groups"],
            "horizontal_splitting": result["stages"]["horizontal_splitting"]["groups"] != control["stages"]["horizontal_splitting"]["groups"],
            "reconciliation": result["stages"]["reconciliation"] != control["stages"]["reconciliation"],
        }
        comparison["first_divergence_stage"] = next(
            (
                stage
                for stage in ("vertical_grouping", "horizontal_splitting", "reconciliation")
                if comparison["stage_difference"][stage]
            ),
            None,
        )
        model_differences[name] = comparison
        if tokens:
            perturbed = _pipeline(fixture_id, page, _perturbed_tokens(tokens), name, builders[name])
            perturbation = compare_canonical_states(result["canonical_state"], perturbed["canonical_state"])
            model_perturbations[name] = {
                "input_coordinates_changed": perturbation["input_coordinates_changed"],
                "assignment_changed": perturbation["assignment_changed"],
                "measurement_changed": perturbation["measurement_changed"],
                "assignment_changed_identities": perturbation["assignment_changed_identities"],
            }
    return {
        "side": page["side"],
        "token_count": len(tokens),
        "production": direct,
        "research_control": control,
        "models": alternatives,
        "model_differences": model_differences,
        "residual_token_states": {
            str(row): {
                "identity": [fixture_id, page["side"], row],
                "production": next(item for item in direct["assignment_projection"]["tokens"].items() if item[0][2] == row)[1],
                **{
                    name: next(item for item in result["assignment_projection"]["tokens"].items() if item[0][2] == row)[1]
                    for name, result in alternatives.items()
                },
            }
            for row in residual_rows
        },
        "one_pixel_coordinate_perturbation": perturbation,
        "model_one_pixel_coordinate_perturbation": model_perturbations,
    }


def _residual_results() -> dict[str, Any]:
    selected = _residual_cases()
    result: dict[str, Any] = {}
    for fixture_id, sides in selected.items():
        geometry = json.loads((GEOMETRY_ROOT / fixture_id / "geometry.json").read_text(encoding="utf-8"))
        result[fixture_id] = {
            page["side"]: _compare_page(fixture_id, page, residual_rows=sides[page["side"]])
            for page in geometry["pages"]
            if page["side"] in sides
        }
    return result


def _synthetic_results() -> list[dict[str, Any]]:
    results = []
    for case in PRIOR._synthetic_cases():
        tokens = PRIOR._synthetic_tokens(case["rows"])
        page = {"side": "synthetic"}
        direct = _direct_production(case["case_id"], page, tokens)
        control = _control_pipeline(case["case_id"], page, tokens)
        alternatives = _alternative_pipelines(case["case_id"], page, tokens)
        model_stage_differences = {}
        for name, model in alternatives.items():
            stage_difference = {
                "vertical_grouping": model["stages"]["vertical_grouping"] != control["stages"]["vertical_grouping"],
                "horizontal_splitting": model["stages"]["horizontal_splitting"] != control["stages"]["horizontal_splitting"],
                "reconciliation": model["stages"]["reconciliation"] != control["stages"]["reconciliation"],
            }
            model_stage_differences[name] = {
                "stage_difference": stage_difference,
                "first_divergence_stage": next((stage for stage in ("vertical_grouping", "horizontal_splitting", "reconciliation") if stage_difference[stage]), None),
            }
        perturbation = _one_pixel_perturbation(case["case_id"], page, tokens, direct["canonical_state"])
        model_perturbations = {}
        builders = {"pairwise-components": _pairwise_vertical_groups, "fixed-anchor-groups": _fixed_anchor_vertical_groups}
        for name, model in alternatives.items():
            perturbed = _pipeline(case["case_id"], page, _perturbed_tokens(tokens), name, builders[name])
            comparison = compare_canonical_states(model["canonical_state"], perturbed["canonical_state"])
            model_perturbations[name] = {
                "input_coordinates_changed": comparison["input_coordinates_changed"],
                "assignment_changed": comparison["assignment_changed"],
                "measurement_changed": comparison["measurement_changed"],
                "assignment_changed_identities": comparison["assignment_changed_identities"],
            }
        results.append({
            "case_id": case["case_id"],
            "physical_interpretation_by_construction": case["physical_interpretation"],
            "rows": case["rows"],
            "production": direct,
            "research_control": control,
            "models": alternatives,
            "fidelity_equal": _state_equal(direct["canonical_state"], control["canonical_state"]),
            "model_differences": {
                name: {
                    **compare_canonical_states(direct["canonical_state"], model["canonical_state"]),
                    **model_stage_differences[name],
                }
                for name, model in alternatives.items()
            },
            "one_pixel_coordinate_perturbation": perturbation,
            "model_one_pixel_coordinate_perturbation": model_perturbations,
        })
    return results


def _successful_controls() -> list[dict[str, Any]]:
    controls = []
    for fixture_id in (
        "relativity_pdf23_pp52-53",
        "stella_maris_pdf03_session-I",
        "stella_maris_pdf06_dense-dialogue",
        "stella_maris_pdf18_session-II_p35",
    ):
        geometry = json.loads((GEOMETRY_ROOT / fixture_id / "geometry.json").read_text(encoding="utf-8"))
        pages = []
        for page in geometry["pages"]:
            record = _compare_page(fixture_id, page)
            pages.append({
                "side": page["side"],
                "token_count": record["token_count"],
                "fidelity_equal": record["research_control"]["canonical_state_sha256"] == record["production"]["canonical_state_sha256"],
                "models": {
                    name: {
                        "permutation_stable": record["models"][name]["permutation_stable"],
                        "assignment_changed": difference["assignment_changed"],
                        "measurement_changed": difference["measurement_changed"],
                        "stage_difference": difference["stage_difference"],
                        "first_divergence_stage": difference["first_divergence_stage"],
                    }
                    for name, difference in record["model_differences"].items()
                },
                "one_pixel_coordinate_perturbation": record["one_pixel_coordinate_perturbation"],
                "model_one_pixel_coordinate_perturbation": record["model_one_pixel_coordinate_perturbation"],
            })
        controls.append({"fixture_id": fixture_id, "recorded_status": geometry["status"], "pages": pages})
    return controls


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
        "production_geometry_import_path": str(Path(production_geometry.__file__).resolve()),
        "tesseract": subprocess.run(["tesseract", "--version"], check=True, text=True, capture_output=True).stdout.splitlines()[0],
    }


def _artifact_inventory() -> list[dict[str, Any]]:
    return [
        {"path": str(path.relative_to(REPOSITORY_ROOT)), "sha256": sha256(path), "size_bytes": path.stat().st_size}
        for path in sorted(ROOT.rglob("*"))
        if path.is_file() and path.name != "manifest.json" and "__pycache__" not in path.parts and path.suffix != ".pyc"
    ]


def run(output: Path = ROOT, *, write_manifest: bool = True) -> dict[str, Any]:
    current_revision = _git("rev-parse", "HEAD")
    if not _is_ancestor(BASELINE_COMMIT, current_revision):
        raise AssertionError(
            "stage ablation requires the published vertical-investigation commit "
            f"or a descendant; found {current_revision}"
        )
    if sha256(REPOSITORY_ROOT / "src/normalize/geometry.py") != GEOMETRY_SHA256:
        raise AssertionError("production geometry differs from the published baseline")
    if sha256(REPOSITORY_ROOT / "tests/geometry_oracle.py") != ORACLE_SHA256:
        raise AssertionError("identity-complete oracle differs from the published baseline")
    output.mkdir(parents=True, exist_ok=True)
    fidelity = _fidelity_gate()
    if not fidelity["all_complete_states_equal"] or not fidelity["all_horizontal_splits_equal"]:
        raise AssertionError("research control failed the mandatory production-fidelity gate")
    result = {
        "schema": "normalize-vertical-stage-ablation-v1",
        "baseline_commit": BASELINE_COMMIT,
        "production_geometry_sha256": GEOMETRY_SHA256,
        "identity_complete_oracle_sha256": ORACLE_SHA256,
        "stage_boundaries": {
            "vertical_grouping": "production _line_bands pre-split loop; alternatives replace only this raw-group constructor",
            "horizontal_splitting": "production _split_horizontal_regions called unchanged",
            "final_reconciliation": "research copy of production group_physical_lines final candidate and uncertainty logic; fidelity-gated against direct production",
            "serialization": "canonical identity-complete oracle state; no experimental output enters production serialization",
        },
        "fidelity_gate": fidelity,
        "synthetic_cases": _synthetic_results(),
        "real_residuals": _residual_results(),
        "successful_fixture_controls": _successful_controls(),
        "assignment_comparison_contract": {
            "assignment_projection": "stable identity, resolved assignment, candidate set, uncertainty, and canonical line partition",
            "coordinate_projection": "identity to x/y/width/height; reported separately as input change",
            "measurement_projection": "canonical line measurements and page measurements; reported separately",
            "line_id_handling": "canonical oracle geometric order; generated label renaming is irrelevant",
        },
        "scope": {
            "production_geometry_modified": False,
            "production_assignments_modified": False,
            "identity_complete_oracle_modified": False,
            "fixture_expectations_modified": False,
            "pixel_evidence_integrated": False,
            "source_pdfs_committed": False,
        },
    }
    (output / "results.json").write_text(json.dumps(_jsonable(result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if write_manifest:
        manifest = {
            "schema": "normalize-vertical-stage-ablation-manifest-v1",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "experiment_start": {"git_commit_sha": BASELINE_COMMIT, "git_branch": "verification-repair-stage-ablation", "git_status": "clean before task edits"},
            "generation_state": {"git_commit_sha": _git("rev-parse", "HEAD"), "git_branch": _git("branch", "--show-current"), "git_status_porcelain": _git("status", "--short")},
            "environment": _environment(),
            "commands": [
                ".venv/bin/python research/geometry/vertical-stage-ablation/stage_ablation.py",
                ".venv/bin/python -m pytest -q tests/test_verification_repair.py tests/test_vertical_stage_ablation.py",
                ".venv/bin/python -m pytest -q",
            ],
            "input_hashes": {
                "production_geometry": GEOMETRY_SHA256,
                "identity_complete_oracle": ORACLE_SHA256,
                "prior_investigation_script": {"path": str(PRIOR_INVESTIGATION.relative_to(REPOSITORY_ROOT)), "sha256": sha256(PRIOR_INVESTIGATION)},
                "geometry_artifacts": [
                    {"path": str(path.relative_to(REPOSITORY_ROOT)), "sha256": sha256(path)}
                    for path in sorted(GEOMETRY_ROOT.glob("*/geometry.json"))
                ],
            },
            "model_parameters": {
                "shared_tolerance_formula": "max(1, floor(median(token.height_px) / 4 + 0.5))",
                "shared_horizontal_gap_formula": "2 * median(token.width_px)",
                "pairwise_predicate": "adjusted-center tolerance plus production horizontal adjacency",
                "fixed_anchor_predicate": "adjusted-center tolerance to fixed first-token anchor",
            },
            "artifact_paths_and_hashes": _artifact_inventory(),
            "restrictions": result["scope"],
        }
        (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT)
    args = parser.parse_args()
    result = run(args.output)
    print(json.dumps({"output": str(args.output), "fidelity": result["fidelity_gate"]["all_complete_states_equal"], "synthetic_cases": len(result["synthetic_cases"])}, indent=2))


if __name__ == "__main__":
    main()
