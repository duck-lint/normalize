"""Compare frozen OCR box center and lower-edge anchors against pixel rows.

This shadow implementation mirrors the current Slice 2 band/candidate rules;
its only experimental input is the selected vertical coordinate. The saved OCR
observations remain immutable, and image reconstruction is used only to verify
the prior raster hashes and bind the human row oracle to those pixels.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
PRIOR = ROOT / "research/geometry/spineless-acquisition-ablation"
RESIDUAL = ROOT / "research/geometry/spineless-residual-forensics"
ORACLE_PATH = HERE / "row-oracle.json"
OUTPUT_PATH = HERE / "anchor-comparison.json"
PAGES = (26, 27, 40, 41, 52, 53)
TARGETS = {26: 76, 27: 37, 53: 111}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_prior_and_verify() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Reuse saved OCR; reconstruct pixels only to verify their recorded hash."""
    acquisition = json.loads((PRIOR / "results.json").read_text())
    reproduction = json.loads((RESIDUAL / "results.json").read_text())
    oracle = json.loads(ORACLE_PATH.read_text())
    spec = importlib.util.spec_from_file_location("prior_spineless", PRIOR / "run_ablation.py")
    assert spec and spec.loader
    prior_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prior_module)
    for page in PAGES:
        record = acquisition["spineless"][str(page)]
        prior_record = reproduction["pages"][str(page)]
        source_path = ROOT / "fixtures/einstein/spineless" / record["source_filename"]
        source_hash = _sha256(source_path.read_bytes())
        assert source_hash == record["source_sha256"] == prior_record["source_sha256"]
        from PIL import Image

        with Image.open(source_path) as source:
            _crop, _rotated, final = prior_module.prepare_spineless_raster(
                source.convert("RGB"), tuple(record["crop_box"]), record["angle_correction_degrees"]
            )
        raster_hash = _sha256(final.tobytes())
        assert raster_hash == record["transform"]["final_rgb_sha256"]
        assert raster_hash == prior_record["final_rgb_sha256"]
        assert oracle["pages"][str(page)]["raster_sha256"] == raster_hash
        assert record["tsv_sha256"] == prior_record["raw_tsv_sha256"]
        geometry = record["geometry"]
        assert len(geometry["tokens"]) == prior_record["admitted_tokens"]
        assert len(geometry["physical_lines"]) == prior_record["physical_lines"]
        assert geometry["ambiguous_count"] == prior_record["ambiguous"] == 0
        assert geometry["unassigned_count"] == prior_record["unassigned"] == 0
        assert geometry["measurements"]["baseline_slope_px_per_px"] == prior_record["selected_slope"] == 0.0
        assert geometry["measurements"]["tolerance_px"] == prior_record["vertical_tolerance"] == 4
    return acquisition, reproduction, oracle


def _anchor(token: dict[str, Any], vertical_anchor: str) -> float:
    center_y = token["y"] + token["height"] / 2
    if vertical_anchor == "center_y":
        return center_y
    if vertical_anchor == "y1":
        return token["y"] + token["height"]
    raise ValueError(f"unsupported vertical anchor: {vertical_anchor}")


def _gap_limit(tokens: list[dict[str, Any]]) -> float:
    widths = sorted(token["width"] for token in tokens if token["width"] > 0)
    return max(1.0, 2.0 * statistics.median(widths)) if widths else 1.0


def _horizontally_adjacent(left: dict[str, Any], right: dict[str, Any], gap_limit: float) -> bool:
    if left["x"] == right["x"]:
        return False
    first, second = sorted((left, right), key=lambda token: (token["x"], token["source_row"]))
    return second["x"] - (first["x"] + first["width"]) <= gap_limit


