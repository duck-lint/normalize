"""Human visual oracle package and scorer for Slice 2 physical-line geometry.

This module is research-only. It calls the unchanged production preprocessing
and geometry entry points, copies their actual input pixels, and never reads
raw/normalized Markdown or expected structural assertions as review answers.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = Path(__file__).resolve().parent / "review"
LEDGER_PATH = Path(__file__).resolve().parent / "human-review.json"
SCORER_VERSION = "human-geometry-scorer-v1"
REVIEW_STATUSES = {"unreviewed", "verified_no_exceptions", "verified_with_exceptions"}
EXCEPTION_TYPES = {
    "false_merge",
    "false_split",
    "wrong_membership",
    "wrong_order",
    "residual_expected_membership",
    "other_geometry_error",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object in {path}")
    return value


def _line_bbox(line: Mapping[str, Any], tokens: Mapping[str, Mapping[str, Any]]) -> tuple[int, int, int, int] | None:
    fields = ("left_px", "top_px", "right_px", "bottom_px")
    if all(line.get(field) is not None for field in fields):
        return tuple(int(line[field]) for field in fields)  # type: ignore[return-value]
    # Production intentionally nulls line bounds when any page token is
    # unassigned. For inspection, show the observed bounds of this line's
    # resolved member boxes without changing the geometry artifact.
    members = [tokens[token_id] for token_id in line.get("token_ids", []) if token_id in tokens]
    if not members:
        members = [
            token for token in tokens.values()
            if line.get("line_id") in token.get("candidate_line_ids", [])
        ]
    if not members and tokens:
        # If production withheld all bounds and assignments for this band, use
        # the closest observed token row as a locating region for the label.
        # The bounds remain a review aid; the saved geometry stays untouched.
        median_y = float(line.get("median_center_y_px", 0))
        members = [min(tokens.values(), key=lambda token: abs((token["y_px"] + token["bottom_px"]) / 2 - median_y))]
    if not members:
        return None
    return (
        min(int(token["x_px"]) for token in members),
        min(int(token["y_px"]) for token in members),
        max(int(token["right_px"]) for token in members),
        max(int(token["bottom_px"]) for token in members),
    )


def _overlay(source_path: Path, page: Mapping[str, Any], output_path: Path) -> None:
    with Image.open(source_path) as opened:
        image = opened.convert("RGB")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    tokens = {item["token_id"]: item for item in page.get("tokens", [])}

    # The source image remains pixel-identical in its separate package file.
    # This second image adds only review marks on top of those pixels.
    for token in page.get("tokens", []):
        box = (token["x_px"], token["y_px"], token["right_px"], token["bottom_px"])
        color = (220, 0, 180) if token.get("physical_line_id") is None else (40, 150, 230)
        draw.rectangle(box, outline=color, width=2)
    for line in page.get("physical_lines", []):
        box = _line_bbox(line, tokens)
        if box is None:
            continue
        x0, y0, x1, y1 = box
        draw.rectangle(box, outline=(255, 40, 20), width=3)
        label = str(line["line_id"])
        label_box = draw.textbbox((0, 0), label, font=font)
        label_width = label_box[2] - label_box[0]
        label_height = label_box[3] - label_box[1]
        label_x = max(0, min(x0, image.width - label_width - 8))
        label_y = max(0, y0 - label_height - 8)
        draw.rectangle((label_x, label_y, label_x + label_width + 8, label_y + label_height + 5), fill=(140, 15, 0))
        draw.text((label_x + 4, label_y + 2), label, fill=(255, 255, 255), font=font)

    # Residual token boxes use magenta. Numbered labels link them to the
    # residual identity table and carry every current candidate line ID.
    residual_index = 0
    for token in page.get("tokens", []):
        if token.get("physical_line_id") is not None:
            continue
        residual_index += 1
        candidates = token.get("candidate_line_ids", [])
        state = "ambiguous" if candidates else "unassigned"
        label = f"R{residual_index} {state}: {','.join(candidates) if candidates else 'no candidates'}"
        x = int(token["x_px"])
        y = max(0, int(token["y_px"]) - 17)
        bounds = draw.textbbox((x, y), label, font=font)
        draw.rectangle((bounds[0] - 2, bounds[1] - 1, bounds[2] + 2, bounds[3] + 1), fill=(150, 0, 110))
        draw.text((x, y), label, fill="white", font=font)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG")


def _page_html(fixture_id: str, page: Mapping[str, Any]) -> str:
    side = str(page["side"])
    source = f"../preprocessed/{fixture_id}/{Path(str(page['image_path'])).name}"
    overlay = f"../pages/{fixture_id}/{side}.overlay.png"
    tokens = {token["token_id"]: token for token in page.get("tokens", [])}
    line_rows = []
    for line in page.get("physical_lines", []):
        members = [tokens[token_id] for token_id in line.get("token_ids", []) if token_id in tokens]
        text = " ".join(str(token.get("text", "")) for token in members)
        identities = ", ".join(
            f"row {token['source_row']} / {token['token_id']} [{token['x_px']},{token['y_px']},{token['width_px']},{token['height_px']}]"
            for token in members
        )
        line_rows.append(
            f"<tr><td>{html.escape(str(line['line_id']))}</td><td>{html.escape(text)}</td>"
            f"<td>{html.escape(identities)}</td></tr>"
        )
    residual_rows = []
    residual_ordinal = 0
    for token in page.get("tokens", []):
        if token.get("physical_line_id") is not None:
            continue
        residual_ordinal += 1
        candidates = token.get("candidate_line_ids", [])
        state = "ambiguous" if candidates else "unassigned"
        residual_rows.append(
            "<tr>"
            f"<td>R{residual_ordinal}</td><td>{html.escape(token['token_id'])}</td>"
            f"<td>source row {token['source_row']}</td><td>{html.escape(str(token['text']))}</td>"
            f"<td>{state}</td><td>{html.escape(', '.join(candidates) or 'none')}</td></tr>"
        )
    residual_table = "".join(residual_rows) or '<tr><td colspan="6">No residual tokens.</td></tr>'
    return f"""<section class="page" id="{html.escape(fixture_id)}-{html.escape(side)}">
