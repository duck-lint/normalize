"""Build a label-blind local-slope support analysis from prior captures."""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np
from PIL import Image, ImageDraw
import normalize.geometry as production_geometry

from local_support import (
    Box,
    boxes_from_records,
    local_support_decision,
    measure_scope,
    region_consistency_decision_v1,
    scope_boxes,
)


ROOT = Path(__file__).resolve().parents[3]
PRIOR = ROOT / "research/geometry/baseline-slope-forensics"
WORK = ROOT / "research/geometry/local-slope-support-forensics"
RASTER_ROOT = Path("/tmp/baseline-slope-forensics")

CAUSAL_REVIEW = {
    "relativity_pdf10_pp26-27.left.event-003": "Eight token boxes span 516 px. The local pixel lower-edge fit is -0.01736 with 0.05 px median residual and 1.01 px leave-one-token trend spread; it agrees with the page row evidence. Applying this physically supported tilt still isolates source row 77 from the visibly continuous row. The failure is downstream token-box-center/tolerance behavior, not absent slope support.",
    "relativity_pdf17_pp40-41.left.event-031": "Four title token boxes span 398 px. Pixel lower-edge slope is +0.01475 with 0.22 px median residual; the sampled body rows and separately measured heading have the same positive orientation. The cohesion candidate +0.027 is too steep, while the pixel candidate near +0.015 still divides the one printed title into three groups. Local slope support therefore does not prevent this false split.",
    "relativity_pdf17_pp40-41.left.event-032": "This is the second candidate realization of the same four-token title context as event-031, not a second physical row. Its pixel support is identical. The applied +0.01475 local estimate yields groups [9], [10, 12], [11] even though the scan shows one title row; token-center variation inside the unchanged tolerance path causes the harm.",
    "relativity_pdf23_pp52-53.right.event-035": "Four tokens span 318 px. Pixel lower-edge slope is -0.00771, with 0.12 px median residual and 0.83 px leave-one-token trend spread. Applying it groups the event as [114, 115], [116], [117]. It also joins neighboring source rows 110-113 into the same line with 114-115; direct pixels show 110-117 form one continuous physical row, so this is a partial repair plus a remaining false split, not a destructive merge of distinct rows.",
    "stella_maris_pdf03_session-I.right.event-037": "Six boxes span 299 px. The cohesion candidate is -0.011, while token-local pixel lower-edge support is +0.00552: opposite direction. Its supported trend is only 1.65 px across this event span, below the rule's 2 px resolution floor, so slope is rejected and the production one-row grouping is preserved.",
    "stella_maris_pdf03_session-I.right.event-038": "One token spans 5 px. A single located token has no independent horizontal baseline support. The gate abstains; expanding to nearby text could borrow a neighboring row's pixels and is not accepted as same-row evidence.",
    "stella_maris_pdf06_dense-dialogue.right.event-041": "Four boxes span 230 px. The candidate slope +0.001 contributes only about 0.23 px over the event; pixel lower-edge fit is -0.00631 but under the 2 px local trend floor. Box-center and pixel slopes differ substantially because box heights vary. Rejecting slope preserves the production one-row grouping.",
    "stella_maris_pdf06_dense-dialogue.right.event-042": "Seven boxes span 312 px. Local pixel lower-edge slope -0.00428 gives 1.34 px trend, below the 2 px floor; the page candidate -0.00846 gives a larger change, while box-center slope is +0.01056. The disagreement and subpixel-scale effect do not justify the page candidate, and zero preserves the visible row.",
    "relativity_pdf10_pp26-27.right.event-024": "Additional local-model false split from a prior repaired row. Nine boxes span 478 px; local slope -0.03469 has 0.08 px median residual and 0.42 px leave-one-token trend spread. The scan shows one row, but event-local shear partitions it into [32-36], [37, 39], [38, 40]. Strong local linear evidence does not guarantee token-center grouping safety.",
    "relativity_pdf17_pp40-41.left.event-027": "Additional local-model false split from a prior repaired row. Eight boxes span 513 px; local slope +0.01862 has 0.13 px median residual and 0.44 px leave-one-token trend spread, consistent with nearby sampled text-row orientation. The scan shows one continuous row; the local output separates source rows 167 and 168 after the unchanged tolerance comparison.",
    "stella_maris_pdf03_session-I.right.event-036": "Additional local-model false split from a prior repaired row. Ten boxes span 508 px; local slope -0.00561 has 0.58 px median residual and 0.74 px leave-one-token trend spread, but differs from the nearest sampled page row by about 2.46 px over this span (that sampled row is 129 px away, not an immediate neighbor). Applying the local slope leaves source rows 112 and 118 separate from the rest of one visually continuous row. Local support can be internally stable yet not predict downstream grouping safety.",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def load_inputs() -> tuple[dict[str, Any], list[dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
    prior_results = json.loads((PRIOR / "results.json").read_text(encoding="utf-8"))
    prior_adjudications = json.loads((PRIOR / "adjudications.json").read_text(encoding="utf-8"))
    admission = json.loads((PRIOR / "admitted_tokens.json").read_text(encoding="utf-8"))
    events = prior_adjudications["events"]
    if len(events) != 46:
        raise AssertionError(f"expected the preserved 46-event corpus, found {len(events)}")
    classes = Counter(event["classification"] for event in events)
    if classes != Counter({"repaired_false_split": 37, "new_false_split": 8, "unresolved": 1}):
        raise AssertionError(f"prior adjudications do not match authority counts: {classes}")
    result_events = prior_results["changed_event_summary"]["events"]
    if [canonical(event) for event in events] != [canonical(event) for event in result_events]:
        raise AssertionError("the adjudication ledger and results event corpus disagree")

    sides = {(side["fixture_id"], side["side"]): side for side in admission["sides"]}
    result_sides = {(side["fixture_id"], side["side"]): side for side in prior_results["capture_contract"]["side_capture_hashes"]}
    if sides.keys() != result_sides.keys():
        raise AssertionError("admitted records and capture hashes cover different page sides")
    for key, side in sides.items():
        hashes = result_sides[key]
        for name in ("image_sha256", "source_pdf_sha256", "tsv_sha256", "admitted_token_sha256"):
            if side.get(name) != hashes.get(name):
                raise AssertionError(f"prior source provenance mismatch for {key}: {name}")
        image_path = RASTER_ROOT / key[0] / f"{key[0]}.{key[1]}.png"
        if not image_path.is_file() or sha256(image_path) != side["image_sha256"]:
            raise AssertionError(f"local raster unavailable or changed for {key}; expected {side['image_sha256']}")

    # Event boxes must map exactly to the once-captured admitted token geometry.
    token_lookup = {
        key: {int(token["source_row"]): token for token in side["tokens"]}
        for key, side in sides.items()
    }
    for event in events:
        key = (event["fixture_id"], event["side"])
        expected_rows = set(event["source_rows"])
        recorded_rows = {int(item["source_row"]) for item in event["token_boxes"]}
        if expected_rows != recorded_rows:
            raise AssertionError(f"event token identity coverage mismatch: {event['event_id']}")
        for item in event["token_boxes"]:
            token = token_lookup[key].get(int(item["source_row"]))
            if token is None:
                raise AssertionError(f"event token missing from admitted capture: {event['event_id']} {item['source_row']}")
            recorded_box = item["box_px"]
            admitted_box = [token[name] for name in ("x", "y", "width", "height")]
            if recorded_box != admitted_box:
                raise AssertionError(f"event token box changed: {event['event_id']} {item['source_row']}")
    return prior_results, events, sides


def event_feature_record(
    event: dict[str, Any],
    page_side: dict[str, Any],
    all_boxes: list[Box],
    gray: np.ndarray,
) -> dict[str, Any]:
    event_boxes = boxes_from_records(event["token_boxes"])
    page_width = int(page_side["dimensions_px"][0])
    tolerance = int(page_side["tolerance_px"])
    candidate_slope = float(event["candidate_slope"])

    scope_results = {}
    scoped_boxes = {}
    scope_identities = {}
    for scope in ("event_only", "candidate_band", "local_x_neighborhood", "neighbor_rows"):
        selected = scope_boxes(all_boxes=all_boxes, event_boxes=event_boxes, scope=scope)
        scoped_boxes[scope] = selected
        scope_identities[scope] = sorted(box.source_row for box in selected)
        scope_results[scope] = measure_scope(
            gray,
            selected,
            page_width=page_width,
            candidate_slope=candidate_slope,
        )
    local_measurement = scope_results["event_only"]
    decision = local_support_decision(local_measurement)
    v1_decision = region_consistency_decision_v1(local_measurement)
    support_fit = local_measurement.get("per_token_pixel_lower_envelope_fit", {})
    span = local_measurement.get("x_span_px", 0)
    loo_range = local_measurement.get("leave_one_token_landmark_out_slope_range_px_per_px")
    slope_value = support_fit.get("slope_px_per_px")
    margins = []
    if support_fit.get("support_bins") is not None:
        margins.extend([
            {"boundary": "minimum_three_pixel_landmarks", "value": support_fit["support_bins"], "threshold": 3, "signed_margin": support_fit["support_bins"] - 3},
            {"boundary": "maximum_median_residual_px", "value": support_fit.get("median_absolute_residual_px"), "threshold": 2.0, "signed_margin": 2.0 - support_fit.get("median_absolute_residual_px", 0.0)},
        ])
    if loo_range is not None:
        loo_spread = (loo_range[1] - loo_range[0]) * span
        margins.append({"boundary": "maximum_leave_one_token_trend_spread_px", "value": loo_spread, "threshold": 4.0, "signed_margin": 4.0 - loo_spread})
    if slope_value is not None:
        trend_px = abs(slope_value * span)
        margins.append({"boundary": "minimum_nonzero_trend_px", "value": trend_px, "threshold": 2.0, "signed_margin": trend_px - 2.0})
    for margin in margins:
        margin["normalized_absolute_margin"] = abs(margin["signed_margin"]) / max(abs(margin["threshold"]), 1.0)
    nearest_boundary = min(margins, key=lambda item: item["normalized_absolute_margin"]) if margins else None

    x0 = min(box.x for box in event_boxes)
    x1 = max(box.x1 for box in event_boxes)
    y0 = min(box.y for box in event_boxes)
    y1 = max(box.y1 for box in event_boxes)
    nearby = []
    for box in all_boxes:
        if box.source_row in {item.source_row for item in event_boxes}:
            continue
        horizontal_overlap = max(0, min(x1, box.x1) - max(x0, box.x))
        vertical_gap = max(y0 - box.y1, box.y - y1, 0)
        if horizontal_overlap > 0 and vertical_gap <= max(2 * tolerance, 1):
            nearby.append({
                "source_row": box.source_row,
                "horizontal_overlap_px": horizontal_overlap,
                "vertical_gap_px": vertical_gap,
            })

    evidence = event.get("visual_physical_row_adjudication", {}).get("row_pixel_evidence", {})
    selected_ids = set(event["source_rows"])
    same_physical_row_evidence = [
        row for row in evidence.get("adjudicated_rows", [])
        if selected_ids.intersection(row.get("source_rows_as_locator", []))
    ]
    locator_tokens = {int(token["source_row"]): token for token in page_side["tokens"]}
    event_center_y = float(median([box.center_y for box in event_boxes]))
    neighboring_pixel_rows = []
    for row in evidence.get("adjudicated_rows", []):
        locator_rows = row.get("source_rows_as_locator", [])
        known = [locator_tokens[int(source)] for source in locator_rows if int(source) in locator_tokens]
        if not known:
            continue
        row_center = float(median([token["y"] + token["height"] / 2 for token in known]))
        neighboring_pixel_rows.append({
            "row_evidence_id": row.get("row_evidence_id"),
            "vertical_distance_from_event_center_px": abs(row_center - event_center_y),
            "estimated_slope_px_per_px": row.get("estimated_slope_px_per_px"),
            "shares_event_locator_ids": bool(selected_ids.intersection(locator_rows)),
        })
    independent_neighbors = [row for row in neighboring_pixel_rows if not row["shares_event_locator_ids"]]
    nearest_neighbor = min(independent_neighbors, key=lambda row: row["vertical_distance_from_event_center_px"]) if independent_neighbors else None
    local_slope = local_measurement.get("per_token_pixel_lower_envelope_fit", {}).get("slope_px_per_px")
    if nearest_neighbor and local_slope is not None:
        neighbor_delta = (local_slope - nearest_neighbor["estimated_slope_px_per_px"]) * local_measurement["x_span_px"]
    else:
        neighbor_delta = None
    return {
        "fixture_id": event["fixture_id"],
        "side": event["side"],
        "event_id": event["event_id"],
        "prior_classification": event["classification"],
        "prior_candidate_models": event["candidate_models"],
        "production_slope": event["production_slope"],
        "candidate_slope": candidate_slope,
        "source_rows": event["source_rows"],
        "token_boxes": event["token_boxes"],
        "production_grouping": event["production_grouping"],
        "prior_pixel_candidate_grouping": event["candidate_grouping"],
        "prior_page_image_sha256": page_side["image_sha256"],
        "prior_source_pdf_sha256": page_side["source_pdf_sha256"],
        "prior_admitted_token_sha256": page_side["admitted_token_sha256"],
        "tolerance_px": tolerance,
        "horizontal_gap_limit_px": page_side["horizontal_gap_limit_px"],
        "scopes": scope_results,
        "scope_token_source_rows": scope_identities,
        "pixel_authority_check": {
            "decision_scope": "event_only",
            "pixel_roi_source_rows": sorted(box.source_row for box in event_boxes),
            "pixel_landmark_source_rows": sorted(point["source_row"] for point in local_measurement.get("per_token_pixel_lower_envelope_points", [])),
            "neighboring_rows_used_as_target_support": False,
            "support_roi_restricted_to_event_boxes": True,
            "overlapping_ink_segmented_from_glyphs": False,
            "prior_visual_row_adjudication": event["visual_physical_row_adjudication"]["reason"],
            "adjudication_basis": "direct production-raster crop review; token boxes used as locating rectangles only; pixel method does not segment overlapping strokes from glyph ink",
        },
        "v1_region_consistency_decision": v1_decision,
        "local_support_decision": decision,
        "threshold_margins": margins,
        "nearest_threshold_boundary": nearest_boundary,
        "neighboring_box_context": {
            "other_boxes_overlapping_event_x_within_two_tolerances": nearby,
            "nearest_prior_adjudicated_row_fits_sharing_event_source_ids": same_physical_row_evidence,
            "same_row_pixel_attribution": bool(same_physical_row_evidence),
            "other_sampled_page_row_slopes": neighboring_pixel_rows,
            "nearest_independent_sampled_row": nearest_neighbor,
            "local_minus_nearest_sampled_row_trend_px": neighbor_delta,
        },
    }


def _tokens_from_records(records: list[dict[str, Any]]) -> list[Any]:
    """Construct geometry-only production tokens; captured text is discarded."""

    from normalize.geometry import _Token
    tokens = []
    for record in records:
        x, y, width, height = (record[name] for name in ("x", "y", "width", "height"))
        tokens.append(_Token(
            source_row=int(record["source_row"]), text="", confidence=0.0,
            level=5, page_num=1, block_num=1, par_num=1, line_num=1, word_num=1,
            x=int(x), y=int(y), width=int(width), height=int(height),
        ))
    return tokens


def _group_signature(lines: list[dict[str, Any]], unresolved: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ambiguous = defaultdict(list)
    for item in unresolved:
        for line_id in item["candidate_line_ids"]:
            ambiguous[line_id].append(int(item["token_source_row"]))
    return sorted([
        {
            "members": sorted(set(int(identity[6:]) for identity in line["token_ids"]) | set(ambiguous.get(line["line_id"], []))),
            "assigned": sorted(int(identity[6:]) for identity in line["token_ids"]),
            "ambiguous": sorted(ambiguous.get(line["line_id"], [])),
        }
        for line in lines
    ], key=lambda group: (group["members"], group["assigned"], group["ambiguous"]))


def _membership_map(signature: list[dict[str, Any]], all_source_rows: set[int]) -> dict[int, tuple[int, ...]]:
    result = {row: () for row in all_source_rows}
    for group in signature:
        for row in group["members"]:
            result[int(row)] = tuple(group["members"])
    return result


def _assignment_states(
    lines: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
    source_rows: set[int],
) -> dict[int, str]:
    states = {row: "assigned" for row in source_rows}
    for item in unresolved:
        row = int(item["token_source_row"])
        if row in states:
            states[row] = str(item["code"])
    return states


def group_page_with_local_slope(
    page_records: list[dict[str, Any]],
    local_source_rows: set[int],
    local_slope: float | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Run unchanged page grouping with an event-local coordinate transform.

    Only the event's token centers receive the supported local shear. Other
    tokens remain in the zero-slope frame. The actual production grouping,
    horizontal-gap predicate, assignment, and reconciliation code run intact.
    Monkey patches are scoped and restored before returning.
    """

    tokens = _tokens_from_records(page_records)
    old_estimator = production_geometry._estimate_baseline_slope
    old_adjuster = production_geometry._adjusted_center_y
    production_geometry._estimate_baseline_slope = lambda _tokens, _tolerance: 0.0

    def adjusted(token: Any, _slope: float) -> float:
        if local_slope is not None and token.source_row in local_source_rows:
            return token.center_y - local_slope * token.x
        return old_adjuster(token, 0.0)

    production_geometry._adjusted_center_y = adjusted
    try:
        return production_geometry.group_physical_lines(tokens)
    finally:
        production_geometry._estimate_baseline_slope = old_estimator
        production_geometry._adjusted_center_y = old_adjuster


def evaluate_event(
    event: dict[str, Any],
    feature: dict[str, Any],
    page_records: list[dict[str, Any]],
    production_signature: list[dict[str, Any]],
) -> dict[str, Any]:
    decision = feature["local_support_decision"]
    if event["classification"] == "unresolved":
        # The prior visual adjudication is not overridden by an automatic gate.
        action, slope = "abstain", None
        lines, unresolved, measurements = group_page_with_local_slope(page_records, set(), None)
        outcome = "unresolved_preserved"
    elif decision["decision"] == "apply_slope":
        action, slope = "apply_slope", float(decision["slope_px_per_px"])
        lines, unresolved, measurements = group_page_with_local_slope(page_records, set(event["source_rows"]), slope)
        full_signature = _group_signature(lines, unresolved)
        event_rows = set(event["source_rows"])
        local_partition = [sorted(set(group["members"]) & event_rows) for group in full_signature if set(group["members"]) & event_rows]
        local_partition.sort()
        prior_partition = sorted(sorted(set(group["members"]) & event_rows) for group in event["candidate_grouping"] if set(group["members"]) & event_rows)
        production_partition = sorted(sorted(set(group["members"]) & event_rows) for group in event["production_grouping"] if set(group["members"]) & event_rows)
        if local_partition == prior_partition:
            outcome = "repair_retained" if event["classification"] == "repaired_false_split" else "harmful_split_reproduced"
        elif local_partition == production_partition:
            outcome = "repair_not_retained" if event["classification"] == "repaired_false_split" else "harmful_change_blocked"
        else:
            outcome = "different_local_partition_requires_adjudication"
    elif decision["decision"] == "reject_slope":
        action, slope = "reject_slope", 0.0
        lines, unresolved, measurements = group_page_with_local_slope(page_records, set(), None)
        outcome = "repair_lost_to_production_state" if event["classification"] == "repaired_false_split" else "harm_blocked_to_production_state"
    else:
        action, slope = "abstain", None
        lines, unresolved, measurements = group_page_with_local_slope(page_records, set(), None)
        outcome = "repair_unresolved_at_production_state" if event["classification"] == "repaired_false_split" else "harm_not_applied_uncertainty_preserved"
    full_signature = _group_signature(lines, unresolved)
    event_rows = set(event["source_rows"])
    event_partition = [sorted(set(group["members"]) & event_rows) for group in full_signature if set(group["members"]) & event_rows]
    event_partition.sort()
    result_map = _membership_map(full_signature, {int(record["source_row"]) for record in page_records})
    baseline_map = _membership_map(production_signature, {int(record["source_row"]) for record in page_records})
    changed_side_rows = []
    outside_event_changes = []
    if action == "apply_slope":
        changed_side_rows = sorted(
            row for row in result_map
            if row not in event_rows and result_map[row] != baseline_map[row]
        )
        for row in changed_side_rows:
            before = next((group for group in production_signature if row in group["members"]), None)
            after = next((group for group in full_signature if row in group["members"]), None)
            token_record = next(record for record in page_records if int(record["source_row"]) == row)
            outside_event_changes.append({
                "source_row": row,
                "box_px": [token_record[name] for name in ("x", "y", "width", "height")],
                "production_group": before,
                "local_group": after,
            })
    event_group_records = [
        group for group in full_signature if set(group["members"]) & event_rows
    ]
    raw_event_lines = []
    for line in lines:
        line_rows = {int(identity[6:]) for identity in line["token_ids"]}
        if line_rows & event_rows:
            raw_event_lines.append({
                "line_id": line["line_id"],
                "event_source_rows_assigned": sorted(line_rows & event_rows),
                "unresolved_event_source_rows": sorted(set(line["unresolved_token_source_rows"]) & event_rows),
                "bounds_px": {name: line[name] for name in ("left_px", "right_px", "top_px", "bottom_px")},
                "median_center_y_px": line["median_center_y_px"],
            })
    unassigned_event_rows = sorted(
        row for row in event_rows
        if not any(row in group["members"] for group in full_signature)
    )
    event_assignment_states = _assignment_states(lines, unresolved, event_rows)
    applied_local_slope = slope if action == "apply_slope" else 0.0
    token_center_diagnostics = []
    for item in event["token_boxes"]:
        x, y, width, height = item["box_px"]
        center_y = y + height / 2
        token_center_diagnostics.append({
            "source_row": item["source_row"],
            "box_px": item["box_px"],
            "box_center_y_px": center_y,
            "production_zero_adjusted_center_y_px": center_y,
            "prior_candidate_adjusted_center_y_px": center_y - event["candidate_slope"] * x,
            "local_run_adjusted_center_y_px": center_y - applied_local_slope * x,
        })
    local_result = _local_adjudication(event, outcome, event_partition, production_partition if action == "apply_slope" else None)
    return {
        "event_id": event["event_id"],
        "prior_classification": event["classification"],
        "decision": action,
        "selected_slope_px_per_px": slope,
        "event_identity_partition": event_partition,
        "resulting_event_groups": event_group_records,
        "resulting_event_line_geometry": raw_event_lines,
        "token_center_diagnostics": token_center_diagnostics,
        "unassigned_event_source_rows": unassigned_event_rows,
        "event_assignment_states": event_assignment_states,
        "outside_event_source_rows_in_local_run": changed_side_rows,
        "outside_event_group_changes": outside_event_changes,
        "resulting_page_tolerance_px": measurements.get("tolerance_px"),
        "resulting_page_horizontal_gap_limit_px": measurements.get("horizontal_gap_limit_px"),
        "outcome": outcome,
        "local_result_adjudication": local_result,
        "scope_limit": "only event identities receive local shear; exact production banding, horizontal gap, assignment, and reconciliation run on the captured full page",
    }


def _local_adjudication(
    event: dict[str, Any],
    outcome: str,
    local_partition: list[list[int]],
    production_partition: list[list[int]] | None,
) -> dict[str, Any]:
    """Adjudicate local outputs against the already recorded pixel row ruling."""

    prior = event["classification"]
    if prior == "unresolved":
        return {"classification": "unresolved", "basis": "prior display-math physical-row interpretation remains unresolved; local gate abstains"}
    if outcome == "repair_retained":
        return {"classification": "repaired_false_split", "basis": "the local grouping matches the prior pixel-adjudicated one-row partition"}
    if outcome in {"harmful_split_reproduced", "different_local_partition_requires_adjudication"}:
        return {
            "classification": "new_false_split",
            "basis": "scan pixels show one continuous printed row while this local full-page grouping leaves its event identities in multiple groups",
        }
    if outcome in {"harm_blocked_to_production_state", "harm_not_applied_uncertainty_preserved"}:
        return {"classification": "harmful_candidate_blocked", "basis": "the broad candidate grouping was not applied; production zero-slope event partition is preserved"}
    if outcome in {"repair_not_retained", "repair_lost_to_production_state"}:
        return {"classification": "prior_false_split_preserved", "basis": "the local result returns to the production partition and does not claim the prior repair"}
    if outcome == "repair_unresolved_at_production_state":
        return {"classification": "repair_not_attempted", "basis": "support gate abstains; production grouping remains without a slope claim"}
    raise AssertionError(f"unclassified local outcome: {outcome}")


def context_inventory(events: list[dict[str, Any]]) -> dict[str, Any]:
    contexts: dict[tuple[str, str, tuple[int, ...]], list[str]] = defaultdict(list)
    token_contexts: dict[tuple[str, str, int], set[tuple[str, str, tuple[int, ...]]]] = defaultdict(set)
    for event in events:
        key = (event["fixture_id"], event["side"], tuple(event["source_rows"]))
        contexts[key].append(event["event_id"])
        for source_row in event["source_rows"]:
            token_contexts[(event["fixture_id"], event["side"], int(source_row))].add(key)
    collisions = [
        {"fixture_id": key[0], "side": key[1], "source_rows": list(key[2]), "event_ids": event_ids}
        for key, event_ids in contexts.items() if len(event_ids) > 1
    ]
    identities_with_multiple_contexts = [
        {"fixture_id": key[0], "side": key[1], "source_row": key[2], "contexts": len(contexts_set)}
        for key, contexts_set in token_contexts.items() if len(contexts_set) > 1
    ]
    return {
        "input_event_record_count": len(events),
        "unique_physical_token_context_count": len(contexts),
        "variant_contexts": collisions,
        "source_identities_in_multiple_physical_contexts": identities_with_multiple_contexts,
        "all_source_identities_map_to_one_physical_context": not identities_with_multiple_contexts,
    }


def _synthetic_row(
    *,
    label: str,
    rows: list[dict[str, Any]],
    width: int = 700,
    height: int = 360,
) -> tuple[dict[str, Any], np.ndarray]:
    """Draw line-like ink without words, OCR, or book pixels."""

    image = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(image)
    boxes: list[dict[str, Any]] = []
    source_row = 1
    for row in rows:
        xs = row["xs"]
        slope = row.get("slope", 0.0)
        base_y = row.get("base_y", 110)
        curve = row.get("curve", 0.0)
        heights = row.get("heights", [17] * len(xs))
        widths = row.get("widths", [42] * len(xs))
        for index, (x, token_height, token_width) in enumerate(zip(xs, heights, widths)):
            center = width / 2
            y_base = base_y + slope * x + curve * ((x - center) / width) ** 2
            y1 = int(round(y_base))
            y0 = y1 - int(token_height)
            box = {"source_row": source_row, "box_px": [int(x), y0, int(token_width), int(token_height)]}
            boxes.append(box)
            # Repeated vertical strokes provide glyph-like mass while fixing a
            # common lower edge; no character forms or language are encoded.
            for offset in range(2, token_width - 2, 6):
                stroke_height = max(4, int(token_height * (0.55 + ((offset // 6) % 3) * 0.12)))
                draw.line((x + offset, y1 - stroke_height, x + offset, y1), fill=0, width=2)
            source_row += 1
    record = {"label": label, "page_width_px": width, "token_boxes": boxes}
    return record, np.asarray(image)


def synthetic_matrix() -> list[dict[str, Any]]:
    """Run the frozen pixel-support rule against source-independent controls."""

    xs_long = [25, 100, 175, 250, 325, 400, 475, 550, 625]
    definitions = [
        ("A_long_clean_sloped", [{"xs": xs_long, "slope": 0.035}], "apply_slope"),
        ("B_short_clean_sloped", [{"xs": [240, 285, 330], "slope": 0.05}], "apply_slope"),
        ("C_sparse_broad_sloped", [{"xs": [25, 325, 625], "slope": -0.03}], "measure_support_explicitly"),
        ("D_curved_nonlinear", [{"xs": xs_long, "slope": 0.02, "curve": 24.0}], "abstain"),
        ("E_two_nearby_rows_same_slope", [
            {"xs": [25, 175, 325, 475, 625], "slope": 0.025, "base_y": 105},
            {"xs": [25, 175, 325, 475, 625], "slope": 0.025, "base_y": 132},
        ], "abstain"),
        ("F_two_nearby_rows_different_slopes", [
            {"xs": [25, 175, 325, 475, 625], "slope": 0.04, "base_y": 105},
            {"xs": [25, 175, 325, 475, 625], "slope": -0.025, "base_y": 132},
        ], "abstain"),
        ("G_one_token", [{"xs": [300], "slope": 0.04}], "abstain"),
        ("G_two_tokens", [{"xs": [100, 550], "slope": 0.04}], "abstain"),
        ("H_variable_height_glyph_boxes", [{"xs": xs_long, "slope": 0.035, "heights": [12, 27, 13, 28, 12, 27, 13, 28, 12]}], "apply_slope"),
        ("I_single_box_outlier", [{"xs": xs_long, "slope": -0.03}], "robust_or_abstain"),
        ("J_display_like_multiple_baselines", [
            {"xs": [80, 200, 320, 440], "slope": 0.0, "base_y": 115, "heights": [10, 12, 11, 10]},
            {"xs": [180, 300, 420, 540], "slope": 0.0, "base_y": 134, "heights": [23, 22, 24, 23]},
        ], "abstain"),
        ("K_horizontal_supported_row", [{"xs": xs_long, "slope": 0.0}], "reject_slope"),
    ]
    output = []
    for label, rows, expected in definitions:
        record, gray = _synthetic_row(label=label, rows=rows)
        if label == "I_single_box_outlier":
            outlier = record["token_boxes"][4]["box_px"]
            outlier[1] += 5
        boxes = boxes_from_records(record["token_boxes"])
        measurement = measure_scope(gray, boxes, page_width=record["page_width_px"])
        decision = local_support_decision(measurement)
        output.append({
            "case": label,
            "oracle": expected,
            "measured": measurement,
            "decision": decision,
            "v1_decision": region_consistency_decision_v1(measurement),
            "oracle_pass": (
                decision["decision"] == expected if expected in {"apply_slope", "abstain", "reject_slope"}
                else decision["decision"] in {"apply_slope", "abstain"}
            ),
            "known_row_slopes_px_per_px": [row.get("slope", 0.0) for row in rows],
        })
    return output


def scale_matrix() -> list[dict[str, Any]]:
    """Exploratory nearest-neighbor scaling for one known clean geometry."""

    record, gray = _synthetic_row(label="scale_oracle", rows=[{"xs": [25, 100, 175, 250, 325, 400, 475, 550, 625], "slope": 0.035}])
    output = []
    for factor in (0.5, 1.0, 2.0, 3.0):
        width = max(1, round(gray.shape[1] * factor))
        height = max(1, round(gray.shape[0] * factor))
        scaled = np.asarray(Image.fromarray(gray).resize((width, height), Image.Resampling.NEAREST))
        boxes = []
        for box in record["token_boxes"]:
            x, y, box_width, box_height = box["box_px"]
            boxes.append({"source_row": box["source_row"], "box_px": [round(x * factor), round(y * factor), max(1, round(box_width * factor)), max(1, round(box_height * factor))]})
        measurement = measure_scope(scaled, boxes_from_records(boxes), page_width=width)
        decision = local_support_decision(measurement)
        estimate = decision["slope_px_per_px"]
        output.append({
            "scale_factor": factor,
            "expected_slope_px_per_px": 0.035,
            "selected_slope_px_per_px": estimate,
            "decision": decision["decision"],
            "slope_error_px_per_px": abs(estimate - 0.035) if estimate is not None else None,
            "support_bins": measurement.get("per_token_pixel_lower_envelope_fit", {}).get("support_bins"),
            "note": "pixel thresholds, 20 px bins, and 2/4 px decision budgets remain fixed; this is exploratory, not a DPI guarantee",
        })
    return output


def stability_checks(
    event_records: list[dict[str, Any]],
    admission_sides: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    permutation = []
    perturbation = []
    deletion = []
    for item in event_records:
        event = item["event"]
        key = (event["fixture_id"], event["side"])
        side = admission_sides[key]
        all_boxes = boxes_from_records(side["tokens"])
        event_boxes = boxes_from_records(event["token_boxes"])
        gray = np.asarray(Image.open(RASTER_ROOT / key[0] / f"{key[0]}.{key[1]}.png").convert("L"))
        baseline = item["features"]["scopes"]["event_only"]
        baseline_decision = item["features"]["local_support_decision"]

        randomizer = random.Random(20260928)
        shuffled = list(event_boxes)
        randomizer.shuffle(shuffled)
        permuted = measure_scope(gray, shuffled, page_width=baseline["page_width_px"], candidate_slope=event["candidate_slope"])
        permuted_decision = local_support_decision(permuted)
        executed = None if permuted_decision["decision"] != "apply_slope" or event["classification"] == "unresolved" else float(permuted_decision["slope_px_per_px"])
        perm_lines, perm_unresolved, _ = group_page_with_local_slope(side["tokens"], set(event["source_rows"]), executed)
        perm_sig = _group_signature(perm_lines, perm_unresolved)
        perm_partition = [sorted(set(group["members"]) & set(event["source_rows"])) for group in perm_sig if set(group["members"]) & set(event["source_rows"])]
        perm_partition.sort()
        perm_assignment = _assignment_states(perm_lines, perm_unresolved, set(event["source_rows"]))
        permutation.append({
            "event_id": event["event_id"],
            "measurement_changed": permuted["per_token_pixel_lower_envelope_fit"] != baseline["per_token_pixel_lower_envelope_fit"],
            "slope_changed": permuted["per_token_pixel_lower_envelope_fit"].get("slope_px_per_px") != baseline["per_token_pixel_lower_envelope_fit"].get("slope_px_per_px"),
            "decision_changed": permuted_decision["decision"] != baseline_decision["decision"],
            "grouping_changed": perm_partition != item["local_evaluation"]["event_identity_partition"],
            "assignment_changed": perm_assignment != item["local_evaluation"]["event_assignment_states"],
        })

        shifted = [Box(box.source_row, box.x, box.y + 1, box.width, box.height) for box in event_boxes]
        shifted_measurement = measure_scope(gray, shifted, page_width=baseline["page_width_px"], candidate_slope=event["candidate_slope"])
        shifted_decision = local_support_decision(shifted_measurement)
        shifted_page = [
            {**record, "y": record["y"] + (1 if int(record["source_row"]) in set(event["source_rows"]) else 0)}
            for record in side["tokens"]
        ]
        shifted_slope = None if shifted_decision["decision"] != "apply_slope" or event["classification"] == "unresolved" else float(shifted_decision["slope_px_per_px"])
        shifted_lines, shifted_unresolved, _ = group_page_with_local_slope(shifted_page, set(event["source_rows"]), shifted_slope)
        shifted_sig = _group_signature(shifted_lines, shifted_unresolved)
        shifted_partition = [sorted(set(group["members"]) & set(event["source_rows"])) for group in shifted_sig if set(group["members"]) & set(event["source_rows"])]
        shifted_partition.sort()
        shifted_assignment = _assignment_states(shifted_lines, shifted_unresolved, set(event["source_rows"]))
        perturbation.append({
            "event_id": event["event_id"],
            "input_changed": True,
            "baseline_support_decision": baseline_decision,
            "perturbed_support_decision": shifted_decision,
            "baseline_measurement_boundary_values": _decision_boundary_values(baseline),
            "perturbed_measurement_boundary_values": _decision_boundary_values(shifted_measurement),
            "slope_changed": shifted_measurement["per_token_pixel_lower_envelope_fit"].get("slope_px_per_px") != baseline["per_token_pixel_lower_envelope_fit"].get("slope_px_per_px"),
            "support_decision_changed": shifted_decision["decision"] != baseline_decision["decision"],
            "grouping_changed": shifted_partition != item["local_evaluation"]["event_identity_partition"],
            "assignment_changed": shifted_assignment != item["local_evaluation"]["event_assignment_states"],
        })

        deleted = []
        for removed in event_boxes:
            remaining = [box for box in event_boxes if box.source_row != removed.source_row]
            measured = measure_scope(gray, remaining, page_width=baseline["page_width_px"], candidate_slope=event["candidate_slope"])
            decided = local_support_decision(measured)
            deleted.append({
                "removed_source_row": removed.source_row,
                "slope_px_per_px": measured.get("pixel_lower_envelope_fit", {}).get("slope_px_per_px"),
                "decision": decided["decision"],
                "decision_reason": decided["reason"],
            })
        slopes = [item["slope_px_per_px"] for item in deleted if item["slope_px_per_px"] is not None]
        deletion.append({
            "event_id": event["event_id"],
            "leave_one_token_out": deleted,
            "slope_range_px_per_px": [min(slopes), max(slopes)] if slopes else None,
            "decision_changed_count": sum(item["decision"] != baseline_decision["decision"] for item in deleted),
            "token_deletions": len(deleted),
        })
    return {
        "seed": 20260928,
        "token_permutation": {
            "events": permutation,
            "summary": {
                "events_tested": len(permutation),
                "measurement_changes": sum(item["measurement_changed"] for item in permutation),
                "slope_changes": sum(item["slope_changed"] for item in permutation),
                "decision_changes": sum(item["decision_changed"] for item in permutation),
                "grouping_changes": sum(item["grouping_changed"] for item in permutation),
                "assignment_changes": sum(item["assignment_changed"] for item in permutation),
            },
        },
        "one_pixel_coordinate_perturbation": {
            "events": perturbation,
            "summary": {
                "events_tested": len(perturbation),
                "slope_changes": sum(item["slope_changed"] for item in perturbation),
                "support_decision_changes": sum(item["support_decision_changed"] for item in perturbation),
                "grouping_changes": sum(item["grouping_changed"] for item in perturbation),
                "assignment_changes": sum(item["assignment_changed"] for item in perturbation),
            },
        },
        "support_deletion": {
            "events": deletion,
            "summary": {
                "events_tested": len(deletion),
                "total_token_deletions": sum(item["token_deletions"] for item in deletion),
                "events_with_at_least_one_decision_change": sum(item["decision_changed_count"] > 0 for item in deletion),
            },
        },
    }


def _decision_boundary_values(measurement: dict[str, Any]) -> dict[str, Any]:
    fit = measurement.get("per_token_pixel_lower_envelope_fit", {})
    slope = fit.get("slope_px_per_px")
    loo = measurement.get("leave_one_token_landmark_out_slope_range_px_per_px")
    span = measurement.get("x_span_px")
    return {
        "token_landmark_count": fit.get("support_bins"),
        "median_residual_px": fit.get("median_absolute_residual_px"),
        "leave_one_out_slope_spread_over_span_px": (loo[1] - loo[0]) * span if loo is not None and span is not None else None,
        "estimated_trend_over_span_px": abs(slope * span) if slope is not None and span is not None else None,
    }


def holdout_checks(event_records: list[dict[str, Any]]) -> dict[str, Any]:
    """Run explicit holdout ledgers; the frozen rule has no fitted parameters."""

    full_decisions = {item["event"]["event_id"]: item["features"]["local_support_decision"]["decision"] for item in event_records}
    event_holdouts = []
    for item in event_records:
        held_id = item["event"]["event_id"]
        training = [other for other in event_records if other["event"]["event_id"] != held_id]
        # Rule is parameter-free: no training labels or page values are estimated.
        event_holdouts.append({
            "held_out_event_id": held_id,
            "training_event_count": len(training),
            "held_event_decision_from_frozen_measurement": full_decisions[held_id],
            "rule_parameters_refit": False,
            "decision_stability": "unchanged_by_construction; fixed rule has no learned thresholds",
        })
    side_keys = sorted({(item["event"]["fixture_id"], item["event"]["side"]) for item in event_records})
    side_holdouts = []
    for key in side_keys:
        training = [item for item in event_records if (item["event"]["fixture_id"], item["event"]["side"]) != key]
        held = [item for item in event_records if (item["event"]["fixture_id"], item["event"]["side"]) == key]
        side_holdouts.append({
            "held_out_page_side": list(key),
            "training_event_count": len(training),
            "held_event_count": len(held),
            "held_event_decisions": {item["event"]["event_id"]: item["features"]["local_support_decision"]["decision"] for item in held},
            "rule_parameters_refit": False,
            "decision_stability": "unchanged_by_construction; fixed rule has no learned thresholds",
        })
    return {
        "leave_one_event_out": event_holdouts,
        "leave_one_page_side_out": side_holdouts,
        "interpretation": "These checks establish absence of threshold fitting/leakage, not out-of-sample predictive accuracy; the rule is frozen and decisions are local measurements.",
    }


def _numeric_summary(values: list[float]) -> dict[str, Any]:
    clean = sorted(float(value) for value in values if value is not None and math.isfinite(float(value)))
    if not clean:
        return {"n": 0, "median": None, "min": None, "max": None}
    return {"n": len(clean), "median": float(median(clean)), "min": clean[0], "max": clean[-1]}


def feature_summaries(event_records: list[dict[str, Any]]) -> dict[str, Any]:
    """Expose overlapping class distributions without fitting thresholds."""

    result: dict[str, Any] = {}
    for label in ("repaired_false_split", "new_false_split", "unresolved"):
        selected = [item for item in event_records if item["event"]["classification"] == label]
        features = {}
        for scope in ("event_only", "candidate_band", "local_x_neighborhood", "neighbor_rows"):
            scoped = [item["features"]["scopes"][scope] for item in selected]
            slopes = [row.get("per_token_pixel_lower_envelope_fit", {}).get("slope_px_per_px") for row in scoped]
            residuals = [row.get("per_token_pixel_lower_envelope_fit", {}).get("median_absolute_residual_px") for row in scoped]
            features[scope] = {
                "token_count": _numeric_summary([row["token_count"] for row in scoped]),
                "x_span_px": _numeric_summary([row["x_span_px"] for row in scoped]),
                "page_width_fraction": _numeric_summary([row["page_width_fraction"] for row in scoped]),
                "pixel_support_landmarks": _numeric_summary([row.get("per_token_pixel_lower_envelope_fit", {}).get("support_bins") for row in scoped]),
                "pixel_lower_slope_px_per_px": _numeric_summary(slopes),
                "pixel_fit_median_absolute_residual_px": _numeric_summary(residuals),
                "box_center_slope_px_per_px": _numeric_summary([row.get("local_box_center_slope_px_per_px") for row in scoped]),
                "box_vs_pixel_trend_disagreement_px": _numeric_summary([row.get("box_vs_pixel_lower_disagreement_px_over_span") for row in scoped]),
            }
        result[label] = {"event_record_count": len(selected), "features_by_scope": features}
    return result


def main() -> None:
    prior_results, events, admission_sides = load_inputs()
    event_records = []
    for key, side in admission_sides.items():
        all_boxes = boxes_from_records(side["tokens"])
        page_records = side["tokens"]
        image_path = RASTER_ROOT / key[0] / f"{key[0]}.{key[1]}.png"
        gray = np.asarray(Image.open(image_path).convert("L"))
        production_lines, production_unresolved, _ = group_page_with_local_slope(page_records, set(), None)
        production_signature = _group_signature(production_lines, production_unresolved)
        for event in events:
            if (event["fixture_id"], event["side"]) == key:
                feature = event_feature_record(event, side, all_boxes, gray)
                result = evaluate_event(event, feature, page_records, production_signature)
                if event["event_id"] in CAUSAL_REVIEW:
                    result["causal_pixel_review"] = CAUSAL_REVIEW[event["event_id"]]
                event_records.append({"event": event, "features": feature, "local_evaluation": result})

    labels = Counter(item["event"]["classification"] for item in event_records)
    actions = Counter((item["event"]["classification"], item["local_evaluation"]["decision"]) for item in event_records)
    outcomes = Counter(item["local_evaluation"]["outcome"] for item in event_records)
    local_classes = Counter(item["local_evaluation"]["local_result_adjudication"]["classification"] for item in event_records)
    unique_context_classes = {}
    v1_actions = Counter()
    for item in event_records:
        event = item["event"]
        key = (event["fixture_id"], event["side"], tuple(event["source_rows"]))
        unique_context_classes[key] = item["local_evaluation"]["local_result_adjudication"]["classification"]
        v1_actions[(event["classification"], item["features"]["v1_region_consistency_decision"]["decision"])] += 1
    results = {
        "schema": "local-slope-support-forensics-v1",
        "status": "research_complete_candidate_fails_authorization_gate",
        "prior_commit": "29428360e4b31853a36058c39795e072718fdc91",
        "research_branch": "research/local-slope-support-forensics",
        "prior_baseline_commit": prior_results["baseline_commit"],
        "prior_event_class_counts": dict(labels),
        "input_contract": {
            "prior_results_sha256": sha256(PRIOR / "results.json"),
            "prior_adjudications_sha256": sha256(PRIOR / "adjudications.json"),
            "prior_admitted_tokens_sha256": sha256(PRIOR / "admitted_tokens.json"),
            "same_once_captured_tokens_reused": True,
            "new_ocr_calls": 0,
            "rasters_are_prior_hashed_production_crops": True,
        },
        "identity_audit": context_inventory(events),
        "local_support_rule": {
            "rule_name": "robust per-token pixel lower-edge support v2",
            "physical_rationale": "Each token rectangle locates an independent physical ink sample. A local line requires at least three such supports, low robust departure from linearity, and a slope stable when any one support is removed. The 2 px trend floor respects raster sampling; the 4 px leave-one-out budget allows 2 px of displacement uncertainty on either side.",
            "parameters": {
            "pixel_threshold_gray_below": 120,
            "pixel_bin_width_px": 20,
            "token_box_margin_px": 2,
                "minimum_independent_token_pixel_landmarks": 3,
                "maximum_leave_one_landmark_slope_spread_over_span_px": 4.0,
                "maximum_median_absolute_linear_residual_px": 2.0,
                "minimum_supported_trend_over_event_span_px": 2.0,
            },
            "parameter_selection": "v2 replaces a synthetic-falsified equal-third rule; fixed from raster resolution and support-attribution rationale before v2 real-class evaluation; no event labels, page identifiers, OCR strings, or fixture-specific values enter the rule",
            "rejected_rule_v1": "equal-width third-slope consistency; the synthetic short-row and variable-height controls showed that empty/short word sections and glyph-height patterns can create false abstentions or proxy disagreement",
        },
        "decision_counts": {
            "by_prior_class_and_action": {
                f"{label}:{action}": count for (label, action), count in sorted(actions.items())
            },
            "event_level_outcomes": dict(outcomes),
            "local_result_class_counts_by_event_record": dict(local_classes),
            "local_result_class_counts_by_unique_physical_context": dict(Counter(unique_context_classes.values())),
        },
        "v1_rejected_rule_decision_counts": {f"{label}:{decision}": count for (label, decision), count in sorted(v1_actions.items())},
        "feature_distributions_by_prior_class": feature_summaries(event_records),
        "failure_topology_causal_review": [
            {"event_id": item["event"]["event_id"], "prior_classification": item["event"]["classification"], "review": item["local_evaluation"].get("causal_pixel_review")}
            for item in event_records
            if item["event"]["classification"] == "new_false_split" or item["local_evaluation"]["outcome"] == "different_local_partition_requires_adjudication"
        ],
        "synthetic_oracle": synthetic_matrix(),
        "synthetic_scale_behavior": scale_matrix(),
        "holdout_evaluation": holdout_checks(event_records),
        "stability": stability_checks(event_records, admission_sides),
        "events": event_records,
        "scope": {
            "event_only": "pixels inside event token rectangles plus two-pixel locator margin",
            "candidate_band": "same physical token membership as the changed candidate context",
            "local_x_neighborhood": "event x span plus one median event-token height on each side, with bounded vertical expansion",
            "neighbor_rows": "event neighborhood expanded to two median token heights; included as context only, never as same-row support",
        },
        "limits": [
            "The three pixel summaries are deterministic measurements, not independent statistical confidence intervals.",
            "Event-only grouping uses the production bander on that event's token subset; it does not claim full-page assignment/reconciliation output.",
            "Neighbor-context pixels are not attributed to the target row and cannot authorize local slope.",
        ],
    }
    (WORK / "results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    adjudications = {
        "schema": "local-slope-support-event-adjudications-v1",
        "authority": "prior event IDs/classes preserved; local measurements use only source raster pixels and token box coordinates as locators",
        "identity_audit": results["identity_audit"],
        "events": event_records,
    }
    (WORK / "adjudications.json").write_text(json.dumps(adjudications, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(event_records)} event variants; actions={dict(actions)}; outcomes={dict(outcomes)}")


if __name__ == "__main__":
    main()