def _partition(tokens: list[dict[str, Any]], values: dict[int, float]) -> tuple[list[list[dict[str, Any]]], list[list[dict[str, Any]]]]:
    """Mirror `_line_bands` ordering/support, then cumulative horizontal split."""
    gap_limit = _gap_limit(tokens)
    ordered = sorted(tokens, key=lambda t: (values[t["source_row"]], t["x"], t["source_row"]))
    vertical_bands: list[list[dict[str, Any]]] = []
    for token in ordered:
        if vertical_bands:
            current = vertical_bands[-1]
            current_median = statistics.median(values[item["source_row"]] for item in current)
            value = values[token["source_row"]]
            median_support = abs(value - current_median) <= 4
            neighbor_support = any(
                abs(value - values[item["source_row"]]) <= 4
                and _horizontally_adjacent(item, token, gap_limit)
                for item in current
            )
            if median_support or neighbor_support:
                current.append(token)
                continue
        vertical_bands.append([token])

    regions: list[list[dict[str, Any]]] = []
    for band in vertical_bands:
        ordered_x = sorted(band, key=lambda token: (token["x"], token["source_row"]))
        region: list[dict[str, Any]] = []
        covered_right: int | None = None
        for token in ordered_x:
            if region and covered_right is not None and token["x"] - covered_right > gap_limit:
                regions.append(region)
                region = []
                covered_right = None
            region.append(token)
            covered_right = token["x"] + token["width"] if covered_right is None else max(
                covered_right, token["x"] + token["width"]
            )
        if region:
            regions.append(region)
    return vertical_bands, regions


def _full_grouping(tokens: list[dict[str, Any]], vertical_anchor: str, *, order: str = "production") -> dict[str, Any]:
    """Shadow the current production candidate-generation and assignment path."""
    values = {t["source_row"]: _anchor(t, vertical_anchor) for t in tokens}
    if order == "x":
        ordered = sorted(tokens, key=lambda t: (t["x"], t["source_row"]))
        vertical_bands, regions = _partition_in_order(tokens, values, ordered)
    else:
        vertical_bands, regions = _partition(tokens, values)
    gap_limit = _gap_limit(tokens)
    ordered_regions = sorted(
        enumerate(regions),
        key=lambda pair: (statistics.median(values[t["source_row"]] for t in pair[1]),
                          min(token["x"] for token in pair[1]), pair[0]),
    )
    line_ids = {region_index: f"line-{ordinal:04d}" for ordinal, (region_index, _region) in enumerate(ordered_regions, 1)}
    candidates: dict[int, list[str]] = {}
    region_by_id = {line_ids[index]: region for index, region in enumerate(regions)}
    for token in tokens:
        token_regions: list[str] = []
        for region_index, region in ordered_regions:
            center_support = abs(values[token["source_row"]] - statistics.median(
                values[item["source_row"]] for item in region
            )) <= 4
            adjacent_support = any(
                abs(values[token["source_row"]] - values[item["source_row"]]) <= 4
                and item["source_row"] != token["source_row"]
                and _horizontally_adjacent(item, token, gap_limit)
                for item in region
            )
            if ((any(item["source_row"] == token["source_row"] for item in region)
                 and (center_support or adjacent_support))
                or (center_support and min(item["x"] for item in region) <= token["x"]
                    <= max(item["x"] + item["width"] for item in region))):
                token_regions.append(line_ids[region_index])
        candidates[token["source_row"]] = token_regions
    assignments: dict[str, list[int]] = {line_id: [] for line_id in line_ids.values()}
    unresolved: list[dict[str, Any]] = []
    for token in tokens:
        found = candidates[token["source_row"]]
        if len(found) == 1:
            assignments[found[0]].append(token["source_row"])
        elif len(found) > 1:
            unresolved.append({"source_row": token["source_row"], "candidate_line_ids": found})
        else:
            unresolved.append({"source_row": token["source_row"], "candidate_line_ids": []})
    partitions = {line_id: sorted(source_rows) for line_id, source_rows in assignments.items()}
    return {
        "vertical_bands": [[t["source_row"] for t in band] for band in vertical_bands],
        "vertical_regions": [[t["source_row"] for t in region] for region in regions],
        "candidate_line_ids": candidates,
        "partitions": partitions,
        "unresolved": unresolved,
        "gap_limit": gap_limit,
        "values": values,
    }