<h2>{html.escape(fixture_id)} / {html.escape(side)}</h2>
<p>{len(page.get('physical_lines', []))} lines · {sum(t.get('physical_line_id') is not None for t in page.get('tokens', []))} resolved · {len(residual_rows)} residual</p>
<div class="images"><figure><a href="{source}"><img src="{source}" alt="Unchanged preprocessed page"></a><figcaption>Unchanged preprocessed page</figcaption></figure>
<figure><a href="{overlay}"><img src="{overlay}" alt="Production geometry overlay"></a><figcaption>Geometry overlay — red line bounds and IDs, blue resolved token boxes, magenta residuals</figcaption></figure></div>
<details><summary>Production physical lines and token identities</summary><table><thead><tr><th>physical_line_id</th><th>OCR locator text</th><th>Stable token identities and boxes (px)</th></tr></thead><tbody>{''.join(line_rows)}</tbody></table></details>
<details><summary>Residual tokens</summary><table><thead><tr><th>Overlay</th><th>Token ID</th><th>Source row</th><th>OCR locator</th><th>State</th><th>Candidate lines</th></tr></thead><tbody>{residual_table}</tbody></table></details>
</section>"""


def _write_index(pages: list[tuple[str, Mapping[str, Any]]], destination: Path) -> None:
    sections = "\n".join(_page_html(fixture_id, page) for fixture_id, page in pages)
    content = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Normalize geometry human review</title><style>
body{font:16px/1.45 system-ui,sans-serif;margin:1.5rem;color:#171717}h1{margin-bottom:.3rem}.instructions{background:#f4f2e9;padding:1rem;max-width:80rem}.page{border-top:2px solid #bbb;margin-top:2rem;padding-top:1rem}.images{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem}.images img{display:block;width:100%;height:auto;image-rendering:auto;border:1px solid #888}.images figure{margin:0;min-width:0}figcaption{font-size:.9rem;color:#444}table{border-collapse:collapse;width:100%;margin:.6rem 0 1rem}th,td{border:1px solid #bbb;padding:.4rem;text-align:left;vertical-align:top}td{overflow-wrap:anywhere}summary{cursor:pointer;font-weight:600}code{white-space:normal}@media(max-width:850px){.images{grid-template-columns:1fr}}
</style><body><h1>Normalize Slice 2 geometry review</h1><div class="instructions"><b>Review each page visually.</b> Compare the overlay with the unchanged source image; zoom by opening either image in a new tab. If every production line and assignment is right, set its page-side record in <code>../human-review.json</code> to <code>verified_no_exceptions</code>. Otherwise use <code>verified_with_exceptions</code> and record only the affected lines/tokens and their correction relation. Do not report OCR spelling issues as geometry errors. The JSON ledger is authoritative; this page does not write review state. Exception examples and field definitions are in <code>README.md</code>.</div>
""" + sections + "</body></html>\n"
    destination.write_text(content, encoding="utf-8")


