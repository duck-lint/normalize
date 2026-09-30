"""Frozen-OCR coordinate-frame ablation; production modules are read-only inputs."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

from PIL import Image
from pytesseract import Output
import pytesseract

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "research/geometry/page-side-rigid-rotation"))

from normalize.fixtures import FixtureCatalog  # noqa: E402
from normalize.geometry import _Token, group_physical_lines, parse_tsv_rows  # noqa: E402
from normalize.rendering import SUCCESS, preprocess_fixture  # noqa: E402
from run_rotation_ablation import ANGLE_EVIDENCE, FIXTURE_IDS, TESSERACT_CONFIG, TESSERACT_LANGUAGE  # noqa: E402
from affine import PageAffine, make_page_affine, transform_box_envelope  # noqa: E402

BLANK_SIDE = ("stella_maris_pdf03_session-I", "left")
UNRESOLVED_SIDES = {
    ("stella_maris_pdf03_session-I", "left"),
    ("stella_maris_pdf18_session-II_p35", "left"),
}
PERTURBATION_DEGREES = (-0.2, 0.0, 0.2)
ROUNDING_RULE = "transform all four half-open box edge corners; floor x/y minima and ceil x1/y1 maxima"
MANUAL_ADJUDICATIONS = {
    "relativity_pdf10_pp26-27.left.frozen-event-004": ("repaired_false_split", "One continuous body row: ‘executing a uniform translatory motion with respect to’."),
    "relativity_pdf10_pp26-27.right.frozen-event-001": ("repaired_false_split", "The words K. through ‘the’ occupy one visibly continuous printed row."),
    "relativity_pdf10_pp26-27.right.frozen-event-004": ("repaired_false_split", "The boxes from ‘co-ordinate’ through ‘when, in relation’ lie on one descending printed row."),
    "relativity_pdf10_pp26-27.right.frozen-event-005": ("new_false_split", "‘to K, it is in a condition of uniform motion of translation’ is one visible row; transformed boxes isolate its first OCR box."),
    "relativity_pdf10_pp26-27.right.frozen-event-008": ("repaired_false_split", "One continuous row: ‘uniformly moving co-ordinate system devoid of rotation’."),
    "relativity_pdf10_pp26-27.right.frozen-event-009": ("unresolved", "The isolated tiny ‘7’ box is separated from the phrase; page pixels do not establish whether it is a footnote/mark or a token belonging to that row."),
    "relativity_pdf10_pp26-27.right.frozen-event-014": ("new_false_split", "‘affords an insufficient foundation for the physical’ is visibly one row; transformed boxes separate the OCR fragment for ‘physical’."),
    "relativity_pdf10_pp26-27.right.frozen-event-015": ("repaired_false_split", "The words ‘description of all natural phenomena. At this juncture the’ continue along one visible printed row."),
    "relativity_pdf17_pp40-41.left.frozen-event-004": ("benign_difference", "These OCR marks label separate parts of a diagram (point/velocity/train); they are not a body-text row."),
    "relativity_pdf17_pp40-41.left.frozen-event-005": ("repaired_false_split", "One continuous row: ‘train. Also the definition of simultaneity can be given’."),
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def token_identity(token: _Token) -> dict[str, Any]:
    return {
        "source_row": token.source_row,
        "text": token.text,
        "confidence": token.confidence,
        "level": token.level,
        "page_num": token.page_num,
        "block_num": token.block_num,
        "par_num": token.par_num,
        "line_num": token.line_num,
        "word_num": token.word_num,
    }


def token_record(token: _Token) -> dict[str, Any]:
    return {**token_identity(token), "x": token.x, "y": token.y, "width": token.width, "height": token.height, "x1": token.x1, "y1": token.y1}


def frozen_hash(tokens: list[_Token]) -> str:
    payload = [token_record(token) for token in tokens]
    return sha256(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def affine_payload(affine: PageAffine) -> dict[str, Any]:
    return {
        "angle_degrees": affine.angle_degrees,
        "source_dimensions_px": [affine.source_width, affine.source_height],
        "source_center_px": list(affine.source_center),
        "rotation_matrix": [list(row) for row in affine.rotation],
        "expansion_translation_px": list(affine.expansion_translation),
        "final_affine_matrix": [list(row) for row in affine.matrix],
        "destination_dimensions_px": [affine.destination_width, affine.destination_height],
        "rounding_rule": ROUNDING_RULE,
        "interpolation_note": "coordinate transform only; raster interpolation is not applied",
    }


def transformed_tokens(tokens: list[_Token], affine: PageAffine) -> tuple[list[_Token], dict[str, Any]]:
    output: list[_Token] = []
    before_widths, after_widths, before_heights, after_heights = [], [], [], []
    before_areas, after_areas = [], []
    for token in tokens:
        x, y, width, height = transform_box_envelope(affine, (token.x, token.y, token.width, token.height))
        output.append(dataclasses.replace(token, x=x, y=y, width=width, height=height))
        before_widths.append(token.width); after_widths.append(width)
        before_heights.append(token.height); after_heights.append(height)
        before_areas.append(token.width * token.height); after_areas.append(width * height)
    inflation = {
        "token_count": len(tokens),
        "mean_width_before_px": mean(before_widths) if tokens else None,
        "mean_width_after_px": mean(after_widths) if tokens else None,
        "mean_height_before_px": mean(before_heights) if tokens else None,
        "mean_height_after_px": mean(after_heights) if tokens else None,
        "mean_area_before_px2": mean(before_areas) if tokens else None,
        "mean_area_after_px2": mean(after_areas) if tokens else None,
        "tokens_with_increased_area": sum(after > before for before, after in zip(before_areas, after_areas)),
        "max_width_increase_px": max((a - b for a, b in zip(after_widths, before_widths)), default=0),
        "max_height_increase_px": max((a - b for a, b in zip(after_heights, before_heights)), default=0),
    }
    return output, inflation


def run_geometry(tokens: list[_Token]) -> dict[str, Any]:
    lines, unresolved, measurements = group_physical_lines(tokens)
    membership: dict[str, list[str]] = {str(token.source_row): [] for token in tokens}
    signature_by_line: dict[str, str] = {}
    for line in lines:
        line_rows = sorted(
            [int(token_id.removeprefix("token-")) for token_id in line["token_ids"]]
            + [int(row) for row in line["unresolved_token_source_rows"]]
        )
        signature_by_line[line["line_id"]] = "line:" + ",".join(map(str, line_rows))
        for token_id in line["token_ids"]:
            membership[token_id.removeprefix("token-").lstrip("0") or "0"] = [signature_by_line[line["line_id"]]]
    for item in unresolved:
        membership[str(item["token_source_row"])] = [signature_by_line[line_id] for line_id in item["candidate_line_ids"]]
    return {
        "token_identities_hash": sha256(json.dumps([token_identity(token) for token in tokens], separators=(",", ":")).encode()),
        "token_count": len(tokens),
        "physical_line_count": len(lines),
        "physical_lines": lines,
        "membership_by_source_row": membership,
        "ambiguous": [item for item in unresolved if item["code"] == "ambiguous_line_assignment"],
        "unassigned": [item for item in unresolved if item["code"] == "unassigned_line_assignment"],
        "selected_slope_px_per_px": measurements["baseline_slope_px_per_px"],
        "vertical_tolerance_px": measurements["tolerance_px"],
        "horizontal_gap_limit_px": measurements["horizontal_gap_limit_px"],
    }


def source_row_set(line: dict[str, Any]) -> tuple[int, ...]:
    return tuple(sorted(int(value.removeprefix("token-")) for value in line["token_ids"]))


def _groups(geometry: dict[str, Any]) -> dict[int, tuple[str, ...]]:
    result = {int(row): tuple(lines) for row, lines in geometry["membership_by_source_row"].items()}
    return result


def changed_events(fixture: str, side: str, before: dict[str, Any], after: dict[str, Any], tokens_before: list[_Token], tokens_after: list[_Token], angle: float) -> list[dict[str, Any]]:
    bm, am = _groups(before), _groups(after)
    changed = {row for row in bm if bm[row] != am.get(row, ())}
    if not changed:
        return []
    # Connect changed tokens through their old/new bands so each event is a
    # complete local membership change rather than an arbitrary string slice.
    parent = {row: row for row in changed}
    def find(row: int) -> int:
        while parent[row] != row:
            parent[row] = parent[parent[row]]
            row = parent[row]
        return row
    def union(rows: list[int]) -> None:
        rows = [row for row in rows if row in changed]
        for row in rows[1:]:
            parent[find(row)] = find(rows[0])
    for geom in (before, after):
        for line in geom["physical_lines"]:
            union([int(value.removeprefix("token-")) for value in line["token_ids"]])
    components: dict[int, list[int]] = defaultdict(list)
    for row in changed:
        components[find(row)].append(row)
    originals = {token.source_row: token for token in tokens_before}
    transformed = {token.source_row: token for token in tokens_after}
    events = []
    for event_num, rows in enumerate(sorted((sorted(rows) for rows in components.values()), key=lambda rows: rows[0]), 1):
        events.append({
            "fixture_id": fixture,
            "side": side,
            "event_id": f"{fixture}.{side}.frozen-event-{event_num:03d}",
            "source_rows": rows,
            "source_token_locators": {str(row): originals[row].text for row in rows},
            "original_boxes": {str(row): [originals[row].x, originals[row].y, originals[row].x1, originals[row].y1] for row in rows},
            "transformed_boxes": {str(row): [transformed[row].x, transformed[row].y, transformed[row].x1, transformed[row].y1] for row in rows},
            "correction_angle_degrees": angle,
            "original_memberships": {str(row): list(bm[row]) for row in rows},
            "transformed_memberships": {str(row): list(am[row]) for row in rows},
            "original_slope": before["selected_slope_px_per_px"],
            "transformed_slope": after["selected_slope_px_per_px"],
            "vertical_tolerance_px": after["vertical_tolerance_px"],
            "horizontal_gap_limit_px": after["horizontal_gap_limit_px"],
            "classification": "unresolved",
        })
    return events


def _prior_crosswalk(events: list[dict[str, Any]], prior_path: Path) -> None:
    prior = json.loads(prior_path.read_text(encoding="utf-8"))["events"]
    for event in events:
        same_page = [item for item in prior if item["fixture_id"] == event["fixture_id"] and item["side"] == event["side"]]
        event_rows = set(event["source_rows"])
        candidates = []
        for old in same_page:
            rows = set(old["source_row_identities"])
            overlap = len(rows & event_rows)
            if overlap:
                candidates.append((overlap / len(rows | event_rows), overlap, old))
        if candidates:
            score, overlap, old = max(candidates, key=lambda item: (item[0], item[1]))
            event["prior_raster_event_crosswalk"] = {
                "event_id": old["event_id"], "classification": old["classification"],
                "source_row_overlap": overlap, "jaccard": score,
                "exact_source_row_identity": set(old["source_row_identities"]) == event_rows,
            }
            if old.get("visible_interpretation"):
                event["prior_pixel_review_interpretation"] = old["visible_interpretation"]
                if set(old["source_row_identities"]) == event_rows and "visible_physical_interpretation" not in event:
                    event["visible_physical_interpretation"] = old["visible_interpretation"]
            if set(old["source_row_identities"]) == event_rows:
                old_class = old["classification"]
                before_partition = {tuple(value) for value in event["original_memberships"].values() if value}
                after_partition = {tuple(value) for value in event["transformed_memberships"].values() if value}
                if old_class == "repaired_false_split" and len(before_partition) > 1 and len(after_partition) == 1:
                    event["classification"] = "repaired_false_split"
                elif old_class == "new_false_split" and len(before_partition) > 1 and len(after_partition) == 1:
                    # The prior raster event introduced a split relative to
                    # its re-OCR control; frozen coordinates instead repair
                    # the pre-existing split in the exact same control set.
                    event["classification"] = "repaired_false_split"
                elif old_class == "new_false_split" and len(before_partition) == 1 and len(after_partition) > 1:
                    event["classification"] = "new_false_split"


def _apply_manual_adjudications(events: list[dict[str, Any]]) -> None:
    for event in events:
        decision = MANUAL_ADJUDICATIONS.get(event["event_id"])
        if decision:
            event["classification"], event["visible_physical_interpretation"] = decision


def prior_repair_crosswalk(pages: list[dict[str, Any]], prior_events: list[dict[str, Any]]) -> dict[str, Any]:
    page_by_key = {(page["fixture_id"], page["side"]): page for page in pages}
    rows = []
    for prior in prior_events:
        if prior["classification"] != "repaired_false_split":
            continue
        page = page_by_key[(prior["fixture_id"], prior["side"])]
        identities = [str(row) for row in prior["source_row_identities"]]
        before = page["control"]["membership_by_source_row"]
        after = page["transformed"]["membership_by_source_row"]
        before_bands = {tuple(before[row]) for row in identities if row in before and before[row]}
        after_bands = {tuple(after[row]) for row in identities if row in after and after[row]}
        outcome = "repaired" if len(before_bands) > 1 and len(after_bands) == 1 else "different_or_unresolved"
        rows.append({
            "prior_event_id": prior["event_id"], "fixture_id": prior["fixture_id"], "side": prior["side"],
            "source_rows": [int(row) for row in identities], "ocr_tsv_hash_exact": page["prior_control_tsv_hash_match"],
            "control_band_count": len(before_bands), "frozen_transform_band_count": len(after_bands),
            "outcome": outcome,
        })
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[row["outcome"]] += 1
    return {"prior_repair_count": len(rows), "outcome_counts": dict(counts), "events": rows}


def prior_slope_crosswalk(pages: list[dict[str, Any]], prior_results_path: Path) -> dict[str, Any]:
    prior = json.loads(prior_results_path.read_text(encoding="utf-8"))["prior_slope_context_comparison"]["contexts"]
    page_by_key = {(page["fixture_id"], page["side"]): page for page in pages}
    rows = []
    for context in prior:
        page = page_by_key[(context["fixture_id"], context["side"])]
        identities = sorted({int(item["current_source_row"]) for item in context.get("matched_tokens", []) if item.get("current_source_row") is not None})
        before = page["control"]["membership_by_source_row"]
        after = page["transformed"]["membership_by_source_row"]
        before_bands = {tuple(before[str(row)]) for row in identities if str(row) in before and before[str(row)]}
        after_bands = {tuple(after[str(row)]) for row in identities if str(row) in after and after[str(row)]}
        if len(before_bands) > 1 and len(after_bands) == 1:
            outcome = "frozen_transform_groups_to_one_band"
        elif len(after_bands) > 1:
            outcome = "remains_multi_band"
        elif not identities or not after_bands:
            outcome = "unresolved_identity_crosswalk"
        else:
            outcome = "already_one_band_or_other"
        rows.append({
            "prior_event_id": context["event_id"], "fixture_id": context["fixture_id"], "side": context["side"],
            "prior_classification": context["prior_classification"], "historical_outcome": context["outcome"],
            "current_source_rows": identities, "identity_count": len(identities), "frozen_transform_outcome": outcome,
        })
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[row["frozen_transform_outcome"]] += 1
    return {"context_count": len(rows), "outcome_counts": dict(counts), "contexts": rows}


def sensitivity_trace(fixture: str, side: str, tokens: list[_Token], width: int, height: int, chosen_angle: float, chosen_geometry: dict[str, Any]) -> list[dict[str, Any]]:
    """Trace ±0.3° around the chosen angle at 0.05° using frozen OCR only."""
    trace = []
    for step in range(-6, 7):
        angle = round(chosen_angle + step * 0.05, 2)
        affine = make_page_affine(width, height, angle)
        moved, _ = transformed_tokens(tokens, affine)
        geometry = run_geometry(moved)
        events = changed_events(fixture, side, chosen_geometry, geometry, tokens, moved, angle)
        _apply_manual_adjudications(events)
        trace.append({
            "angle_degrees": angle,
            "token_count": len(moved),
            "physical_line_count": geometry["physical_line_count"],
            "ambiguous_count": len(geometry["ambiguous"]),
            "unassigned_count": len(geometry["unassigned"]),
            "changed_source_rows_vs_chosen": sorted({row for event in events for row in event["source_rows"]}),
            "changed_events_vs_chosen": events,
        })
    return trace


def rebuild_from_frozen_capture(capture_path: Path, output_path: Path) -> dict[str, Any]:
    """Recompute geometry/adjudication from saved source OCR without invoking OCR."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = json.loads(capture_path.read_text(encoding="utf-8"))
    prior = json.loads((ROOT / "research/geometry/page-side-rigid-rotation/results.json").read_text(encoding="utf-8"))
    prior_pages = {(page["fixture_id"], page["side"]): page for page in prior["pages"]}
    result["changed_events"] = []
    result["ocr"]["reused_saved_capture_for_analysis"] = True
    result["tesseract_version"] = "5.3.4"
    result["production_source_hashes"] = {
        "src/normalize/geometry.py": sha256((ROOT / "src/normalize/geometry.py").read_bytes()),
        "src/normalize/rendering.py": sha256((ROOT / "src/normalize/rendering.py").read_bytes()),
        "fixtures/preprocessing.json": sha256((ROOT / "fixtures/preprocessing.json").read_bytes()),
    }
    for page in result["pages"]:
        key = (page["fixture_id"], page["side"])
        page["angle_evidence"] = ANGLE_EVIDENCE[f"{key[0]}.{key[1]}"]
        prior_control_hash = prior_pages[key]["control"]["ocr_tsv_sha256"]
        page["prior_control_tsv_hash_match"] = page["source_tsv_sha256"] == prior_control_hash
        page["prior_control_tsv_hash"] = prior_control_hash
        if not page["prior_control_tsv_hash_match"]:
            raise AssertionError(f"fresh frozen OCR differs from prior study control TSV for {key}")
        tokens = [_Token(
            item["source_row"], item["text"], item["confidence"], item["level"], item["page_num"],
            item["block_num"], item["par_num"], item["line_num"], item["word_num"],
            item["x"], item["y"], item["width"], item["height"],
        ) for item in page["frozen_tokens"]]
        if frozen_hash(tokens) != page["frozen_token_record_sha256"]:
            raise AssertionError(f"saved token record hash mismatch for {key}")
        page["control"] = run_geometry(tokens)
        angle = page["angle_degrees"]
        applied = 0.0 if angle is None else float(angle)
        affine = make_page_affine(*page["source_dimensions_px"], applied)
        moved, inflation = transformed_tokens(tokens, affine)
        page["affine"] = affine_payload(affine)
        page["aabb_inflation"] = inflation
        page["transformed"] = run_geometry(moved)
        page["token_identity_invariant"] = [token_identity(t) for t in moved] == [token_identity(t) for t in tokens]
        if not page["token_identity_invariant"]:
            raise AssertionError(f"token identity changed for {key}")
        if angle is None or float(angle) == 0.0:
            page["zero_degree_output_identical"] = page["control"] == page["transformed"]
            if not page["zero_degree_output_identical"]:
                raise AssertionError(f"untransformed page geometry changed for {key}")
        page_events = changed_events(page["fixture_id"], page["side"], page["control"], page["transformed"], tokens, moved, applied)
        page["changed_events"] = page_events
        result["changed_events"].extend(page_events)
        page["perturbations"] = []
        page["sensitivity_trace"] = []
        page["geometry_status"] = "uncertain" if page["control"]["ambiguous"] or page["control"]["unassigned"] else "success"
        if angle is not None and float(angle) != 0.0:
            for delta in PERTURBATION_DEGREES:
                perturbed_angle = float(angle) + delta
                perturbed_affine = make_page_affine(*page["source_dimensions_px"], perturbed_angle)
                perturbed, perturbed_inflation = transformed_tokens(tokens, perturbed_affine)
                geometry = run_geometry(perturbed)
                events = changed_events(page["fixture_id"], page["side"], page["control"], geometry, tokens, perturbed, perturbed_angle)
                page["perturbations"].append({
                    "angle_degrees": perturbed_angle,
                    "token_count": len(perturbed),
                    "token_record_sha256": frozen_hash(tokens),
                    "geometry": geometry,
                    "aabb_inflation": perturbed_inflation,
                    "changed_events": events,
                })
            page["sensitivity_trace"] = sensitivity_trace(
                page["fixture_id"], page["side"], tokens,
                page["source_dimensions_px"][0], page["source_dimensions_px"][1],
                float(angle), page["transformed"],
            )
    adjudication_path = ROOT / "research/geometry/page-side-rigid-rotation/adjudications.json"
    _prior_crosswalk(result["changed_events"], adjudication_path)
    _apply_manual_adjudications(result["changed_events"])
    for page in result["pages"]:
        _prior_crosswalk(page.get("changed_events", []), adjudication_path)
        _apply_manual_adjudications(page.get("changed_events", []))
        for variant in page["perturbations"]:
            _prior_crosswalk(variant["changed_events"], adjudication_path)
            _apply_manual_adjudications(variant["changed_events"])
    prior_events = json.loads(adjudication_path.read_text(encoding="utf-8"))["events"]
    result["prior_raster_repair_crosswalk"] = prior_repair_crosswalk(result["pages"], prior_events)
    result["prior_slope_context_crosswalk"] = prior_slope_crosswalk(
        result["pages"], ROOT / "research/geometry/page-side-rigid-rotation/results.json"
    )
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def run(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    prep_root = output_dir / "production-preprocessing"
    catalog = FixtureCatalog.load(ROOT)
    result: dict[str, Any] = {
        "schema": "frozen-ocr-page-coordinate-rotation-v1",
        "branch_base": "88c8b04ddab3ad128caef107a54972e479b84c63",
        "ocr": {"language": TESSERACT_LANGUAGE, "config": TESSERACT_CONFIG, "calls": 0, "frozen_once_per_side": True},
        "tesseract_version": str(pytesseract.get_tesseract_version()).strip(),
        "production_source_hashes": {
            "src/normalize/geometry.py": sha256((ROOT / "src/normalize/geometry.py").read_bytes()),
            "src/normalize/rendering.py": sha256((ROOT / "src/normalize/rendering.py").read_bytes()),
            "fixtures/preprocessing.json": sha256((ROOT / "fixtures/preprocessing.json").read_bytes()),
        },
        "rounding_rule": ROUNDING_RULE,
        "pages": [],
        "changed_events": [],
    }
    for fixture_id in FIXTURE_IDS:
        fixture = catalog.get(fixture_id)
        fixture_dir = prep_root / fixture_id
        prep = preprocess_fixture(fixture, ROOT / "fixtures/preprocessing.json", fixture_dir)
        if prep["status"] != SUCCESS:
            raise RuntimeError(f"production preprocessing failed: {fixture_id}: {prep}")
        metadata = json.loads((fixture_dir / f"{fixture_id}.preprocess.json").read_text())
        for page in metadata["pages"]:
            side = page["side"]
            key = f"{fixture_id}.{side}"
            image_path = fixture_dir / page["output_path"]
            with Image.open(image_path) as image_file:
                image = image_file.convert("RGB")
            tsv = pytesseract.image_to_data(image, lang=TESSERACT_LANGUAGE, config=TESSERACT_CONFIG, output_type=Output.STRING)
            result["ocr"]["calls"] += 1
            tokens, parse_errors = parse_tsv_rows(tsv, image.width, image.height)
            if parse_errors:
                raise RuntimeError(f"production TSV parse errors for {key}: {parse_errors[:2]}")
            frozen_identity = [token_identity(token) for token in tokens]
            frozen_digest = frozen_hash(tokens)
            control = run_geometry(tokens)
            angle = ANGLE_EVIDENCE[key]["angle_degrees"]
            unresolved_angle = angle is None
            chosen = 0.0 if unresolved_angle else float(angle)
            affine = make_page_affine(image.width, image.height, chosen)
            transformed, inflation = transformed_tokens(tokens, affine)
            corrected = run_geometry(transformed)
            if [token_identity(token) for token in transformed] != frozen_identity:
                raise AssertionError(f"token identity changed under geometry transform: {key}")
            event_list = changed_events(fixture_id, side, control, corrected, tokens, transformed, chosen)
            result["changed_events"].extend(event_list)
            page_result: dict[str, Any] = {
                "fixture_id": fixture_id, "side": side,
                "source_dimensions_px": [image.width, image.height],
                "source_image_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
                "source_tsv_sha256": sha256(tsv.encode("utf-8")),
                "frozen_token_record_sha256": frozen_digest,
                "frozen_token_count": len(tokens),
                "frozen_tokens": [token_record(token) for token in tokens],
                "token_identity_invariant": True,
                "ocr_invocations_for_side": 1,
                "angle_degrees": None if unresolved_angle else chosen,
                "angle_status": "unresolved; geometry unchanged" if unresolved_angle else "measured in prior page-pixel study",
                "angle_evidence": ANGLE_EVIDENCE[key],
                "affine": affine_payload(affine),
                "aabb_inflation": inflation,
                "control": control,
                "transformed": corrected,
                "changed_events": event_list,
                "perturbations": [],
                "blank_side_diagnostics": fixture_id == BLANK_SIDE[0] and side == BLANK_SIDE[1],
                "geometry_status": "uncertain" if control["ambiguous"] or control["unassigned"] else "success",
            }
            if not unresolved_angle and chosen != 0.0:
                for delta in PERTURBATION_DEGREES:
                    perturbed_angle = chosen + delta
                    perturbed_affine = make_page_affine(image.width, image.height, perturbed_angle)
                    perturbed_tokens, perturbed_inflation = transformed_tokens(tokens, perturbed_affine)
                    if [token_identity(token) for token in perturbed_tokens] != frozen_identity:
                        raise AssertionError(f"token identity changed in perturbation: {key}")
                    geom = run_geometry(perturbed_tokens)
                    page_result["perturbations"].append({
                        "angle_degrees": perturbed_angle,
                        "token_count": len(perturbed_tokens),
                        "token_record_sha256": frozen_digest,
                        "geometry": geom,
                        "aabb_inflation": perturbed_inflation,
                        "changed_events": changed_events(fixture_id, side, control, geom, tokens, perturbed_tokens, perturbed_angle),
                    })
            if angle == 0.0:
                page_result["zero_degree_output_identical"] = control == corrected
                if control != corrected:
                    raise AssertionError(f"zero degree transform changed geometry: {key}")
            result["pages"].append(page_result)
            print(f"{key}: OCR={len(tokens)} lines={control['physical_line_count']}→{corrected['physical_line_count']} angle={angle}")
    result["ocr"]["calls"] = int(result["ocr"]["calls"])
    _prior_crosswalk(result["changed_events"], ROOT / "research/geometry/page-side-rigid-rotation/adjudications.json")
    _apply_manual_adjudications(result["changed_events"])
    for page in result["pages"]:
        _apply_manual_adjudications(page.get("changed_events", []))
        for variant in page["perturbations"]:
            _prior_crosswalk(variant["changed_events"], ROOT / "research/geometry/page-side-rigid-rotation/adjudications.json")
            _apply_manual_adjudications(variant["changed_events"])
    (output_dir / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=HERE / "local-run")
    parser.add_argument("--reuse-frozen-json", type=Path)
    args = parser.parse_args()
    if args.reuse_frozen_json:
        rebuild_from_frozen_capture(args.reuse_frozen_json, args.output_dir / "results.json")
    else:
        run(args.output_dir)