def _partition_in_order(tokens: list[dict[str, Any]], values: dict[int, float], ordered: list[dict[str, Any]]) -> tuple[list[list[dict[str, Any]]],list[list[dict[str, Any]]]]:
    """Diagnostic replay with x order; band predicate and all constants stay fixed."""
    gap_limit = _gap_limit(tokens)
    vertical: list[list[dict[str, Any]]] = []
    for token in ordered:
        if vertical:
            current = vertical[-1]
            current_median = statistics.median(values[item["source_row"]] for item in current)
            value = values[token["source_row"]]
            if abs(value-current_median) <= 4 or any(
                abs(value-values[item["source_row"]]) <= 4 and _horizontally_adjacent(item,token,gap_limit)
                for item in current
            ):
                current.append(token)
                continue
        vertical.append([token])
    result=[]
    for band in vertical:
        region=[]; right=None
        for token in sorted(band,key=lambda t:(t["x"],t["source_row"])):
            if region and right is not None and token["x"]-right > gap_limit:
                result.append(region); region=[]; right=None
            region.append(token); right=token["x"]+token["width"] if right is None else max(right,token["x"]+token["width"])
        if region: result.append(region)
    return vertical, result


def _row_oracle_tokens(tokens: list[dict[str, Any]], page_oracle: dict[str, Any]) -> list[dict[str, Any]]:
    rows=[]
    row_ordinal=0
    for block in page_oracle["blocks"]:
        for top,bottom in block["rows"]:
            row_ordinal+=1
            identities=[token["source_row"] for token in tokens
                        if top-5 <= token["y"]+token["height"]/2 <= bottom+5]
            rows.append({"row_id":f"p{page_oracle['page']}-r{row_ordinal:03d}","block_id":block["block_id"],
                         "pixel_region":[top,bottom],"source_rows":sorted(identities)})
    return rows


def _dispersion(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"min":None,"max":None,"range":None,"median":None,"mad":None,"max_abs_from_median":None}
    med=statistics.median(values)
    return {"min":min(values),"max":max(values),"range":max(values)-min(values),"median":med,
            "mad":statistics.median(abs(v-med) for v in values),"max_abs_from_median":max(abs(v-med) for v in values)}


def _row_classification(rows: list[dict[str, Any]], grouping: dict[str, Any]) -> tuple[dict[str, str], list[dict[str, Any]]]:
    row_by_source={source:row["row_id"] for row in rows for source in row["source_rows"]}
    line_by_source={source:line_id for line_id,sources in grouping["partitions"].items() for source in sources}
    sources_by_line=defaultdict(list)
    for source,line_id in line_by_source.items(): sources_by_line[line_id].append(source)
    row_lines={}
    for row in rows:
        row_lines[row["row_id"]]=sorted({line_by_source[s] for s in row["source_rows"] if s in line_by_source})
    result={}; harms=[]
    for row in rows:
        rid=row["row_id"]; sources=row["source_rows"]
        if not sources or any(source not in line_by_source for source in sources):
            result[rid]="unresolved"; continue
        lines=row_lines[rid]
        foreign=[]
        for line in lines:
            foreign.extend(source for source in sources_by_line[line] if row_by_source.get(source) not in (None,rid))
        if foreign:
            result[rid]="destructive_merge_with_neighbor"
        elif len(lines)>1:
            result[rid]="false_split"
        else:
            result[rid]="correct_single_band"
    return result, harms


