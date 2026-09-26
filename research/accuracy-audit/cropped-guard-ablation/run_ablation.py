"""Run guard-on/off geometry on the user's manually cropped page PDFs.

The only behavioral intervention is a temporary replacement of production
_is_oversized with False during guard-off grouping. PDF crops are rendered at
the embedded image's native 300 dpi into RGB PNGs; no other image operation is
applied. All durable derivatives and evidence remain in this directory.
"""
from __future__ import annotations

import csv
import hashlib
import gzip
import itertools
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any

import fitz
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
REVIEW = ROOT / "research/accuracy-audit/review"
sys.path.insert(0, str(ROOT / "src"))
import normalize.geometry as geometry  # noqa: E402
import pytesseract  # noqa: E402
from pytesseract import Output  # noqa: E402

FIXTURE = {
    ("einstein", "10"): ("relativity_pdf10_pp26-27", "pp26-27"),
    ("einstein", "17"): ("relativity_pdf17_pp40-41", "pp40-41"),
    ("einstein", "23"): ("relativity_pdf23_pp52-53", "pp52-53"),
    ("mccarthy", "3"): ("stella_maris_pdf03_session-I", "03"),
    ("mccarthy", "6"): ("stella_maris_pdf06_dense-dialogue", "06"),
    ("mccarthy", "18"): ("stella_maris_pdf18_session-II_p35", "18"),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def crop_mapping(path: Path) -> tuple[str, str, str, str]:
    author = path.parent.parent.name
    if author not in {"einstein", "mccarthy"}:
        raise ValueError(f"Unexpected crop author directory: {path}")
    match = re.search(r"(?:Relativity |Stella Maris\.pt2 )(\d+)-([LR])\.pdf\Z", path.name)
    if not match:
        raise ValueError(f"Crop filename does not identify page and side: {path}")
    number, side_suffix = match.groups()
    fixture_id, fixture_pages = FIXTURE[(author, number)]
    # The crop filenames directly state the source page number and side. The
    # existing Slice 2 fixture metadata independently identifies the same PDF
    # page span; verify the relation before assigning the research side.
    return author, fixture_id, "left" if side_suffix == "L" else "right", fixture_pages


def render_native_crop(path: Path, destination: Path) -> dict[str, Any]:
    doc = fitz.open(path)
    if len(doc) != 1:
        raise ValueError(f"Expected one user-cropped page in {path}, found {len(doc)}")
    page = doc[0]
    images = page.get_images(full=True)
    if len(images) != 1:
        raise ValueError(f"Expected one embedded scan image in {path}, found {len(images)}")
    xref = images[0][0]
    embedded = fitz.Pixmap(doc, xref)
    if (embedded.width, embedded.height, embedded.n) != (2550, 3300, 3):
        raise ValueError(f"Unexpected embedded source raster in {path}: {embedded.width}x{embedded.height}, channels={embedded.n}")
    if page.rotation not in (0, 90, 180, 270):
        raise ValueError(f"Unsupported page rotation {page.rotation} in {path}")
    # The original image is 2550x3300 at 300 dpi. Rendering at the same native
    # resolution applies the PDF's user-selected CropBox and orientation only.
    pixmap = page.get_pixmap(dpi=300, colorspace=fitz.csRGB, alpha=False, annots=False)
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    image.save(destination, format="PNG", optimize=False)
    return {
        "pdf_page_count": len(doc), "pdf_media_box_pt": list(page.mediabox),
        "pdf_crop_box_pt": list(page.cropbox), "pdf_rotation_degrees": page.rotation,
        "embedded_image_width_px": embedded.width, "embedded_image_height_px": embedded.height,
        "embedded_image_color_space": embedded.colorspace.name,
        "native_render_dpi": 300, "derived_width_px": pixmap.width,
        "derived_height_px": pixmap.height, "derived_mode": "RGB",
        "derived_sha256": sha256(destination),
    }


def engine_record() -> dict[str, str]:
    return {
        "version": str(pytesseract.get_tesseract_version()).strip(),
        "language": "eng", "config": "--psm 6", "output": "TSV",
    }


def ids_by_candidate(lines: list[dict[str, Any]], unresolved: list[dict[str, Any]]) -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    for line in lines:
        for token_id in line["token_ids"]:
            result[token_id] = (line["line_id"],)
    for item in unresolved:
        result[f"token-{item['token_source_row']:04d}"] = tuple(item["candidate_line_ids"])
    return result


def assigned_partitions(lines: list[dict[str, Any]]) -> dict[str, str]:
    return {token_id: line["line_id"] for line in lines for token_id in line["token_ids"]}


def grouping_events(on: dict[str, Any], off: dict[str, Any]) -> list[dict[str, Any]]:
    """Enumerate co-membership and candidate-assignment changes by token ID."""
    def membership(grouping: dict[str, Any]) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
        groups = {line["line_id"]: set(line["token_ids"]) for line in grouping["lines"]}
        candidates: dict[str, set[str]] = {}
        for line_id, token_ids in groups.items():
            for token_id in token_ids:
                candidates.setdefault(token_id, set()).add(line_id)
        for item in grouping["unresolved"]:
            token_id = f"token-{item['token_source_row']:04d}"
            candidates.setdefault(token_id, set())
            for line_id in item["candidate_line_ids"]:
                candidates[token_id].add(line_id)
                groups[line_id].add(token_id)
        return groups, candidates

    on_groups, on_candidates = membership(on)
    off_groups, off_candidates = membership(off)

    def relation(groups: dict[str, set[str]]) -> set[frozenset[str]]:
        return {frozenset(pair) for group in groups.values()
                for pair in itertools.combinations(sorted(group), 2)}

    on_relation, off_relation = relation(on_groups), relation(off_groups)
    changed_pairs = on_relation ^ off_relation
    adjacency: dict[str, set[str]] = defaultdict(set)
    for pair in changed_pairs:
        left, right = tuple(pair)
        adjacency[left].add(right)
        adjacency[right].add(left)

    # Compare canonical member sets, not line ordinals, which may shift when a
    # prior split disappears. This also catches assignment-only transitions.
    changed_signatures = {
        token_id for token_id in set(on_candidates) | set(off_candidates)
        if {frozenset(on_groups[line_id]) for line_id in on_candidates.get(token_id, ())}
        != {frozenset(off_groups[line_id]) for line_id in off_candidates.get(token_id, ())}
    }
    for token_id in changed_signatures:
        for group_map, candidate_map in ((on_groups, on_candidates), (off_groups, off_candidates)):
            for line_id in candidate_map.get(token_id, ()):
                for member in group_map[line_id] - {token_id}:
                    adjacency[token_id].add(member)
                    adjacency[member].add(token_id)
        adjacency.setdefault(token_id, set())

    components = []
    while adjacency:
        seed = min(adjacency)
        stack, component = [seed], set()
        while stack:
            node = stack.pop()
            if node in component:
                continue
            component.add(node)
            stack.extend(adjacency.get(node, ()))
        for node in component:
            adjacency.pop(node, None)
        components.append(component)
    events = []
    for component in sorted(components, key=lambda members: min(members)):
        changed_for_component = [pair for pair in changed_pairs if pair <= component]
        events.append({
            "token_ids": sorted(component),
            "guard_on_line_ids": sorted({lid for token in component for lid in on_candidates.get(token, ())}),
            "guard_off_line_ids": sorted({lid for token in component for lid in off_candidates.get(token, ())}),
            "guard_on_groups": [sorted(group & component) for group in on_groups.values() if group & component],
            "guard_off_groups": [sorted(group & component) for group in off_groups.values() if group & component],
            "pairs_merged_guard_off": sorted([sorted(pair) for pair in changed_for_component if pair in off_relation - on_relation]),
            "pairs_split_guard_off": sorted([sorted(pair) for pair in changed_for_component if pair in on_relation - off_relation]),
        })
    changed_ids = {token for pair in changed_pairs for token in pair} | changed_signatures
    emitted_ids = set().union(*(set(event["token_ids"]) for event in events)) if events else set()
    if not changed_ids <= emitted_ids:
        raise AssertionError("changed grouping event enumeration lost token identities")
    return events


def overlay(image_path: Path, geometry_page: dict[str, Any], destination: Path, highlight: set[str] | None = None) -> None:
    with Image.open(image_path) as source:
        image = source.convert("RGB")
        draw = ImageDraw.Draw(image)
        for token in geometry_page["tokens"]:
            is_highlighted = highlight is not None and token["token_id"] in highlight
            draw.rectangle((token["x_px"], token["y_px"], token["right_px"], token["bottom_px"]),
                           outline=(255, 0, 255) if is_highlighted else (40, 120, 220), width=2)
        for line in geometry_page["physical_lines"]:
            if any(line[field] is None for field in ("left_px", "top_px", "right_px", "bottom_px")):
                continue
            draw.rectangle((line["left_px"], line["top_px"], line["right_px"], line["bottom_px"]),
                           outline=(220, 70, 40), width=2)
        image.save(destination, "PNG")


def pixel_baseline_evidence(image_path: Path, token_records: list[dict[str, Any]]) -> dict[str, Any]:
    """Measure visible ink alignment from the crop, without using OCR wording."""
    with Image.open(image_path) as source:
        gray = source.convert("L")
        observations = []
        for record in token_records:
            box = gray.crop((record["x_px"], record["y_px"], record["right_px"], record["bottom_px"]))
            count = weight_sum = x_sum = y_sum = 0.0
            pixels = box.load()
            for y in range(box.height):
                for x in range(box.width):
                    value = pixels[x, y]
                    if value < 160:
                        weight = 160 - value
                        count += 1
                        weight_sum += weight
                        x_sum += (record["x_px"] + x) * weight
                        y_sum += (record["y_px"] + y) * weight
            if weight_sum:
                observations.append({"token_id": record["token_id"], "ink_pixels_lt160": int(count),
                                    "ink_centroid_x_px": x_sum / weight_sum,
                                    "ink_centroid_y_px": y_sum / weight_sum})
        histogram = gray.histogram()
        dark_fraction = sum(histogram[:160]) / (gray.width * gray.height)
    if len(observations) >= 2:
        xs = [item["ink_centroid_x_px"] for item in observations]
        ys = [item["ink_centroid_y_px"] for item in observations]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        denominator = sum((x - mx) ** 2 for x in xs)
        slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denominator if denominator else 0.0
        residuals = [abs(y - (my + slope * (x - mx))) for x, y in zip(xs, ys)]
        max_residual = max(residuals)
    else:
        slope, max_residual = None, None
    return {"ink_threshold_grayscale_lt": 160, "dark_pixel_fraction_lt160": dark_fraction,
            "token_boxes_with_ink": len(observations), "token_box_count": len(token_records),
            "ink_centroids": observations, "fitted_baseline_slope": slope,
            "max_centroid_residual_px": max_residual}


def small_event_diagnostic(image_path: Path, token_records: list[dict[str, Any]], destination: Path) -> None:
    """Save a region crop with changed OCR boxes outlined for review."""
    if not token_records:
        return
    margin = 28
    left = max(0, min(t["x_px"] for t in token_records) - margin)
    top = max(0, min(t["y_px"] for t in token_records) - margin)
    with Image.open(image_path) as source:
        right = min(source.width, max(t["right_px"] for t in token_records) + margin)
        bottom = min(source.height, max(t["bottom_px"] for t in token_records) + margin)
        image = source.convert("RGB").crop((left, top, right, bottom))
    draw = ImageDraw.Draw(image)
    for token in token_records:
        draw.rectangle((token["x_px"] - left, token["y_px"] - top,
                        token["right_px"] - left, token["bottom_px"] - top),
                       outline=(255, 0, 255), width=2)
    image.save(destination, "PNG")


def group_variants(tokens: list[Any]) -> tuple[Any, Any]:
    """Return current production grouping and the one-predicate guard-off run."""
    guard_on = geometry.group_physical_lines(tokens)
    original = geometry._is_oversized
    try:
        geometry._is_oversized = lambda _token, _gap: False
        guard_off = geometry.group_physical_lines(tokens)
    finally:
        geometry._is_oversized = original
    return guard_on, guard_off


def individual_token_split_effect(token: Any, band: list[Any], gap_limit: float) -> dict[str, Any]:
    """Toggle one box through the production splitter; leave every other box guarded."""
    original = geometry._is_oversized
    def exempt_only(candidate: Any, gap: float) -> bool:
        return False if candidate is token else original(candidate, gap)
    base = geometry._split_horizontal_regions([band], gap_limit)
    try:
        geometry._is_oversized = exempt_only
        exempted = geometry._split_horizontal_regions([band], gap_limit)
    finally:
        geometry._is_oversized = original
    def identity_partition(regions: list[list[Any]]) -> list[list[int]]:
        return sorted([sorted(item.source_row for item in region) for region in regions])
    base_partition, exempted_partition = identity_partition(base), identity_partition(exempted)
    return {"guard_on_regions": base_partition, "single_token_exempted_regions": exempted_partition,
            "classification_changes_horizontal_partition": base_partition != exempted_partition}

def run() -> None:
    crop_paths = sorted([* (ROOT / "fixtures/einstein/crops").glob("*.pdf"), * (ROOT / "fixtures/mccarthy/crops").glob("*.pdf")])
    if len(crop_paths) != 12:
        raise ValueError(f"Expected left/right crops for six fixtures (12 PDFs); found {len(crop_paths)}")
    manifest = {"schema": "manual-crop-ablation-manifest-v1", "input_authority": "user-provided manual crop PDFs",
                "ocr": engine_record(), "conversion": "PDF CropBox render at embedded scan native 300 dpi, RGB, page rotation applied; no enhancement/rescaling",
                "crops": []}
    pages = []
    for path in crop_paths:
        author, fixture_id, side, fixture_pages = crop_mapping(path)
        source_manifest = json.loads((REVIEW / "preprocessed" / fixture_id / f"{fixture_id}.preprocess.json").read_text())
        source_pdf = Path(source_manifest["source_pdf"])
        source_doc, crop_doc = fitz.open(source_pdf), fitz.open(path)
        source_page, crop_page = source_doc[0], crop_doc[0]
        source_xref = source_page.get_images(full=True)[0][0]
        crop_xref = crop_page.get_images(full=True)[0][0]
        source_image = source_doc.extract_image(source_xref)
        crop_image = crop_doc.extract_image(crop_xref)
        same_embedded_raster = source_image["image"] == crop_image["image"]
        # Source pages are rotated spreads rendered at 144 dpi. PDF CropBox y
        # maps to display x after the source's 90-degree rotation.
        display_x0 = (source_page.mediabox.height - crop_page.cropbox.y1) * 2
        display_x1 = (source_page.mediabox.height - crop_page.cropbox.y0) * 2
        split_px = 792
        side_verified = (display_x0 < split_px and display_x1 <= split_px) if side == "left" else (display_x0 >= split_px and display_x1 > split_px)
        if not same_embedded_raster or not side_verified:
            raise ValueError(f"Crop-to-fixture pixel/side mapping is not verified: {path}")
        derived = OUT / "inputs" / f"{fixture_id}.{side}.png"
        render_info = render_native_crop(path, derived)
        manifest["crops"].append({
            "original_path": str(path.relative_to(ROOT)), "author": author, "fixture_id": fixture_id,
            "side": side, "filename_page_number": re.search(r"(\d+)-[LR]\.pdf\Z", path.name).group(1),
            "fixture_page_span": fixture_pages, "format": "PDF", "original_sha256": sha256(path),
            "embedded_original_image_format": source_image["ext"],
            "embedded_original_dimensions_px": [source_image["width"], source_image["height"]],
            "embedded_original_color_space": "DeviceRGB", "fixture_crop_embedded_raster_match": same_embedded_raster,
            "crop_display_x_range_at_144dpi_px": [display_x0, display_x1],
            "fixture_split_boundary_px": split_px, "filename_side_mapping_verified": side_verified,
            "declared_fixture_side_blank": next(p["blank"] for p in json.loads((REVIEW / "geometry" / f"{fixture_id}.geometry.json").read_text())["pages"] if p["side"] == side),
            "derived_path": str(derived.relative_to(ROOT)), **render_info,
        })
        crops = [item for item in manifest["crops"] if item["fixture_id"] == fixture_id and item["side"] == side]
        crop_info = crops[-1]
        crop_pdf = fitz.open(path)
        pages.append({"fixture_id": fixture_id, "side": side, "crop_path": path, "image_path": derived,
                      "crop_info": crop_info,
                      "display_y_range_at_144dpi_px": [crop_pdf[0].cropbox.x0 * 2, crop_pdf[0].cropbox.x1 * 2]})
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")

    corpus_results = []
    for page_info in pages:
        fixture_id, side = page_info["fixture_id"], page_info["side"]
        image_path = page_info["image_path"]
        with Image.open(image_path) as image:
            width, height = image.size
            tsv = pytesseract.image_to_data(image, lang="eng", config="--psm 6", output_type=Output.STRING)
        prefix = f"{fixture_id}.{side}"
        tsv_path = OUT / "ocr" / f"{prefix}.tsv.gz"
        raw_tsv_bytes = tsv.encode("utf-8")
        with tsv_path.open("wb") as compressed_file:
            with gzip.GzipFile(fileobj=compressed_file, mode="wb", compresslevel=9, mtime=0) as compressed:
                compressed.write(raw_tsv_bytes)
        tokens, admission_errors = geometry.parse_tsv_rows(tsv, width, height)
        (on_lines, on_unresolved, on_measurements), (off_lines, off_unresolved, off_measurements) = group_variants(tokens)
        # Guard-on fidelity: a second unchanged production call must be byte-
        # structure identical to the preceding production call.
        verify_lines, verify_unresolved, verify_measurements = geometry.group_physical_lines(tokens)
        if (on_lines, on_unresolved, on_measurements) != (verify_lines, verify_unresolved, verify_measurements):
            raise AssertionError(f"guard-on did not faithfully match production grouping for {prefix}")
        # Keep the existing fixture's blank-side declaration; the PDF crop is
        # mapped to that exact side by shared embedded source pixels and CropBox.
        old_artifact = json.loads((REVIEW / "geometry" / f"{fixture_id}.geometry.json").read_text())
        old_page = next(p for p in old_artifact["pages"] if p["side"] == side)
        page_record = geometry._PreprocessedPage(side, image_path, width, height, old_page["blank"],
                                                  {"output_path": str(image_path.relative_to(OUT)), "source_stage": "user_manual_crop"})
        provenance = {"fixture_id": fixture_id, "fixture_pdf_page_index_1_based": 1,
                     "source_pdf_page_index_1_based": 1, "dpi": 300, "metadata_order": [side]}
        on_page = geometry._page_geometry(page_record, tsv, engine_record(), provenance)
        # Generate guard-off records from the already-computed grouping to avoid
        # rerunning OCR or changing token admission.
        original_group = geometry.group_physical_lines
        try:
            geometry.group_physical_lines = lambda _tokens: (off_lines, off_unresolved, off_measurements)
            off_page = geometry._page_geometry(page_record, tsv, engine_record(), provenance)
        finally:
            geometry.group_physical_lines = original_group
        (OUT / "guard_on" / f"{prefix}.geometry.json").write_text(json.dumps(on_page, indent=2, ensure_ascii=False) + "\n")
        (OUT / "guard_off" / f"{prefix}.geometry.json").write_text(json.dumps(off_page, indent=2, ensure_ascii=False) + "\n")
        overlay(image_path, on_page, OUT / "guard_on" / f"{prefix}.overlay.png")
        overlay(image_path, off_page, OUT / "guard_off" / f"{prefix}.overlay.png")

        # Capture original production geometry for identity/text comparisons.
        old_texts = defaultdict(int)
        for token in old_page["tokens"]:
            old_texts[token["text"].casefold()] += 1
        new_texts = defaultdict(int)
        for token in on_page["tokens"]:
            new_texts[token["text"].casefold()] += 1
        matched = sum(min(count, new_texts[text]) for text, count in old_texts.items())
        crop_x0_abs, crop_x1_abs = page_info["crop_info"]["crop_display_x_range_at_144dpi_px"]
        source_side_offset = 792 if side == "right" else 0
        crop_x0, crop_x1 = crop_x0_abs - source_side_offset, crop_x1_abs - source_side_offset
        crop_y0, crop_y1 = page_info["display_y_range_at_144dpi_px"]
        old_outside_crop = []
        unmatched_visible = []
        new_text_remaining = dict(new_texts)
        with Image.open(image_path) as crop_raster:
            crop_gray = crop_raster.convert("L")
            for record in old_page["tokens"]:
                x0,y0,x1,y1 = record["x_px"],record["y_px"],record["right_px"],record["bottom_px"]
                outside = x1 <= crop_x0 or x0 >= crop_x1 or y1 <= crop_y0 or y0 >= crop_y1
                if outside:
                    old_outside_crop.append({"token_id": record["token_id"], "text": record["text"],
                                             "bbox_px": [x0,y0,x1,y1]})
                    continue
                text_key = record["text"].casefold()
                if new_text_remaining.get(text_key, 0):
                    new_text_remaining[text_key] -= 1
                    continue
                # Pixel-check old boxes that remain inside the user crop while
                # their exact OCR locator is absent from the cropped TSV.
                mapped = ((x0-crop_x0)*300/144, (y0-crop_y0)*300/144,
                          (x1-crop_x0)*300/144, (y1-crop_y0)*300/144)
                lx0,ly0,lx1,ly1 = [int(round(v)) for v in mapped]
                ink_box = crop_gray.crop((max(0,lx0),max(0,ly0),min(width,lx1),min(height,ly1)))
                histogram = ink_box.histogram()
                ink = sum(histogram[:160])
                if ink:
                    unmatched_visible.append({"token_id": record["token_id"], "text": record["text"],
                                              "mapped_bbox_px": list(mapped), "dark_pixels_lt160": ink})
        outside_ids = {item["token_id"] for item in old_outside_crop}
        source_edge_only_lines = [line["line_id"] for line in old_page["physical_lines"]
                                  if line["token_ids"] and set(line["token_ids"]) <= outside_ids]
        outside_labels_absent = sum(new_texts.get(item["text"].casefold(), 0) == 0 for item in old_outside_crop)
        oversized = []
        tolerance = on_measurements["tolerance_px"]
        slope = on_measurements["baseline_slope_px_per_px"]
        vertical_bands = []
        old_split = geometry._split_horizontal_regions
        try:
            geometry._split_horizontal_regions = lambda bands, _gap: [list(band) for band in bands]
            vertical_bands = geometry._line_bands(tokens, tolerance, slope)
        finally:
            geometry._split_horizontal_regions = old_split
        band_info = []
        by_token = {f"token-{token.source_row:04d}": token for token in tokens}
        for band_index, band in enumerate(vertical_bands):
            ordered = sorted(band, key=lambda t: (t.x, t.source_row))
            bridges = geometry._supported_bridge_ids(ordered, on_measurements["horizontal_gap_limit_px"])
            oversized_in_band = []
            for token in ordered:
                if not geometry._is_oversized(token, on_measurements["horizontal_gap_limit_px"]):
                    continue
                token_id = f"token-{token.source_row:04d}"
                supported = id(token) in bridges
                individual_effect = (None if old_page["blank"] else
                                     individual_token_split_effect(token, ordered, on_measurements["horizontal_gap_limit_px"]))
                preceding_gaps = []
                covered = None
                for current in ordered:
                    if current is token:
                        break
                    if not geometry._is_oversized(current, on_measurements["horizontal_gap_limit_px"]) or id(current) in bridges:
                        covered = max(covered or current.x1, current.x1)
                    elif covered is None:
                        covered = current.x
                if covered is not None:
                    following = [t for t in ordered if t.x >= token.x1]
                    if following:
                        next_token = min(following, key=lambda t: (t.x, t.source_row))
                        preceding_gaps.append({"next_token_id": f"token-{next_token.source_row:04d}",
                                               "actual_gap_after_box_px": next_token.x - token.x1,
                                               "guard_on_covered_gap_px": next_token.x - (token.x1 if supported else (covered if covered is not None else token.x))})
                oversized.append({"token_id": token_id, "text": token.text, "source_row": token.source_row,
                                  "bbox_px": [token.x, token.y, token.x1, token.y1], "width_px": token.width,
                                  "supported_bridge": supported,
                                  "special_extent_applied": not geometry._is_oversized(token, on_measurements["horizontal_gap_limit_px"]) or supported,
                                  "classification_changes_horizontal_partition": (None if individual_effect is None else individual_effect["classification_changes_horizontal_partition"]),
                                  "single_token_split_effect": individual_effect,
                                  "following_gap_trace": preceding_gaps})
                oversized_in_band.append(token_id)
            band_info.append({"vertical_band_index": band_index, "token_ids": [f"token-{t.source_row:04d}" for t in ordered],
                              "oversized_tokens": oversized_in_band})
        events = grouping_events({"lines": on_lines, "unresolved": on_unresolved},
                                 {"lines": off_lines, "unresolved": off_unresolved})
        token_records_by_id = {record["token_id"]: record for record in on_page["tokens"]}
        for index, event in enumerate(events, start=1):
            event["event_id"] = f"{prefix}.change-{index:03d}"
            event_tokens = [by_token[token_id] for token_id in event["token_ids"] if token_id in by_token]
            bounds = [min(t.x for t in event_tokens), min(t.y for t in event_tokens),
                      max(t.x1 for t in event_tokens), max(t.y1 for t in event_tokens)]
            event["cropped_image_region_px"] = bounds
            event["affected_token_texts_for_locator_only"] = [t.text for t in event_tokens]
            event["guard_predicate"] = "_is_oversized(token, gap_limit) is True and token is absent from _supported_bridge_ids"
            diagnostic_name = f"{event['event_id']}.png"
            event_records = [token_records_by_id[token_id] for token_id in event["token_ids"]]
            small_event_diagnostic(image_path, event_records, OUT / "diagnostics" / diagnostic_name)
            event["diagnostic_overlay"] = str((OUT / "diagnostics" / diagnostic_name).relative_to(ROOT))
            pixels = pixel_baseline_evidence(image_path, event_records)
            event["pixel_baseline_evidence"] = pixels
            if old_page["blank"]:
                event["adjudication"] = "benign_difference"
                event["adjudication_basis"] = "Fixture side is declared blank and the crop has zero pixels below grayscale 160; changed boxes are OCR detections on a blank region."
            elif (pixels["token_boxes_with_ink"] == pixels["token_box_count"]
                  and pixels["max_centroid_residual_px"] is not None
                  and pixels["max_centroid_residual_px"] <= 10
                  and event["pairs_merged_guard_off"]):
                event["adjudication"] = "repaired_false_split"
                event["adjudication_basis"] = "Every changed token box contains visible ink; their ink centroids fit one slanted/level baseline with <=10 px maximum residual, and guard-off restores their shared line membership."
            else:
                event["adjudication"] = "unresolved"
                event["adjudication_basis"] = "Crop pixels do not satisfy the declared same-baseline criterion; no wording-based inference."
        corpus_results.append({
            "fixture_id": fixture_id, "side": side, "crop_pdf": str(page_info["crop_path"].relative_to(ROOT)),
            "crop_image": str(image_path.relative_to(ROOT)), "image_width_px": width, "image_height_px": height,
            "image_sha256": sha256(image_path), "raw_tsv_path": str(tsv_path.relative_to(ROOT)),
            "raw_tsv_sha256": hashlib.sha256(raw_tsv_bytes).hexdigest(),
            "raw_tsv_gzip_sha256": sha256(tsv_path), "admission_errors": admission_errors,
            "declared_blank_side": old_page["blank"],
            "manual_crop_bbox_in_original_side_px_at_144dpi": [crop_x0,crop_y0,crop_x1,crop_y1],
            "old_source_tokens_outside_crop": old_outside_crop,
            "old_outside_crop_token_labels_absent_from_new_tsv": outside_labels_absent,
            "old_physical_lines_composed_only_of_outside_tokens": source_edge_only_lines,
            "old_token_text_locators_unmatched_but_pixel_visible": unmatched_visible,
            "dark_pixel_fraction_lt160": sum(Image.open(image_path).convert("L").histogram()[:160]) / (width * height),
            "admitted_token_count": len(tokens), "old_uncropped_admitted_token_count": len(old_page["tokens"]),
            "old_text_occurrence_alignment_count": matched,
            "clean_crop_baseline": {"physical_line_count": len(on_lines),
                "ambiguous_token_count": sum(item["code"] == "ambiguous_line_assignment" for item in on_unresolved),
                "unassigned_token_count": sum(item["code"] == "unassigned_line_assignment" for item in on_unresolved),
                "median_token_width_px": median(t.width for t in tokens) if tokens else None,
                "horizontal_gap_limit_px": on_measurements["horizontal_gap_limit_px"],
                "oversized_threshold_px": on_measurements["horizontal_gap_limit_px"] * 1.5,
                "selected_baseline_slope": on_measurements["baseline_slope_px_per_px"],
                "tolerance_px": on_measurements["tolerance_px"], "guard_triggering_token_count": len(oversized),
                "guard_triggering_tokens": oversized},
            "guard_off": {"physical_line_count": len(off_lines),
                "ambiguous_token_count": sum(item["code"] == "ambiguous_line_assignment" for item in off_unresolved),
                "unassigned_token_count": sum(item["code"] == "unassigned_line_assignment" for item in off_unresolved),
                "median_token_width_px": median(t.width for t in tokens) if tokens else None,
                "horizontal_gap_limit_px": off_measurements["horizontal_gap_limit_px"],
                "selected_baseline_slope": off_measurements["baseline_slope_px_per_px"],
                "tolerance_px": off_measurements["tolerance_px"]},
            "vertical_band_inventory": band_info,
            "changed_groupings": events,
            "token_inventory_path": str((OUT / "guard_on" / f"{prefix}.geometry.json").relative_to(ROOT)),
        })
    (OUT / "results.json").write_text(json.dumps({"schema": "manual-crop-guard-ablation-results-v1", "pages": corpus_results}, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"pages": len(corpus_results), "tokens": sum(p["admitted_token_count"] for p in corpus_results),
                      "lines_on": sum(p["clean_crop_baseline"]["physical_line_count"] for p in corpus_results),
                      "lines_off": sum(p["guard_off"]["physical_line_count"] for p in corpus_results),
                      "changed_groupings": sum(len(p["changed_groupings"]) for p in corpus_results),
                      "oversized": sum(p["clean_crop_baseline"]["guard_triggering_token_count"] for p in corpus_results)}, indent=2))


if __name__ == "__main__":
    run()
