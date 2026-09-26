"""Render the human-readable report from the recorded experiment outputs."""
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
manifest = json.loads((ROOT / "manifest.json").read_text())
results = json.loads((ROOT / "results.json").read_text())
pages = results["pages"]
nonblank = [page for page in pages if not page["declared_blank_side"]]
events = [(page, event) for page in pages for event in page["changed_groupings"]]
classes = Counter(event["adjudication"] for _, event in events)
all_oversized = [token for page in pages for token in page["clean_crop_baseline"]["guard_triggering_tokens"]]
nonblank_oversized = [token for page in nonblank for token in page["clean_crop_baseline"]["guard_triggering_tokens"]]
effects = [token for token in nonblank_oversized if token["classification_changes_horizontal_partition"] is True]
outside = sum(len(page["old_source_tokens_outside_crop"]) for page in pages)
flagged = [page for page in pages if (page["fixture_id"], page["side"]) in {
    ("relativity_pdf10_pp26-27", "left"), ("relativity_pdf17_pp40-41", "right"),
    ("relativity_pdf23_pp52-53", "left"), ("relativity_pdf23_pp52-53", "right")
}]
flagged_boxes = sum(len(page["old_source_tokens_outside_crop"]) for page in flagged)
flagged_lines = sum(len(page["old_physical_lines_composed_only_of_outside_tokens"]) for page in flagged)
flagged_absent = sum(page["old_outside_crop_token_labels_absent_from_new_tsv"] for page in flagged)
visible_mismatch = sum(len(page["old_token_text_locators_unmatched_but_pixel_visible"]) for page in pages)
old_nonblank = sum(page["old_uncropped_admitted_token_count"] for page in nonblank)
new_nonblank = sum(page["admitted_token_count"] for page in nonblank)
on_lines = sum(page["clean_crop_baseline"]["physical_line_count"] for page in pages)
off_lines = sum(page["guard_off"]["physical_line_count"] for page in pages)
nb_on_lines = sum(page["clean_crop_baseline"]["physical_line_count"] for page in nonblank)
nb_off_lines = sum(page["guard_off"]["physical_line_count"] for page in nonblank)
amb_on = sum(page["clean_crop_baseline"]["ambiguous_token_count"] for page in nonblank)
un_on = sum(page["clean_crop_baseline"]["unassigned_token_count"] for page in nonblank)
amb_off = sum(page["guard_off"]["ambiguous_token_count"] for page in nonblank)
un_off = sum(page["guard_off"]["unassigned_token_count"] for page in nonblank)
rows = [
    "# Manual-crop oversized-guard ablation", "",
    "## A. Crop inventory", "",
    "The 12 user files are one-page PDF crop wrappers, six left/right pairs. Each embeds the identical original fixture-page JPEG (2550×3300, DeviceRGB) and applies a CropBox plus a 90° PDF page rotation. Mapping was verified by comparing embedded-image bytes with each fixture PDF and checking CropBox location against the fixture spread split. The PDFs are not accepted by the current Tesseract image path, so each was rendered to RGB PNG at the embedded scan's native 300 dpi. This reproduces the PDF crop and orientation only; there is no added scale, deskew, threshold, denoise, sharpening, or contrast operation. Original crop files were read-only inputs.",
    "", "| Crop PDF | Fixture / side | Format; derived pixels / mode | Original SHA-256 | Derived SHA-256 |", "|---|---|---|---|---|"]
for crop in manifest["crops"]:
    rows.append(f"| `{Path(crop['original_path']).name}` | `{crop['fixture_id']}` / {crop['side']} | PDF → {crop['derived_width_px']}×{crop['derived_height_px']} RGB | `{crop['original_sha256']}` | `{crop['derived_sha256']}` |")