def _target_trace(tokens: list[dict[str, Any]], vertical_anchor: str, source_row: int) -> dict[str, Any]:
    values={t["source_row"]:_anchor(t,vertical_anchor) for t in tokens}
    gap_limit=_gap_limit(tokens)
    ordered=sorted(tokens,key=lambda t:(values[t["source_row"]],t["x"],t["source_row"]))
    band=[]; target=None; trace=None
    for token in ordered:
        value=values[token["source_row"]]
        if band:
            med=statistics.median(values[t["source_row"]] for t in band)
            med_ok=abs(value-med)<=4
            supports=[t for t in band if abs(value-values[t["source_row"]])<=4 and _horizontally_adjacent(t,token,gap_limit)]
            neighbor=bool(supports)
            if token["source_row"]==source_row:
                evaluations=[]
                for item in band:
                    difference=abs(value-values[item["source_row"]])
                    if difference<=4:
                        first,second=sorted((item,token),key=lambda item:(item["x"],item["source_row"]))
                        evaluations.append({"source_row":item["source_row"],"anchor_difference":difference,
                                            "same_x":item["x"]==token["x"],
                                            "evaluated_x_gap":second["x"]-(first["x"]+first["width"]),
                                            "horizontal_gap_limit":gap_limit,
                                            "horizontal_adjacency":_horizontally_adjacent(item,token,gap_limit)})
                trace={"anchor":vertical_anchor,"source_row":source_row,"anchor_value":value,
                       "running_band_source_rows":[t["source_row"] for t in band],"running_median":med,
                       "difference":abs(value-med),"tolerance":4,"median_support":med_ok,
                       "neighbor_support_sources":[t["source_row"] for t in supports],
                       "neighbor_predicate_evaluations":evaluations,
                       "decision":"joins_last_band" if med_ok or neighbor else "starts_new_band"}
            if med_ok or neighbor:
                band.append(token)
            else: band=[token]
        else:
            band=[token]
    return trace or {"anchor":vertical_anchor,"source_row":source_row,"error":"target not found"}


def _aggregate_metrics(pages: dict[str, Any]) -> dict[str, Any]:
    result={}
    for anchor in ("center_y","y1"):
        ranges=[]; mads=[]; maxdev=[]
        for page in pages.values():
            for row in page["row_metrics"]:
                d=row["observables"][anchor]
                ranges.append(d["range"]); mads.append(d["mad"]); maxdev.append(d["max_abs_from_median"])
        def summary(values: list[float]) -> dict[str,float]:
            ordered=sorted(values)
            def q(frac:float)->float:
                return ordered[round((len(ordered)-1)*frac)]
            return {"n":len(values),"median":statistics.median(values),"mean":statistics.mean(values),
                    "q10":q(.1),"q25":q(.25),"q75":q(.75),"q90":q(.9)}
        result[anchor]={"row_range_px":summary(ranges),"row_mad_px":summary(mads),"row_max_abs_deviation_px":summary(maxdev)}
    return result


def _neighbor_metrics(rows: list[dict[str, Any]], tokens_by_source: dict[int,dict[str,Any]]) -> list[dict[str,Any]]:
    result=[]
    for left,right in zip(rows,rows[1:]):
        if left["block_id"]!=right["block_id"]: continue
        left_tokens=[tokens_by_source[s] for s in left["source_rows"]]
        right_tokens=[tokens_by_source[s] for s in right["source_rows"]]
        if not left_tokens or not right_tokens: continue
        item={"above_row":left["row_id"],"below_row":right["row_id"]}
        for anchor in ("center_y","y1"):
            a=[_anchor(t,anchor) for t in left_tokens]; b=[_anchor(t,anchor) for t in right_tokens]
            overlap=max(0.0,min(max(a),max(b))-max(min(a),min(b)))
            item[anchor]={"above_median":statistics.median(a),"below_median":statistics.median(b),
                          "median_separation":statistics.median(b)-statistics.median(a),
                          "minimum_cross_row_absolute_separation":min(abs(x-y) for x in a for y in b),
                          "signed_range_separation":min(b)-max(a),"range_overlap_px":overlap}
        result.append(item)
    return result


def _co_membership(partition: dict[str, list[int]]) -> set[tuple[int,int]]:
    return {tuple(sorted((a,b))) for group in partition.values() for i,a in enumerate(group) for b in group[i+1:]}


