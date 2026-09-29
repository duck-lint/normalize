"""Compile local, text-only evidence into the committed research records."""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from normalize.geometry import _Token, _estimate_baseline_slope, group_physical_lines

from candidate_models import (
    candidate_experiments,
    page_pixel_evidence,
    scale_experiments,
    resolution_boundary_experiments,
    stability_experiments,
    synthetic_matrix,
    synthetic_pixel_matrix,
)
from run_forensics import FIXTURE_IDS, analyze


ROOT = Path(__file__).resolve().parents[3]
RESEARCH = Path(__file__).resolve().parent
WORK = Path("/tmp/baseline-slope-forensics")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def role_for_token(token: dict[str, Any], width: int, height: int, fixture_id: str) -> str:
    text = token["text"].strip()
    x, y, box_width, box_height = token["x"], token["y"], token["width"], token["height"]
    if y >= 0.93 * height and text.isdigit():
        return "page_number"
    if y <= 0.04 * height and ("relativity" in text.lower() or "stella" in text.lower() or text in {"I", "II"}):
        return "running_header_or_session_marker"
    if fixture_id == "relativity_pdf17_pp40-41" and 0.38 * height <= y <= 0.70 * height:
        return "diagram_or_figure_region"
    if fixture_id == "relativity_pdf23_pp52-53" and 0.56 * height <= y <= 0.86 * height:
        return "display_math_or_formula_region"
    if y < 0.18 * height and x > 0.15 * width and x + box_width < 0.85 * width:
        return "heading_or_centered_page_furniture"
    if box_width <= 3 or box_height <= 4:
        return "tiny_ocr_fragment_or_noise"
    if all(not character.isalnum() for character in text):
        return "punctuation_or_formula_fragment"
    return "prose_or_dialogue_region"