rows += ["", f"Tesseract: **{manifest['ocr']['version'].splitlines()[0]}**, `eng --psm 6`, TSV. No crop was routed through Slice 1 spread rendering or splitting.",
"", "## B. Clean-crop baseline", "",
"`On → off` is the physical-line count under current production behavior and with only the oversized predicate disabled. Ambiguous/unassigned counts are from guard-on. All coordinates and widths are crop-local. The threshold is exactly production's `gap_limit + gap_limit / 2`; slope is the unchanged production-selected slope.",
"", "| Fixture / side | Tokens | Lines on → off | Ambiguous / unassigned | Median width | Gap | Threshold | Oversized | Individually changes split partition | Slope |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
for page in pages:
    b = page["clean_crop_baseline"]
    effect_count = sum(item["classification_changes_horizontal_partition"] is True for item in b["guard_triggering_tokens"])
    label = " (declared blank)" if page["declared_blank_side"] else ""
    effect_value = "n/a (blank OCR)" if page["declared_blank_side"] else str(effect_count)
    rows.append(f"| `{page['fixture_id']}` / {page['side']}{label} | {page['admitted_token_count']} | {b['physical_line_count']} → {page['guard_off']['physical_line_count']} | {b['ambiguous_token_count']} / {b['unassigned_token_count']} | {b['median_token_width_px']:.1f} | {b['horizontal_gap_limit_px']:.1f} | {b['oversized_threshold_px']:.1f} | {b['guard_triggering_token_count']} | {effect_value} | {b['selected_baseline_slope']:.3f} |")
blank = next(page for page in pages if page["declared_blank_side"])
rows += ["", f"Across all 12 crops, {sum(p['admitted_token_count'] for p in pages):,} tokens yielded {on_lines} guard-on lines and {off_lines} guard-off lines. The declared blank Stella Maris 03 left side alone contributed {blank['admitted_token_count']} admitted boxes and {blank['clean_crop_baseline']['physical_line_count']} lines from a near-white crop. For the 11 nonblank sides, totals were {new_nonblank} tokens and {nb_on_lines} → {nb_off_lines} lines. Nonblank ambiguous/unassigned counts were {amb_on}/{un_on} guard-on and {amb_off}/{un_off} guard-off. The blank-side OCR detections are not content-quality evidence.",
"", "Guard-on calls delegate to production `parse_tsv_rows` and `group_physical_lines`; each guard-on result was checked against a second direct production call. Guard-off temporarily replaces only `_is_oversized` with `False`, then restores it in `finally`. Byte-exact Tesseract TSVs are saved as deterministic gzip files (uncompressed SHA-256 is recorded); this preserves the empty trailing TSV columns. Admitted token inventories, guard-on/off geometry JSON, and whole-page overlays are saved beside this report.",
"", "## C. Edge-noise effect", "",
 f"Mapping old source-side OCR boxes through the exact manual CropBoxes finds {outside} old boxes wholly outside the crops. These are concentrated in edge/gutter regions and consist of bars, punctuation, and tiny isolated marks; no full prose token box lies wholly outside. On the four previously flagged Relativity sides, {flagged_boxes} such boxes occupy {flagged_lines} old physical lines consisting only of outside-crop tokens; {flagged_absent} corresponding OCR labels do not appear in the new crop TSV. Other outside-crop marks occur at page margins on remaining sides. This establishes the effect of these user crops only; it does not establish an automatic crop method.",
 f"The 11 nonblank old geometry pages contain {old_nonblank} admitted tokens; the crops produce {new_nonblank}. Exact case-folded token text occurrences overlap {sum(p['old_text_occurrence_alignment_count'] for p in nonblank)} times. A further {visible_mismatch} old text locators do not recur exactly, although their mapped source boxes still contain dark pixels in the crop. This is evidence of changed OCR segmentation/recognition, not proof that visible wording was lost. No old body-text box was wholly outside a crop; full pixel-location details are in `results.json`.",
 "", "## D. Guard differential", "",
 f"Current grouping classifies {len(all_oversized)} boxes as oversized (including {len(all_oversized)-len(nonblank_oversized)} OCR boxes on the declared blank page). The one-token-at-a-time production splitter trace finds {len(effects)} nonblank oversized classifications whose special extent handling changes the horizontal partition. The aggregate guard-on/off comparison has {len(events)} connected changed-grouping events: **{classes['repaired_false_split']} repaired false splits**, {classes['benign_difference']} benign differences on the declared blank side, zero destructive merges, and zero unresolved events by the pixel criterion below.",
 "", "For every nonblank changed event, all affected token boxes contain dark pixels (grayscale <160); the pixel-weighted ink centroids fit a single horizontal or slanted baseline with maximum residual at most 7.81 px. Guard-off restores their shared line membership. This adjudication uses source pixels and box locations, not OCR wording or reduced line count. No changed event combines ink from distinct visible baselines. The one-token counts and exact `_is_oversized` / `_supported_bridge_ids` / covered-extent trace for every trigger are in `results.json`.",
 "", "### Complete changed-grouping enumeration", "",
 "Each row identifies the affected tokens and line-member sets in both states. Small cropped diagnostic overlays are linked from each row.",
 "", "| Page side | Event | Affected token IDs | Guard-on groups | Guard-off groups | Adjudication | Ink-fit max residual px | Diagnostic |", "|---|---|---|---|---|---|---:|---|"]
for page, event in events:
    on = "; ".join(",".join(group) for group in event["guard_on_groups"])
    off = "; ".join(",".join(group) for group in event["guard_off_groups"])
    residual = event["pixel_baseline_evidence"]["max_centroid_residual_px"]
    residual_s = "n/a" if residual is None else f"{residual:.2f}"
    rows.append(f"| `{page['fixture_id']}` / {page['side']} | `{event['event_id']}` | {', '.join(event['token_ids'])} | {on} | {off} | {event['adjudication']} | {residual_s} | `{Path(event['diagnostic_overlay']).name}` |")
rows += ["", "All 243 oversized-token inventory entries are in `results.json`, including source row, OCR locator, bbox/width, threshold, bridge support, whether extent was applied, next-box actual gap, stale covered gap, and a per-token production splitter toggle. Tokens are not assigned semantic object classes based on width.",
"", "## E. Known examples and adversarial content", "",
"| OCR locator / page | Cropped guard-on trace | Guard-off result | Pixel evidence |", "|---|---|---|---|"]
# Report requested examples from exact token records.
for fixture, side, locator in [
    ("relativity_pdf17_pp40-41", "right", "conclusion"),
    ("relativity_pdf17_pp40-41", "left", "embankment.”"),
    ("relativity_pdf17_pp40-41", "right", "embankment,"),
    ("relativity_pdf17_pp40-41", "right", "reference-body"),
]:
    page = next(p for p in pages if p["fixture_id"] == fixture and p["side"] == side)
    geometry = json.loads((REPO / page["token_inventory_path"]).read_text())
    token = next(t for t in geometry["tokens"] if t["text"] == locator)
    trace = next((item for item in page["clean_crop_baseline"]["guard_triggering_tokens"] if item["token_id"] == token["token_id"]), None)
    event = next((e for e in page["changed_groupings"] if token["token_id"] in e["token_ids"]), None)
    box = f"{token['width_px']}×{token['height_px']} px, bbox [{token['x_px']},{token['y_px']},{token['right_px']},{token['bottom_px']}]"
    if trace is None:
        guard = f"not oversized (threshold {page['clean_crop_baseline']['oversized_threshold_px']:.1f} px)"
        outcome = "No guard-caused split; token is assigned on guard-on."
    else:
        actual = trace["following_gap_trace"][0]["actual_gap_after_box_px"] if trace["following_gap_trace"] else "n/a"
        stale = trace["following_gap_trace"][0]["guard_on_covered_gap_px"] if trace["following_gap_trace"] else "n/a"
        guard = f"oversized; threshold {page['clean_crop_baseline']['oversized_threshold_px']:.1f}px; supported={trace['supported_bridge']}; next actual gap {actual}px, stale covered gap {stale}px"
        outcome = f"{event['adjudication'] if event else 'no changed event'}"
    evidence = "No changed pixel relationship." if event is None else f"ink-fit residual {event['pixel_baseline_evidence']['max_centroid_residual_px']:.2f}px."
    rows.append(f"| `{fixture}` / {side} `{locator}` | {box}; {guard} | {outcome} | {evidence} |")
rows += ["", "The Relativity 10 left heading row (`The Principle of Relativity`) is one of the repaired false splits; all four boxes fit a single ink baseline. On the manual `conclusion` crop, the box is 198 px and the threshold is 210 px, so it is not classified oversized and the earlier uncropped split does not recur under this crop's OCR statistics. The `reference-body` box is 279 px against a 210 px threshold; its unsupported extent makes the next 18 px actual gap appear as a 317 px covered gap. Guard-off restores the same pixel-supported baseline. Repeated `embankment` boxes also trigger guard-caused splits; for example, the left-page 272 px box has a 25 px next-box gap and produces a 322 px stale covered gap. Relativity 23 right has an oversized `theory` box (322 px against a 201 px threshold) whose visible ink spans the boxes before and after it; the `the`–`of` gap is 155 px, above the 134 px page limit, yet all changed token ink fits one baseline with 1.72 px maximum residual. The guard leaves `of` split off; guard-off rejoins it. Relativity 23 left changed rows include the `x'-axis` and `x' = 0` locators; their box ink fits a single baseline after joining. Equation-variable and equal-sign boxes elsewhere do not trigger the guard. OCR strings are locators only.",
"", "## F. Guard necessity", "",
"On these 11 nonblank manually cropped pages, **no destructive guard-off merge was observed**. The guard-off run repairs 44 pixel-supported false splits, and 46 individual nonblank oversized classifications change a horizontal partition. The evidence for this crop corpus is that the current width-based special case mostly creates fragmentation once the user-selected edge strips are removed; it did not protect distinct visible baselines here. This supports a separate production trial to remove the special case, limited to the observed corpus and this Tesseract run. It does not establish that no other document can benefit from a guard.",
"", "## G. Residual and downstream observations", "",
 f"On nonblank pages, line count falls from {nb_on_lines} to {nb_off_lines}; this is secondary to the pixel adjudication. Ambiguous/unassigned token counts change from {amb_on}/{un_on} to {amb_off}/{un_off}. All selected slopes remain 0. The seven historical residual strings appear somewhere in their corresponding crop OCR outputs, but crop-local OCR identities cannot be equated with historical token IDs (several strings repeat). The crop assignments therefore do not establish correct resolution of any historical residual. Stella Maris missing-line behavior was not investigated.",
 "", "## H. Recommendation boundary", "",
 "The evidence warrants a separate production task to trial removing the oversized-token special case. This task provides no evidence warranting a replacement width threshold or a narrower protection; no destructive merge was found in the nonblank crops. No production geometry or preprocessing change is included.",
 "", "## I. Verification", "",
 "- Focused tests: six research tests; result recorded in final report.",
 "- Full repository suite: result recorded in final report.",
 "- Original crop hashes: checked against the initial inventory and manifest.",
 "- Production files and historical review data: unchanged.",
 "- `git diff --check`, commit SHA, and final worktree: recorded after verification.", ""]
(ROOT / "report.md").write_text("\n".join(rows), encoding="utf-8")
print(f"wrote {len(rows)} report lines; {len(events)} grouping events; {dict(classes)}")