def _sensitivity(tokens: list[dict[str,Any]], anchor:str, base:dict[str,Any], rows:list[dict[str,Any]], target_source_row:int|None=None) -> dict[str,Any]:
    base_pairs=_co_membership(base["partitions"])
    base_partition=base["partitions"]
    cases=[]
    for mode in ("uniform_minus_1","uniform_plus_1","deterministic_individual_jitter"):
        if mode=="deterministic_individual_jitter":
            rng=random.Random(7301)
            shifts={t["source_row"]:rng.choice((-1,1)) for t in tokens}
        else:
            shift=-1 if mode=="uniform_minus_1" else 1
            shifts={t["source_row"]:shift for t in tokens}
        shifted=[]
        for token in tokens:
            copy=dict(token); copy["y"]+=shifts[token["source_row"]]; shifted.append(copy)
        grouping=_full_grouping(shifted,anchor)
        pairs=_co_membership(grouping["partitions"])
        labels=_row_classification(rows,grouping)[0]
        counts=defaultdict(int)
        for label in labels.values(): counts[label]+=1
        target_trace=None
        if target_source_row is not None:
            target_trace=_target_trace(shifted,anchor,target_source_row)
        changed_rows=[row_id for row_id,label in labels.items()
                      if label != _row_classification(rows,base)[0][row_id]]
        cases.append({"mode":mode,"token_count":len(shifted),"pairwise_memberships_changed":len(base_pairs.symmetric_difference(pairs)),
                      "partition_equal":{k:sorted(v) for k,v in grouping["partitions"].items()}=={k:sorted(v) for k,v in base_partition.items()},
                      "unresolved_count":len(grouping["unresolved"]),"row_classification_counts":dict(counts),
                      "changed_oracle_rows":changed_rows,"target_trace":target_trace,
                      "seed":7301 if mode=="deterministic_individual_jitter" else None})
    return {"cases":cases}


def _synthetic_controls() -> dict[str, Any]:
    def make_top_row(start: int, y: float, heights: list[int], x_start: int = 10) -> list[dict[str, Any]]:
        return [{"source_row": start + i, "x": x_start + i * 18, "y": y, "width": 10, "height": height}
                for i, height in enumerate(heights)]
    def make_bottom_row(start: int, bottom: float, heights: list[int], x_start: int = 10) -> list[dict[str, Any]]:
        return [{"source_row": start + i, "x": x_start + i * 18, "y": bottom-height, "width": 10, "height": height}
                for i, height in enumerate(heights)]
    def make_center_row(start: int, center: float, heights: list[int], x_start: int = 10) -> list[dict[str, Any]]:
        return [{"source_row": start + i, "x": x_start + i * 18, "y": center-height/2, "width": 10, "height": height}
                for i, height in enumerate(heights)]

    cases = {
        "equal_bottom_varying_heights": make_bottom_row(1, 30, [6, 14, 26, 40]),
        "equal_center_varying_heights": [
            {"source_row": 1 + i, "x": 10 + i * 18, "y": 20 - h / 2, "width": 10, "height": h}
            for i, h in enumerate([6, 14, 26, 40])],
        "two_adjacent_rows_equal_height": make_top_row(1, 10, [16] * 4) + make_top_row(5, 30, [16] * 4),
        "two_rows_strongly_varying_heights": make_center_row(1, 30, [6, 14, 26, 40]) + make_center_row(5, 60, [40, 26, 14, 6]),
        "descender_like_lower_box_outlier": make_center_row(1, 30, [16, 16, 30, 16]),
        "close_rows_nearly_overlapping_bottoms": [
            {"source_row": 1, "x": 10, "y": 20, "width": 10, "height": 10},
            {"source_row": 2, "x": 30, "y": 20, "width": 10, "height": 10},
            {"source_row": 3, "x": 10, "y": 8, "width": 10, "height": 24},
            {"source_row": 4, "x": 30, "y": 8, "width": 10, "height": 24},
        ],
    }
    expected = {
        "equal_bottom_varying_heights": [[1, 2, 3, 4]],
        "equal_center_varying_heights": [[1, 2, 3, 4]],
        "two_adjacent_rows_equal_height": [[1, 2, 3, 4], [5, 6, 7, 8]],
        "two_rows_strongly_varying_heights": [[1, 2, 3, 4], [5, 6, 7, 8]],
        "descender_like_lower_box_outlier": [[1, 2, 3, 4]],
        "close_rows_nearly_overlapping_bottoms": [[1, 2], [3, 4]],
    }
    result = {}
    for name, tokens in cases.items():
        result[name] = {}
        for anchor in ("center_y", "y1"):
            values = {token["source_row"]: _anchor(token, anchor) for token in tokens}
            bands, _regions = _partition(tokens, values)
            observed = sorted([sorted(token["source_row"] for token in band) for band in bands])
            result[name][anchor] = {"vertical_bands": observed, "expected_physical_rows": expected[name],
                                    "correct": observed == sorted(expected[name])}
    return result