def generate_package(root: Path = ROOT, output_dir: Path = PACKAGE) -> dict[str, Any]:
    """Run current geometry and create durable images, JSON artifacts, and ledger."""
    # Local import avoids imposing src/ on users importing the synthetic scorer.
    sys.path.insert(0, str(root / "src"))
    from normalize.fixtures import FixtureCatalog
    from normalize.geometry import run_geometry
    from normalize.rendering import preprocess_fixture

    config_path = root / "fixtures" / "preprocessing.json"
    output_dir.mkdir(parents=True, exist_ok=True)
    pages_root = output_dir / "pages"
    pages_root.mkdir(exist_ok=True)
    # Remove source-image copies from the earlier package layout; the current
    # package links directly to the durable production preprocessing pixels.
    for stale_copy in pages_root.rglob("*.source.png"):
        stale_copy.unlink()
    preprocessed_root = output_dir / "preprocessed"
    preprocessed_root.mkdir(exist_ok=True)
    package_pages: list[tuple[str, Mapping[str, Any]]] = []
    ledger_pages: list[dict[str, Any]] = []
    inventories = {"admitted_tokens": 0, "resolved_tokens": 0, "residual_tokens": 0, "produced_lines": 0}

    with tempfile.TemporaryDirectory(prefix="normalize-human-geometry-") as temporary:
        scratch = Path(temporary)
        for fixture in FixtureCatalog.load(root):
            prep_dir = preprocessed_root / fixture.fixture_id
            geometry_dir = scratch / fixture.fixture_id / "geometry"
            prep_result = preprocess_fixture(fixture, config_path, prep_dir)
            if prep_result.get("status") != "success":
                raise RuntimeError(f"preprocessing failed for {fixture.fixture_id}: {prep_result}")
            geometry_result = run_geometry(prep_dir, geometry_dir)
            if geometry_result.get("status") not in {"success", "uncertain"}:
                raise RuntimeError(f"geometry failed for {fixture.fixture_id}: {geometry_result}")
            geometry_path = geometry_dir / "geometry.json"
            geometry = _load(geometry_path)
            geometry_copy = output_dir / "geometry" / f"{fixture.fixture_id}.geometry.json"
            geometry_copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(geometry_path, geometry_copy)
            metadata_path = prep_dir / f"{fixture.fixture_id}.preprocess.json"
            metadata = _load(metadata_path)
            source_pages = {page["side"]: page for page in metadata["pages"]}
            for page in geometry["pages"]:
                tokens = page.get("tokens", [])
                resolved = sum(token.get("physical_line_id") is not None for token in tokens)
                residuals = [token for token in tokens if token.get("physical_line_id") is None]
                inventories["admitted_tokens"] += len(tokens)
                inventories["resolved_tokens"] += resolved
                inventories["residual_tokens"] += len(residuals)
                inventories["produced_lines"] += len(page.get("physical_lines", []))
                if page.get("blank"):
                    continue
                original_path = prep_dir / source_pages[page["side"]]["output_path"]
                page_dir = output_dir / "pages" / fixture.fixture_id
                page_dir.mkdir(parents=True, exist_ok=True)
                overlay_path = page_dir / f"{page['side']}.overlay.png"
                _overlay(original_path, page, overlay_path)
                package_pages.append((fixture.fixture_id, page))
                ledger_pages.append(
                    {
                        "fixture_id": fixture.fixture_id,
                        "side": page["side"],
                        "source_image": f"review/preprocessed/{fixture.fixture_id}/{Path(source_pages[page['side']]['output_path']).name}",
                        "source_image_sha256": sha256(original_path),
                        "geometry_artifact": f"review/geometry/{fixture.fixture_id}.geometry.json",
                        "geometry_artifact_sha256": sha256(geometry_copy),
                        "geometry_page_sha256": _json_hash(page),
                        "overlay_image": f"review/pages/{fixture.fixture_id}/{page['side']}.overlay.png",
                        "overlay_image_sha256": sha256(overlay_path),
                        "produced_line_count": len(page.get("physical_lines", [])),
                        "admitted_token_count": len(tokens),
                        "resolved_token_count": resolved,
                        "residual_token_count": len(residuals),
                        "residual_tokens": [
                            {
                                "token_id": token["token_id"],
                                "source_row": token["source_row"],
                                "text_locator": token["text"],
                                "bbox_px": [token["x_px"], token["y_px"], token["right_px"], token["bottom_px"]],
                                "state": "ambiguous" if token["candidate_line_ids"] else "unassigned",
                                "candidate_line_ids": token["candidate_line_ids"],
                            }
                            for token in residuals
                        ],
                        "token_identity_index": [
                            {
                                "token_id": token["token_id"],
                                "source_row": token["source_row"],
                                "text_locator": token["text"],
                                "bbox_px": [token["x_px"], token["y_px"], token["right_px"], token["bottom_px"]],
                                "physical_line_id": token["physical_line_id"],
                                "candidate_line_ids": token["candidate_line_ids"],
                            }
                            for token in tokens
                        ],
                        "review_status": "unreviewed",
                        "exceptions": [],
                    }
                )

    config_path = root / "fixtures" / "preprocessing.json"
    audit_module = Path(__file__).resolve()
    provenance = {
        "source_git_revision": _git(root, "rev-parse", "HEAD"),
        "production_geometry_implementation_sha256": sha256(root / "src/normalize/geometry.py"),
        "production_geometry_revision": _git(root, "log", "-1", "--format=%H", "--", "src/normalize/geometry.py"),
        "preprocessing_implementation_sha256": sha256(root / "src/normalize/rendering.py"),
        "preprocessing_config_sha256": sha256(config_path),
        "scorer_version": SCORER_VERSION,
        "scorer_sha256": sha256(audit_module),
    }
    # Use the production geometry provenance copied into each durable artifact;
    # this avoids depending on raw/expected/normalized fixture contents.
    source_pdfs: dict[str, dict[str, str]] = {}
    geometry_hashes: dict[str, str] = {}
    for path in sorted((output_dir / "geometry").glob("*.geometry.json")):
        artifact = _load(path)
        fixture_id = artifact["fixture_id"]
        source_pdfs[fixture_id] = {
            "path": artifact["provenance"]["source_pdf"],
            "sha256": artifact["provenance"]["source_pdf_sha256"],
        }
        geometry_hashes[fixture_id] = sha256(path)
    provenance["fixture_source_pdfs"] = source_pdfs
    provenance["geometry_artifacts"] = geometry_hashes
    ledger = {
        "schema": "normalize-human-geometry-review-v1",
        "review_states": sorted(REVIEW_STATUSES),
        "exception_types": sorted(EXCEPTION_TYPES),
        "provenance": provenance,
        "inventory": inventories,
        "pages": sorted(ledger_pages, key=lambda item: (item["fixture_id"], item["side"])),
    }
    (Path(__file__).resolve().parent / "human-review.json").write_text(
        json.dumps(ledger, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )
    _write_index(package_pages, output_dir / "index.html")
    return ledger


def _check_ledger(ledger: Mapping[str, Any], geometry_by_page: Mapping[tuple[str, str], Mapping[str, Any]]) -> None:
    """Validate review claims before they are allowed to alter an oracle group."""
    pages = ledger.get("pages")
    if not isinstance(pages, list):
        raise ValueError("ledger.pages must be a list")
    keys: set[tuple[str, str]] = set()
    for record in pages:
        key = (str(record.get("fixture_id")), str(record.get("side")))
        if key in keys:
            raise ValueError(f"duplicate page-side ledger key: {key}")
        keys.add(key)
        if record.get("review_status") not in REVIEW_STATUSES:
            raise ValueError(f"invalid review_status for {key}")
        if record["review_status"] == "unreviewed":
            raise ValueError(f"cannot finalize: page side {key[0]}/{key[1]} is unreviewed")
        if record["review_status"] == "verified_no_exceptions" and record.get("exceptions"):
            raise ValueError(f"{key} is verified_no_exceptions but contains exceptions")
        if record["review_status"] == "verified_with_exceptions" and not record.get("exceptions"):
            raise ValueError(f"{key} is verified_with_exceptions without exceptions")
        geometry = geometry_by_page.get(key)
        if geometry is None:
            raise ValueError(f"ledger page side has no production geometry: {key}")
        token_by_id = {token["token_id"]: token for token in geometry.get("tokens", [])}
        lines = {line["line_id"]: set(line["token_ids"]) for line in geometry.get("physical_lines", [])}
        seen_tokens: set[str] = set()
        residual_answers: set[str] = set()
        residual_token_ids = {
            token_id for token_id, token in token_by_id.items()
            if token.get("physical_line_id") is None
        }
        for exception in record.get("exceptions", []):
            kind = exception.get("type")
            if kind not in EXCEPTION_TYPES:
                raise ValueError(f"unsupported exception type {kind!r} on {key}")
            if kind == "other_geometry_error" and not str(exception.get("explanation", "")).strip():
                raise ValueError(f"other_geometry_error requires explanation on {key}")
            ids = set(exception.get("token_ids", []))
            unknown = ids - token_by_id.keys()
            if unknown:
                raise ValueError(f"unknown token identities on {key}: {sorted(unknown)}")
            if seen_tokens & ids:
                raise ValueError(f"overlapping exception token identities on {key}: {sorted(seen_tokens & ids)}")
            seen_tokens |= ids
            if kind == "false_merge":
                line_id = exception.get("production_line_id")
                groups = exception.get("human_groups")
                if line_id not in lines or not isinstance(groups, list) or len(groups) < 2:
                    raise ValueError(f"false_merge requires a production line and 2+ human_groups on {key}")
                if ids != lines[line_id]:
                    raise ValueError(f"false_merge token_ids must cover the complete production line {line_id}")
                group_ids = [group.get("human_group_id") for group in groups]
                if any(not group_id for group_id in group_ids) or len(set(group_ids)) != len(group_ids):
                    raise ValueError(f"false_merge requires distinct non-empty review-local human_group_id values on {key}")
                flattened = [token_id for group in groups for token_id in group.get("token_ids", [])]
                if set(flattened) != ids or len(flattened) != len(ids):
                    raise ValueError(f"false_merge human_groups must partition all affected tokens on {key}")
            elif kind == "false_split":
                line_ids = exception.get("production_line_ids", [])
                if len(line_ids) < 2 or len(set(line_ids)) != len(line_ids) or any(line_id not in lines for line_id in line_ids):
                    raise ValueError(f"false_split requires 2+ distinct production_line_ids on {key}")
                if ids != set().union(*(lines[line_id] for line_id in line_ids)):
                    raise ValueError(f"false_split token_ids must cover the selected production lines on {key}")
                if not exception.get("human_group_id"):
                    raise ValueError(f"false_split requires human_group_id on {key}")
            elif kind == "wrong_membership":
                if not exception.get("production_line_id") or not exception.get("intended_human_group_id"):
                    raise ValueError(f"wrong_membership requires current line and intended group on {key}")
                if not ids:
                    raise ValueError(f"wrong_membership requires token_ids on {key}")
                if any(token_by_id[token_id].get("physical_line_id") != exception["production_line_id"] for token_id in ids):
                    raise ValueError(f"wrong_membership production_line_id does not match current token assignments on {key}")
            elif kind == "wrong_order":
                if not exception.get("production_line_id") or not exception.get("ordered_token_ids"):
                    raise ValueError(f"wrong_order requires production_line_id and ordered_token_ids on {key}")
                order_ids = exception["ordered_token_ids"]
                if set(order_ids) != ids or len(order_ids) != len(ids):
                    raise ValueError(f"wrong_order must give an order of exactly token_ids on {key}")
                if ids != lines.get(exception["production_line_id"], set()):
                    raise ValueError(f"wrong_order must identify every token in production_line_id on {key}")
            elif kind == "residual_expected_membership":
                if len(ids) != 1 or not exception.get("human_group_id"):
                    raise ValueError(f"residual_expected_membership requires one token and human_group_id on {key}")
                token = token_by_id[next(iter(ids))]
                if token.get("physical_line_id") is not None:
                    raise ValueError(f"residual_expected_membership token is already resolved on {key}")
                residual_answers.add(token["token_id"])
            elif kind == "other_geometry_error" and not ids:
                raise ValueError(f"other_geometry_error requires token_ids on {key}")
        if residual_answers != residual_token_ids:
            missing = residual_token_ids - residual_answers
            extra = residual_answers - residual_token_ids
            raise ValueError(f"residual human membership must be recorded once for every residual on {key} (missing={sorted(missing)}, extra={sorted(extra)})")
    if keys != set(geometry_by_page):
        missing = set(geometry_by_page) - keys
        extra = keys - set(geometry_by_page)
        raise ValueError(f"ledger page sides do not match geometry (missing={sorted(missing)}, extra={sorted(extra)})")


def score_review(ledger: Mapping[str, Any], geometries: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Score completed human review; refuses any missing/unreviewed page side."""
    by_page: dict[tuple[str, str], Mapping[str, Any]] = {}
    for fixture_id, geometry in geometries.items():
        for page in geometry.get("pages", []):
            if not page.get("blank", False):
                by_page[(fixture_id, page["side"])] = page
    _check_ledger(ledger, by_page)

    admitted = resolved = covered_correctly = residual_count = residual_review_events = 0
    exact_human_lines = exact_production_lines = false_merges = false_splits = other_groups = 0
    pair_tp = pair_fp = pair_fn = 0
    wrong_order_events = wrong_order_tokens = wrong_order_groups = 0
    page_no_exceptions = page_with_exceptions = distinct_events = affected_tokens = 0
    residual_details: list[dict[str, Any]] = []
    page_details: list[dict[str, Any]] = []
    ledger_by_key = {(item["fixture_id"], item["side"]): item for item in ledger["pages"]}

    for key, page in by_page.items():
        record = ledger_by_key[key]
        tokens = page.get("tokens", [])
        resolved_tokens = [token for token in tokens if token.get("physical_line_id") is not None]
        residual_tokens = [token for token in tokens if token.get("physical_line_id") is None]
        admitted += len(tokens)
        resolved += len(resolved_tokens)
        residual_count += len(residual_tokens)
        exceptions = record.get("exceptions", [])
        page_no_exceptions += record["review_status"] == "verified_no_exceptions"
        page_with_exceptions += record["review_status"] == "verified_with_exceptions"
        distinct_events += len(exceptions)
        affected_tokens += len({token_id for exc in exceptions for token_id in exc.get("token_ids", [])})

        human_group = {token["token_id"]: str(token["physical_line_id"]) for token in resolved_tokens}
        wrong_order_lines: set[str] = set()
        other_lines: set[str] = set()
        page_wrong_order_tokens: set[str] = set()
        for exc in exceptions:
            kind = exc["type"]
            ids = exc.get("token_ids", [])
            if kind == "false_merge":
                false_merges += 1
                for group in exc["human_groups"]:
                    for token_id in group["token_ids"]:
                        human_group[token_id] = str(group["human_group_id"])
            elif kind == "false_split":
                false_splits += 1
                for token_id in ids:
                    human_group[token_id] = str(exc["human_group_id"])
            elif kind == "wrong_membership":
                for token_id in ids:
                    human_group[token_id] = str(exc["intended_human_group_id"])
            elif kind == "wrong_order":
                wrong_order_events += 1
                wrong_order_lines.add(str(exc["production_line_id"]))
                page_wrong_order_tokens.update(ids)
                other_lines.add(str(exc["production_line_id"]))
            elif kind == "other_geometry_error":
                other_lines.update(map(str, exc.get("production_line_ids", [])))
                line_id = exc.get("production_line_id")
                if line_id:
                    other_lines.add(str(line_id))
                if not line_id and not exc.get("production_line_ids"):
                    other_lines.update(
                        str(page_token(token_id, tokens).get("physical_line_id"))
                        for token_id in ids
                        if page_token(token_id, tokens).get("physical_line_id") is not None
                    )
            elif kind == "residual_expected_membership":
                residual_review_events += 1
                token_id = ids[0]
                group_id = str(exc["human_group_id"])
                human_group[token_id] = group_id
                candidate_groups = {
                    human_group.get(candidate["token_id"], "")
                    for candidate in page["tokens"]
                    if candidate.get("physical_line_id") is not None
                    and candidate["physical_line_id"] in page_token(token_id, tokens).get("candidate_line_ids", [])
                    and human_group.get(candidate["token_id"]) == group_id
                }
                candidates = page_token(token_id, tokens).get("candidate_line_ids", [])
                residual_details.append(
                    {
                        "fixture_id": key[0], "side": key[1], "token_id": token_id,
                        "expected_human_group_id": group_id,
                        "candidate_line_ids": candidates,
                        "candidate_state": "ambiguous" if candidates else "unassigned",
                        "correct_group_among_candidates": bool(candidate_groups),
                        "human_review_events": 1,
                    }
                )

        production_groups: dict[str, set[str]] = defaultdict(set)
        human_groups: dict[str, set[str]] = defaultdict(set)
        all_human_groups: dict[str, set[str]] = defaultdict(set)
        for token in resolved_tokens:
            token_id = token["token_id"]
            production_groups[str(token["physical_line_id"])].add(token_id)
            human_groups[human_group[token_id]].add(token_id)
            all_human_groups[human_group[token_id]].add(token_id)
        for token in residual_tokens:
            token_id = token["token_id"]
            all_human_groups[human_group[token_id]].add(token_id)

        # A token receives membership credit only when its complete production
        # equivalence class exactly equals its human physical-line class.
        production_by_token = {token_id: line_id for line_id, ids in production_groups.items() for token_id in ids}
        for token in resolved_tokens:
            token_id = token["token_id"]
            pred = production_groups[production_by_token[token_id]]
            truth = human_groups[human_group[token_id]]
            if pred == truth:
                covered_correctly += 1

        predicted_tokens = [token["token_id"] for token in resolved_tokens]
        for i, first in enumerate(predicted_tokens):
            for second in predicted_tokens[i + 1:]:
                same_pred = production_by_token[first] == production_by_token[second]
                same_human = human_group[first] == human_group[second]
                if same_pred and same_human:
                    pair_tp += 1
                elif same_pred:
                    pair_fp += 1
                elif same_human:
                    pair_fn += 1

        exact_human_lines += len(all_human_groups)
        for human_id, token_ids in all_human_groups.items():
            matches = [line_id for line_id, pred_ids in production_groups.items() if pred_ids == token_ids]
            if matches and not any(line_id in wrong_order_lines or line_id in other_lines for line_id in matches):
                exact_production_lines += 1
        other_groups += len(other_lines - wrong_order_lines)
        wrong_order_groups += len(wrong_order_lines)
        wrong_order_tokens += len(page_wrong_order_tokens)
        page_details.append({
            "fixture_id": key[0], "side": key[1],
            "review_status": record["review_status"],
            "exception_events": len(exceptions),
            "affected_token_count": len({token_id for exc in exceptions for token_id in exc.get("token_ids", [])}),
            "admitted_tokens": len(tokens), "resolved_tokens": len(resolved_tokens), "residual_tokens": len(residual_tokens),
        })

    return {
        "schema": SCORER_VERSION,
        "coverage": {"resolved_tokens": resolved, "admitted_tokens": admitted, "rate": _ratio(resolved, admitted)},
        "resolved_token_membership": {
            "correct_tokens": covered_correctly, "incorrect_tokens": resolved - covered_correctly,
            "resolved_tokens": resolved, "accuracy": _ratio(covered_correctly, resolved),
        },
        "silent_error_rate": _ratio(resolved - covered_correctly, resolved),
        "exact_physical_lines": {
            "human_validated_visible_lines": exact_human_lines,
            "exact_production_matches": exact_production_lines,
            "false_merges": false_merges, "false_splits": false_splits,
            "other_incorrect_groups": other_groups + wrong_order_groups,
        },
        "within_line_order": {
            "correct_resolved_tokens": resolved - wrong_order_tokens,
            "incorrect_resolved_tokens": wrong_order_tokens,
            "resolved_tokens": resolved,
            "accuracy": _ratio(resolved - wrong_order_tokens, resolved),
            "wrong_order_events": wrong_order_events,
        },
        "pairwise_grouping": {
            "same_line_pair_true_positive": pair_tp,
            "same_line_pair_false_positive": pair_fp,
            "same_line_pair_false_negative": pair_fn,
            "precision": _ratio(pair_tp, pair_tp + pair_fp),
            "recall": _ratio(pair_tp, pair_tp + pair_fn),
        },
        "residual_review": {
            "residual_tokens": residual_count,
            "expected_membership_recorded": len(residual_details),
            "correct_line_among_production_candidates": sum(item["correct_group_among_candidates"] for item in residual_details),
            "ambiguous": sum(item["candidate_state"] == "ambiguous" for item in residual_details),
            "unassigned": sum(item["candidate_state"] == "unassigned" for item in residual_details),
            "human_review_events": residual_review_events,
            "details": residual_details,
        },
        "review_burden": {
            "pages_requiring_review": len(by_page), "pages_verified_no_exceptions": page_no_exceptions,
            "pages_with_exceptions": page_with_exceptions,
            "distinct_exception_regions_or_events": distinct_events,
            "residual_review_events": residual_review_events,
            "affected_tokens": affected_tokens,
        },
        "pages": page_details,
    }


def page_token(token_id: str, tokens: list[Mapping[str, Any]]) -> Mapping[str, Any]:
    return next(token for token in tokens if token["token_id"] == token_id)


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def score_from_files(ledger_path: Path = LEDGER_PATH, package_dir: Path = PACKAGE) -> dict[str, Any]:
    ledger = _load(ledger_path)
    provenance = ledger.get("provenance", {})
    if provenance.get("scorer_sha256") != sha256(Path(__file__).resolve()):
        raise ValueError("scorer hash does not match the version recorded when this review package was generated")
    geometries: dict[str, dict[str, Any]] = {}
    artifact_hashes: dict[str, str] = {}
    for path in sorted((package_dir / "geometry").glob("*.geometry.json")):
        geometry = _load(path)
        fixture_id = geometry["fixture_id"]
        geometries[fixture_id] = geometry
        artifact_hashes[fixture_id] = sha256(path)
        if provenance.get("geometry_artifacts", {}).get(fixture_id) != artifact_hashes[fixture_id]:
            raise ValueError(f"geometry artifact hash mismatch for {fixture_id}")
    for record in ledger.get("pages", []):
        fixture_id = record["fixture_id"]
        if record.get("geometry_artifact_sha256") != artifact_hashes.get(fixture_id):
            raise ValueError(f"ledger geometry hash mismatch for {fixture_id}/{record['side']}")
        geometry_page = next(
            page for page in geometries[fixture_id]["pages"] if page["side"] == record["side"]
        )
        if record.get("geometry_page_sha256") != _json_hash(geometry_page):
            raise ValueError(f"geometry page identity hash mismatch for {fixture_id}/{record['side']}")
        for path_field, hash_field in (("source_image", "source_image_sha256"), ("overlay_image", "overlay_image_sha256")):
            image_path = ledger_path.parent / record[path_field]
            if not image_path.is_file() or sha256(image_path) != record.get(hash_field):
                raise ValueError(f"{path_field} hash mismatch for {fixture_id}/{record['side']}")
    result = score_review(ledger, geometries)
    result["ledger_sha256"] = sha256(ledger_path)
    result["scorer_sha256"] = sha256(Path(__file__).resolve())
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("generate", "score"))
    args = parser.parse_args()
    if args.action == "generate":
        ledger = generate_package()
        print(json.dumps({"inventory": ledger["inventory"], "reviewable_page_sides": len(ledger["pages"]), "ledger": str(LEDGER_PATH), "index": str(PACKAGE / "index.html")}, indent=2))
    else:
        print(json.dumps(score_from_files(), indent=2))


if __name__ == "__main__":
    main()