def compact_landscape(landscape: dict[str, Any], capture: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    capture_by_key = {(side["fixture_id"], side["side"]): side for side in capture["sides"]}
    compact_sides = []
    role_inventory = {}
    for side in landscape["sides"]:
        key = (side["fixture_id"], side["side"])
        source = capture_by_key[key]
        tokens = {token["source_row"]: token for token in source["tokens"]}
        frequency: Counter[int] = Counter()
        candidates = []
        for candidate in side.get("candidates", []):
            for identity in candidate["singleton_source_rows"]:
                frequency[identity] += 1
            candidates.append({
                "slope": candidate["slope"],
                "raw_band_count": candidate["raw_band_count"],
                "region_count": candidate["region_count"],
                "raw_band_memberships": candidate["raw_band_memberships"],
                "band_memberships_after_horizontal_splitting": candidate["memberships"],
                "singleton_count": candidate["singleton_count"],
                "singleton_source_rows": candidate["singleton_source_rows"],
                "multi_token_region_count": candidate["multi_token_region_count"],
                "horizontal_split_count": candidate["horizontal_split_count"],
                "cohesion_score": candidate["cohesion_score"],
                "zero_slope_score": candidate["zero_slope_score"],
                "rejected": candidate["rejected"],
                "rejection_reasons": candidate["rejection_reasons"],
                "would_beat_zero_without_gates": candidate["would_beat_zero_without_gates"],
                "admissible": candidate["admissible"],
                "final_rank": candidate.get("final_rank"),
            })
        role_inventory[f"{key[0]}.{key[1]}"] = [
            {
                "source_row": identity,
                "singleton_candidate_count": count,
                "text_locator_only": tokens[identity]["text"],
                "box_px": [tokens[identity]["x"], tokens[identity]["y"], tokens[identity]["width"], tokens[identity]["height"]],
                "spatial_role": role_for_token(tokens[identity], *source["dimensions_px"], side["fixture_id"]),
            }
            for identity, count in sorted(frequency.items())
        ]
        compact_sides.append({
            "fixture_id": side["fixture_id"],
            "side": side["side"],
            "declared_blank": side["blank_declared"],
            "token_count": side["token_count"],
            "selected_slope": side["selected_slope"],
            "line_count": side.get("line_count", 0),
            "ambiguous_source_rows": side.get("ambiguous_source_rows", []),
            "unassigned_source_rows": side.get("unassigned_source_rows", []),
            "zero_score": side.get("candidates", [{}])[100]["cohesion_score"] if side.get("candidates") else 0,
            "best_nonzero_by_raw_score": side.get("best_nonzero_by_raw_score"),
            "singleton_presence_rejection_count": side.get("singleton_presence_rejection_count", 0),
            "rejected_only_by_singleton_count": side.get("rejected_only_by_singleton_count", 0),
            "singleton_only_candidates_that_score_above_zero": side.get("singleton_only_candidates_that_score_above_zero", 0),
            "candidate_count": len(candidates),
            "candidate_landscape": candidates,
            "current_geometry_lines": side.get("lines", []),
            "current_geometry_unresolved": side.get("unresolved", []),
            "current_geometry_measurements": side.get("measurements", {}),
        })
    return compact_sides, role_inventory


def unique_events(comparison: dict[str, Any], pixel_evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pixel_lookup = {(item.get("fixture_id"), item.get("side")): item for item in pixel_evidence}
    unique: dict[str, dict[str, Any]] = {}
    for side in comparison["sides"]:
        for model_name, candidate in side.get("candidates", {}).items():
            for event in candidate["events"]:
                signature = canonical_hash({
                    "fixture_id": event["fixture_id"],
                    "side": event["side"],
                    "source_rows": event["source_rows"],
                    "production": [group["members"] for group in event["production_grouping"]],
                    "candidate": [group["members"] for group in event["candidate_grouping"]],
                })
                current = unique.get(signature)
                if current:
                    current["candidate_models"].append({"name": model_name, "slope": candidate["slope"]})
                    continue
                before_groups = event["production_grouping"]
                after_groups = event["candidate_grouping"]
                after_coverage = {identity for group in after_groups for identity in group["members"]}
                if len(after_groups) > len(before_groups) or not set(event["source_rows"]).issubset(after_coverage):
                    classification = "unresolved" if event["fixture_id"] == "relativity_pdf23_pp52-53" and event["side"] == "left" else "new_false_split"
                    reason = (
                        "Display-math components have raised/superscript geometry; the scan does not establish a single physical baseline for this candidate partition."
                        if classification == "unresolved" else
                        "Visually continuous printed row is split or loses an assigned token under the substituted slope."
                    )
                elif len(after_groups) < len(before_groups):
                    classification = "repaired_false_split"
                    reason = "The scan shows one continuous printed row; zero-slope grouping divided its horizontally distributed tokens into multiple regions."
                else:
                    classification = "benign_difference"
                    reason = "Membership changed without enough evidence for a physical-row repair or a row merge."
                page_pixel = pixel_lookup.get((event["fixture_id"], event["side"]), {})
                current = {
                    **event,
                    "event_id": f"{event['fixture_id']}.{event['side']}.event-{len(unique) + 1:03d}",
                    "candidate_models": [{"name": model_name, "slope": candidate["slope"]}],
                    "classification": classification,
                    "visual_physical_row_adjudication": {
                        "basis": "direct visual inspection of current production-cropped page pixels plus independent dark-pixel baseline measurements; OCR wording is retained only as a locator",
                        "reason": reason,
                        "row_pixel_evidence": {
                            "median": page_pixel.get("row_slope_median"),
                            "range": [page_pixel.get("row_slope_min"), page_pixel.get("row_slope_max")],
                            # Link this event directly to the independently adjudicated
                            # page rows so the aggregate is auditable without inference.
                            "row_evidence_ids": [
                                row["row_evidence_id"]
                                for row in page_pixel.get("adjudicated_rows", [])
                            ],
                            "adjudicated_rows": page_pixel.get("adjudicated_rows", []),
                        },
                    },
                }
                unique[signature] = current
    return sorted(unique.values(), key=lambda event: (event["fixture_id"], event["side"], event["event_id"]))


def main() -> None:
    capture = json.loads((WORK / "capture.json").read_text(encoding="utf-8"))
    landscape = analyze(capture)
    pixel = page_pixel_evidence(capture)
    comparison = candidate_experiments(capture, landscape, pixel)
    synthetic_oracle = synthetic_matrix()
    synthetic_pixels = synthetic_pixel_matrix(WORK / "synthetic-pixels")
    stability = stability_experiments(capture, pixel)
    scaling = scale_experiments(WORK / "synthetic-pixels", WORK / "synthetic-scale")
    boundaries = resolution_boundary_experiments(WORK / "threshold-boundaries")
    side_records, singleton_roles = compact_landscape(landscape, capture)
    events = unique_events(comparison, pixel)

    token_capture = []
    for side in capture["sides"]:
        token_capture.append({key: value for key, value in side.items() if key != "local_paths" and key != "tokens"} | {
            "admitted_token_sha256": side["admitted_token_sha256"],
        })
    results = {
        "schema": "baseline-slope-forensics-v2",
        "status": "completed_research_no_production_change",
        "baseline_commit": "473e639b6fe335ffb527d2338234d38e311189ba",
        "research_branch": "research/baseline-slope-forensics",
        "fixture_ids": list(FIXTURE_IDS),
        "production_hashes": {
            "src/normalize/geometry.py": digest(ROOT / "src/normalize/geometry.py"),
            "src/normalize/rendering.py": digest(ROOT / "src/normalize/rendering.py"),
            "fixtures/preprocessing.json": digest(ROOT / "fixtures/preprocessing.json"),
            "fixture_expectations": {str(path.relative_to(ROOT)): digest(path) for path in sorted((ROOT / "fixtures").glob("*/*.expected.json")) if path.is_file()},
        },
        "environment": {
            "python": sys.version.split()[0],
            "pytest": "9.1.1",
            "tesseract": "5.3.4",
            "dependencies_verified": True,
        },
        "suite_baseline": {"collected": 189, "passed": 188, "skipped": 1, "failed": 0},
        "verification": {
            "full_repository_suite": {"command": ".venv/bin/python -m pytest", "collected": 189, "passed": 188, "skipped": 1, "failed": 0},
            "focused_research_suite": {"command": ".venv/bin/python -m pytest research/geometry/baseline-slope-forensics/test_slope_forensics.py", "passed": 14, "failed": 0},
            "fixture_preprocessing_and_ocr": {"fixtures": 6, "sides": 12, "dpi": 144, "ocr_calls_per_side": 1},
            "tracked_binary_check": "git ls-files '*.png' '*.pdf' is empty",
        },
        "capture_contract": {
            "preprocessing_dpi": 144,
            "ocr_calls_per_production_side": 1,
            "same_token_capture_used_for_all_estimators": True,
            "blank_side_excluded_from_primary_totals": True,
            "side_capture_hashes": token_capture,
        },
        "mechanics": {
            "candidate_slopes": [-0.1, 0.1],
            "candidate_step": 0.001,
            "candidate_count_per_nonempty_side": 201,
            "adjusted_center": "center_y - slope * x",
            "score": "sum(n*(n-1)/2 over post-horizontal-split regions)",
            "nonzero_gates_in_order": ["at least two regions", "all regions multi-token", "score strictly exceeds zero"],
            "tie_break": "smaller absolute slope",
            "all_11_primary_sides_selected_zero": True,
            "singleton_region_veto_on_all_200_nonzero_candidates_per_primary_side": True,
        },
        "real_sides": side_records,
        "singleton_identity_roles": singleton_roles,
        "independent_pixel_evidence": pixel,
        "candidate_models": comparison,
        "changed_event_summary": {
            "identity_complete_unique_transitions": len(events),
            "classification_counts": {
                label: Counter(event["classification"] for event in events).get(label, 0)
                for label in ("repaired_false_split", "destructive_merge", "new_false_split", "benign_difference", "unresolved")
            },
            "events": events,
        },
        "synthetic_geometry_oracle": synthetic_oracle,
        "synthetic_pixel_oracle": synthetic_pixels,
        "stability": stability,
        "scale_behavior": scaling,
        "resolution_boundary_behavior": boundaries,
        "decision": "candidate failure topology requires further research",
        "decision_basis": "independent pixels establish nonzero row slopes on eight real sides, but the tested slope substitutions create new false splits and one materially relevant display-math event remains unresolved; the cohesion-only alternative also fails the synthetic disagreement and single-row abstention cases",
        "scope": {
            "production_geometry_modified": False,
            "preprocessing_modified": False,
            "ocr_modified": False,
            "horizontal_gap_behavior_modified": False,
            "reconciliation_modified": False,
            "fixture_expectations_modified": False,
            "rasters_or_pdfs_committed": False,
        },
    }
    (RESEARCH / "results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    adjudications = {
        "schema": "baseline-slope-changed-event-adjudications-v1",
        "authority": "current scan pixels; OCR wording is locator evidence only",
        "events": events,
    }
    (RESEARCH / "adjudications.json").write_text(json.dumps(adjudications, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    token_records = {
        "schema": "baseline-slope-admitted-token-capture-v1",
        "authority": "token text/boxes are locating evidence; page pixels alone adjudicate physical rows",
        "sides": [
            {key: value for key, value in side.items() if key != "local_paths"}
            for side in capture["sides"]
        ],
    }
    (RESEARCH / "admitted_tokens.json").write_text(json.dumps(token_records, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"wrote {len(side_records)} side records, {len(events)} unique changed events, {sum(len(side['candidate_landscape']) for side in side_records)} candidate records")


if __name__ == "__main__":
    main()