def _row_transition_ledger(record: dict[str, Any]) -> list[dict[str, Any]]:
    center = record["variants"]["center_y"]["production"]
    bottom = record["variants"]["y1"]["production"]
    events = []
    for row in record["pixel_oracle_rows"]:
        row_id = row["row_id"]
        if (center["row_classifications"][row_id] == bottom["row_classifications"][row_id]
                and center["vertical_row_classifications"][row_id] == bottom["vertical_row_classifications"][row_id]):
            continue
        row_sources = set(row["source_rows"])
        events.append({"row_id": row_id, "pixel_region": row["pixel_region"], "source_rows": row["source_rows"],
                       "center_vertical": center["vertical_row_classifications"][row_id],
                       "y1_vertical": bottom["vertical_row_classifications"][row_id],
                       "center_final": center["row_classifications"][row_id],
                       "y1_final": bottom["row_classifications"][row_id],
                       "center_line_memberships": [sorted(group) for group in center["grouping"]["partitions"].values()
                                                    if row_sources.intersection(group)],
                       "y1_line_memberships": [sorted(group) for group in bottom["grouping"]["partitions"].values()
                                               if row_sources.intersection(group)],
                       "center_vertical_band_memberships": [sorted(group) for group in center["grouping"]["vertical_bands"]
                                                             if row_sources.intersection(group)],
                       "y1_vertical_band_memberships": [sorted(group) for group in bottom["grouping"]["vertical_bands"]
                                                         if row_sources.intersection(group)], "boxes": row["tokens"]})
    return events


def _classification_counts(pages: dict[str, Any], anchor: str, order: str, stage: str) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    field = "row_classifications" if stage == "final" else "vertical_row_classifications"
    for record in pages.values():
        for label in record["variants"][anchor][order][field].values():
            counts[label] += 1
    return dict(counts)


def _neighbor_summary(pages: dict[str, Any]) -> dict[str, Any]:
    pairs = [pair for record in pages.values() for pair in record["adjacent_row_metrics"]]
    result = {}
    for anchor in ("center_y", "y1"):
        signed = [pair[anchor]["signed_range_separation"] for pair in pairs]
        minimum = [pair[anchor]["minimum_cross_row_absolute_separation"] for pair in pairs]
        overlap = [pair[anchor]["range_overlap_px"] for pair in pairs]
        medians = [pair[anchor]["median_separation"] for pair in pairs]
        result[anchor] = {
            "n_adjacent_pairs": len(pairs),
            "signed_range_separation_px": {"median": statistics.median(signed), "min": min(signed), "max": max(signed),
                                           "nonpositive_count": sum(value <= 0 for value in signed)},
            "minimum_cross_row_absolute_separation_px": {"median": statistics.median(minimum), "min": min(minimum)},
            "range_overlap_px": {"median": statistics.median(overlap), "nonzero_pairs": sum(value > 0 for value in overlap)},
            "median_to_median_separation_px": {"median": statistics.median(medians), "min": min(medians)},
        }
    return result


def _order_sensitivity(pages: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for anchor in ("center_y", "y1"):
        result[anchor] = {}
        for page, record in pages.items():
            production = record["variants"][anchor]["production"]["row_classifications"]
            x_order = record["variants"][anchor]["x"]["row_classifications"]
            production_vertical = record["variants"][anchor]["production"]["vertical_row_classifications"]
            x_vertical = record["variants"][anchor]["x"]["vertical_row_classifications"]
            result[anchor][page] = {
                "changed_rows": [row_id for row_id in production if production[row_id] != x_order[row_id]],
                "vertical_band_changed_rows": [row_id for row_id in production_vertical
                                                if production_vertical[row_id] != x_vertical[row_id]],
                "production_counts": dict(__import__("collections").Counter(production.values())),
                "x_order_counts": dict(__import__("collections").Counter(x_order.values())),
            }
    return result


def run() -> dict[str,Any]:
    acquisition,reproduction,oracle=_load_prior_and_verify()
    pages_out={}
    for page in PAGES:
        saved=acquisition["spineless"][str(page)]
        geometry=saved["geometry"]
        tokens=geometry["tokens"]
        page_oracle=dict(oracle["pages"][str(page)]); page_oracle["page"]=page
        rows=_row_oracle_tokens(tokens,page_oracle)
        # The pixel bands and frozen identities are explicit and fully retained.
        for row in rows:
            row["tokens"]=[{"source_row":t["source_row"],"x0":t["x"],"x1":t["x"]+t["width"],
                            "y0":t["y"],"y1":t["y"]+t["height"],"width":t["width"],"height":t["height"],
                            "center_y":t["y"]+t["height"]/2,"production_order_rank":None}
                           for t in tokens if t["source_row"] in row["source_rows"]]
        token_by_source={t["source_row"]:t for t in tokens}
        anchor_orders={anchor:{t["source_row"]:rank for rank,t in enumerate(
            sorted(tokens,key=lambda t:(_anchor(t,anchor),t["x"],t["source_row"])),1)}
            for anchor in ("center_y","y1")}
        x_order={t["source_row"]:rank for rank,t in enumerate(sorted(tokens,key=lambda t:(t["x"],t["source_row"])),1)}
        for row in rows:
            for token_record in row["tokens"]:
                token_record["production_order_rank_center_y"]=anchor_orders["center_y"][token_record["source_row"]]
                token_record["production_order_rank_y1"]=anchor_orders["y1"][token_record["source_row"]]
                token_record["physical_x_order_rank"]=x_order[token_record["source_row"]]
        row_metrics=[]
        for row in rows:
            row_tokens=[token_by_source[s] for s in row["source_rows"]]
            row_metrics.append({"row_id":row["row_id"],"pixel_region":row["pixel_region"],"token_count":len(row_tokens),
                                "source_rows":row["source_rows"],"ordinary_prose":True,
                                "height_px":{"min":min(t["height"] for t in row_tokens),"max":max(t["height"] for t in row_tokens),
                                             "median":statistics.median(t["height"] for t in row_tokens),
                                             "range":max(t["height"] for t in row_tokens)-min(t["height"] for t in row_tokens)},
                                "observables":{"center_y":_dispersion([_anchor(t,"center_y") for t in row_tokens]),
                                               "y1":_dispersion([_anchor(t,"y1") for t in row_tokens])}})
        variants={}
        for anchor in ("center_y","y1"):
            variants[anchor]={}
            for order in ("production","x"):
                grouped=_full_grouping(tokens,anchor,order=order)
                final_classifications=_row_classification(rows,grouped)[0]
                vertical_grouping={"partitions":{f"v{index:04d}":sorted(band) for index,band in enumerate(grouped["vertical_bands"],1)}}
                variants[anchor][order]={"grouping":grouped,"row_classifications":final_classifications,
                                         "vertical_row_classifications":_row_classification(rows,vertical_grouping)[0]}
        expected=defaultdict(list)
        for token in tokens: expected[token["line_id"]].append(token["source_row"])
        expected_parts={line_id:sorted(sources) for line_id,sources in expected.items()}
        center_parts={line_id:sorted(sources) for line_id,sources in variants["center_y"]["production"]["grouping"]["partitions"].items() if sources}
        expected_nonempty={line_id:sources for line_id,sources in expected_parts.items() if sources}
        assert sorted(map(tuple,expected_nonempty.values()))==sorted(map(tuple,center_parts.values())),f"page {page} center shadow mismatch"
        if page in TARGETS:
            variants["target_trace"]={}
            for anchor in ("center_y","y1"):
                trace=_target_trace(tokens,anchor,TARGETS[page])
                source=TARGETS[page]
                grouping=variants[anchor]["production"]["grouping"]
                trace["target_box"]={"x0":token_by_source[source]["x"],"x1":token_by_source[source]["x"]+token_by_source[source]["width"],
                                     "y0":token_by_source[source]["y"],"y1":token_by_source[source]["y"]+token_by_source[source]["height"],
                                     "width":token_by_source[source]["width"],"height":token_by_source[source]["height"]}
                trace["resulting_vertical_bands"]=[sorted(group) for group in grouping["vertical_bands"] if source in group]
                trace["resulting_horizontal_regions"]=[sorted(group) for group in grouping["vertical_regions"] if source in group]
                trace["resulting_candidate_line_ids"]=grouping["candidate_line_ids"][source]
                trace["resulting_assigned_lines"]=[sorted(group) for group in grouping["partitions"].values() if source in group]
                variants["target_trace"][anchor]=trace
        variants["sensitivity"]={anchor:_sensitivity(tokens,anchor,variants[anchor]["production"]["grouping"],rows,TARGETS.get(page)) for anchor in ("center_y","y1")}
        for anchor in ("center_y","y1"):
            grouping=variants[anchor]["production"]["grouping"]
            grouping["summary"]={"selected_slope_px_per_px":geometry["measurements"]["baseline_slope_px_per_px"],
                                 "vertical_tolerance_px":4,"horizontal_gap_limit_px":grouping["gap_limit"],
                                 "vertical_band_count":len(grouping["vertical_bands"]),
                                 "horizontal_region_count":len(grouping["vertical_regions"]),
                                 "ambiguous_count":sum(len(item["candidate_line_ids"])>1 for item in grouping["unresolved"]),
                                 "unassigned_count":sum(len(item["candidate_line_ids"])==0 for item in grouping["unresolved"]),
                                 "ambiguous_source_rows":[item["source_row"] for item in grouping["unresolved"] if len(item["candidate_line_ids"])>1],
                                 "unassigned_source_rows":[item["source_row"] for item in grouping["unresolved"] if not item["candidate_line_ids"]]}
        pages_out[str(page)]={"page":page,"fixture":saved["fixture_id"],"side":saved["side"],
                              "raster_sha256":saved["transform"]["final_rgb_sha256"],"tsv_sha256":saved["tsv_sha256"],
                              "token_count":len(tokens),"oracle_row_count":len(rows),"oracle_token_count":sum(len(r["source_rows"]) for r in rows),
                              "pixel_oracle_rows":rows,"row_metrics":row_metrics,
                              "adjacent_row_metrics":_neighbor_metrics(rows,token_by_source),
                              "variants":variants,"production_expected_membership_reproduced":True,
                              "excluded_pixel_regions":page_oracle["excluded_regions"]}
    aggregate=_aggregate_metrics(pages_out)
    transitions={page:_row_transition_ledger(record) for page,record in pages_out.items()}
    final_counts={anchor:{order:_classification_counts(pages_out,anchor,order,"final") for order in ("production","x")}
                  | {"vertical_bands_production":_classification_counts(pages_out,anchor,"production","vertical")}
                  for anchor in ("center_y","y1")}
    result={"schema":"spineless-vertical-anchor-comparison-v1","prior_observation_source":"research/geometry/spineless-acquisition-ablation/results.json",
            "ocr_rerun":False,"all_variants_reuse_frozen_tokens":True,"production_tolerance_px":4,
            "primary_order":"anchor coordinate, x, source row; matches production ordering with only anchor swapped",
            "diagnostic_order":"physical x, source row","within_row_aggregate":aggregate,
            "neighbor_separation_summary":_neighbor_summary(pages_out),"row_classification_counts":final_counts,
            "row_transition_ledger":transitions,"processing_order_sensitivity":_order_sensitivity(pages_out),
            "synthetic_controls":_synthetic_controls(),"pages":pages_out}
    OUTPUT_PATH.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
    return result


if __name__=="__main__":
    data=run()
    for page,record in data["pages"].items():
        print(page,record["token_count"],record["oracle_row_count"],record["oracle_token_count"],
              {anchor:record["variants"][anchor]["production"]["row_classifications"] for anchor in ("center_y","y1")})
