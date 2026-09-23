"""Generate and verify controlled pixel experiments for Slice 2 geometry.

The experiment keeps the OCR/TSV payload fixed while changing only synthetic
source pixels.  It observes the existing box-only geometry implementation and
uses the existing identity-complete oracle without changing either one.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import subprocess
import sys
from collections import deque
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ROOT = Path(__file__).resolve().parent
BASELINE_COMMIT = "d2dbea8e8e1a51ad92b38bb2caddb7f209542e72"
CANVAS = (220, 70)
INK_THRESHOLD = 128

sys.path.insert(0, str(REPOSITORY_ROOT))

import normalize.geometry as geometry  # noqa: E402
from normalize.geometry import TSV_HEADER, group_physical_lines, parse_tsv_rows  # noqa: E402
from tests.geometry_oracle import canonical_geometry_state  # noqa: E402


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _jsonable(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


def _state_digest(state: tuple[Any, ...]) -> str:
    return _sha256_bytes(
        json.dumps(_jsonable(state), sort_keys=True, separators=(",", ":")).encode()
    )


def _row(text: str, *, x: int, y: int, width: int, word: int, height: int = 10) -> str:
    return "\t".join(map(str, (5, 1, 1, 1, 1, word, x, y, width, height, 95, text)))


def _shared_input(rows: list[str]) -> dict[str, Any]:
    """Return the complete synthetic TSV input shared by both pixel cases."""

    return {
        "schema": "normalize-synthetic-tsv-input-v1",
        "dimensions_px": {"width": CANVAS[0], "height": CANVAS[1]},
        "metadata": {
            "page_num": 1,
            "side": "synthetic",
            "source": "controlled synthetic input; not a scan observation",
        },
        "tsv_header": list(TSV_HEADER),
        "rows": rows,
    }


def _input_digest(payload: dict[str, Any]) -> str:
    return _sha256_bytes(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    )


def _parse_input(payload: dict[str, Any]):
    tsv = "\t".join(payload["tsv_header"]) + "\n" + "\n".join(payload["rows"]) + "\n"
    tokens, errors = parse_tsv_rows(
        tsv,
        payload["dimensions_px"]["width"],
        payload["dimensions_px"]["height"],
    )
    if errors:
        raise AssertionError(f"synthetic TSV rejected: {errors}")
    return tokens


def _assignment_rows(state: tuple[Any, ...]) -> list[dict[str, Any]]:
    return [
        {
            "identity": list(item[0]),
            "text": item[1],
            "resolved_assignment": item[2],
            "candidate_lines": list(item[3]),
            "uncertainty": item[4],
            "box": {"x": item[5], "y": item[6], "width": item[7], "height": item[8]},
            "confidence": item[9],
        }
        for item in state[0]
    ]


def _run_box_geometry(payload: dict[str, Any], *, case_identity: str) -> dict[str, Any]:
    """Observe complete state with one common synthetic identity namespace.

    The common namespace is the only synthetic-case normalization.  Stable
    source-row identities, assignments, candidate sets, uncertainty, line
    membership, and measurements remain in the canonical state.
    """

    tokens = _parse_input(payload)
    result = group_physical_lines(tokens)
    state = canonical_geometry_state(case_identity, "synthetic", tokens, *result)
    reversed_tokens = list(reversed(tokens))
    reversed_result = group_physical_lines(reversed_tokens)
    permuted_state = canonical_geometry_state(
        case_identity, "synthetic", reversed_tokens, *reversed_result
    )
    return {
        "physical_lines": result[0],
        "unresolved": result[1],
        "measurements": result[2],
        "canonical_state": _jsonable(state),
        "canonical_state_sha256": _state_digest(state),
        "identity_complete_assignments": _assignment_rows(state),
        "reversed_input_same_state": state == permuted_state,
        "reversed_state_sha256": _state_digest(permuted_state),
    }


def _draw_token_ink(draw: ImageDraw.ImageDraw, x: int, y: int, width: int, height: int) -> None:
    """Draw sparse monochrome glyph-like ink inside an ordinary token box."""

    top = y + 2
    bottom = y + height - 3
    for offset in range(2, max(3, width - 2), 4):
        stroke_width = 2 if offset % 3 else 1
        draw.rectangle((x + offset, top, min(x + offset + stroke_width, x + width - 1), bottom), fill=0)
    draw.rectangle((x + 1, y + height - 3, x + width - 2, y + height - 2), fill=0)


def _base_source_image(rows: list[str]) -> Image.Image:
    image = Image.new("L", CANVAS, 255)
    draw = ImageDraw.Draw(image)
    for row in rows:
        fields = row.split("\t")
        text = fields[-1]
        if text == "ocr-wide":
            continue
        x, y, width, height = map(int, fields[6:10])
        _draw_token_ink(draw, x, y, width, height)
    return image


def _source_image(rows: list[str], roi: dict[str, int], *, continuous: bool) -> Image.Image:
    image = _base_source_image(rows)
    if continuous:
        draw = ImageDraw.Draw(image)
        y0, y1 = roi["y0"], roi["y1"]
        # A visible support structure crosses the entire ROI.  It is not an
        # assertion that ordinary printed words form one connected component.
        draw.rectangle((roi["x0"], y0 + 4, roi["x1"] - 1, y0 + 5), fill=0)
        for x in range(roi["x0"] + 4, roi["x1"] - 2, 11):
            draw.rectangle((x, y0 + 2, min(x + 4, roi["x1"] - 1), y1 - 3), fill=0)
    return image


def _overlay(source: Image.Image, rows: list[str]) -> Image.Image:
    overlay = source.convert("RGB")
    draw = ImageDraw.Draw(overlay)
    for row in rows:
        fields = row.split("\t")
        x, y, width, height = map(int, fields[6:10])
        draw.rectangle((x, y, x + width - 1, y + height - 1), outline=(30, 90, 220), width=1)
    return overlay


def _roi_measurements(image: Image.Image, roi: dict[str, int]) -> dict[str, Any]:
    crop = image.convert("L").crop((roi["x0"], roi["y0"], roi["x1"], roi["y1"]))
    width, height = crop.size
    pixels = list(crop.tobytes())
    ink = [value < INK_THRESHOLD for value in pixels]
    columns = [
        sum(ink[y * width + x] for y in range(height))
        for x in range(width)
    ]
    rows = [sum(ink[y * width : (y + 1) * width]) for y in range(height)]

    empty_runs: list[int] = []
    run = 0
    for count in columns:
        if count == 0:
            run += 1
        elif run:
            empty_runs.append(run)
            run = 0
    if run:
        empty_runs.append(run)

    def component_count(scale: int = 1) -> tuple[int, int]:
        scaled = crop if scale == 1 else crop.resize(
            (math.ceil(width / scale), math.ceil(height / scale)), Image.Resampling.BOX
        )
        sw, sh = scaled.size
        points = {(x, y) for y in range(sh) for x in range(sw) if scaled.getpixel((x, y)) < INK_THRESHOLD}
        count = 0
        largest = 0
        while points:
            count += 1
            start = points.pop()
            queue = deque([start])
            area = 1
            while queue:
                x, y = queue.popleft()
                for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1), (x - 1, y - 1), (x + 1, y + 1), (x - 1, y + 1), (x + 1, y - 1)):
                    if neighbor in points:
                        points.remove(neighbor)
                        queue.append(neighbor)
                        area += 1
            largest = max(largest, area)
        return count, largest

    occupied_rows = [index for index, count in enumerate(rows) if count]
    return {
        "roi": roi,
        "dimensions_px": {"width": width, "height": height},
        "ink_pixels": sum(ink),
        "ink_occupancy": sum(ink) / (width * height),
        "occupied_column_fraction": sum(count > 0 for count in columns) / width,
        "column_ink_counts": columns,
        "row_ink_counts": rows,
        "empty_column_runs_px": empty_runs,
        "max_empty_column_run_px": max(empty_runs, default=0),
        "occupied_row_bounds_px": None
        if not occupied_rows
        else {"y0": occupied_rows[0] + roi["y0"], "y1": occupied_rows[-1] + roi["y0"] + 1},
        "connected_components_8_native": {
            "count": component_count()[0],
            "largest_area_px": component_count()[1],
        },
        "connected_components_8_half_scale": {
            "count": component_count(2)[0],
            "largest_area_px": component_count(2)[1],
        },
    }


def _assert_monochrome(image: Image.Image) -> None:
    if image.mode != "L" or set(image.tobytes()) - {0, 255}:
        raise AssertionError("source image is not clean monochrome")


def _pair_result(
    name: str,
    payload: dict[str, Any],
    continuous: Image.Image,
    disconnected: Image.Image,
    roi: dict[str, int],
) -> dict[str, Any]:
    _assert_monochrome(continuous)
    _assert_monochrome(disconnected)
    # Keep independent payload objects so the check does not pass merely by
    # reusing one object as both inputs.
    continuous_payload = json.loads(json.dumps(payload))
    disconnected_payload = json.loads(json.dumps(payload))
    continuous_box = _run_box_geometry(continuous_payload, case_identity="synthetic-pair")
    disconnected_box = _run_box_geometry(disconnected_payload, case_identity="synthetic-pair")
    continuous_measurements = _roi_measurements(continuous, roi)
    disconnected_measurements = _roi_measurements(disconnected, roi)
    source_equal = continuous.tobytes() == disconnected.tobytes()
    input_hash = _input_digest(payload)
    checks = {
        "identical_box_input_payload": continuous_payload == disconnected_payload,
        "box_input_sha256": input_hash,
        "source_pixel_arrays_differ": not source_equal,
        "bridge_roi_measurements_differ": continuous_measurements != disconnected_measurements,
        "disconnected_case_has_empty_bridge_interval": disconnected_measurements["max_empty_column_run_px"] == roi["x1"] - roi["x0"],
        "box_only_complete_assignment_state_equivalent": continuous_box["canonical_state"] == disconnected_box["canonical_state"],
        "box_only_reversed_input_stable": continuous_box["reversed_input_same_state"] and disconnected_box["reversed_input_same_state"],
    }
    if not all(checks.values()):
        raise AssertionError(f"corrected pair {name} failed: {checks}")
    return {
        "pair_id": name,
        "input": payload,
        "input_sha256": input_hash,
        "region_of_interest": roi,
        "continuous": {
            "source_image": {"dimensions_px": continuous.size},
            "measurements": continuous_measurements,
            "box_only_output": continuous_box,
        },
        "disconnected": {
            "source_image": {"dimensions_px": disconnected.size},
            "measurements": disconnected_measurements,
            "box_only_output": disconnected_box,
        },
        "checks": checks,
        "interpretation": {
            "continuous": "controlled synthetic pixels visibly support ink across the proposed bridge ROI",
            "disconnected": "controlled synthetic pixels contain a blank bridge ROI; the wide OCR box is not source ink",
            "authority": "illustrative synthetic evidence, not an observation from a scanned book",
        },
    }


def _adversarial_measurements(rows: list[str], roi: dict[str, int]) -> dict[str, Any]:
    base = _base_source_image(rows)

    noise = base.copy()
    noise_draw = ImageDraw.Draw(noise)
    for x in range(roi["x0"], roi["x1"]):
        noise_draw.point((x, roi["y0"] + 5), fill=0)

    glyphs = base.copy()
    glyph_draw = ImageDraw.Draw(glyphs)
    for x in range(roi["x0"] + 2, roi["x1"] - 2, 13):
        glyph_draw.rectangle((x, roi["y0"] + 3, min(x + 4, roi["x1"] - 1), roi["y1"] - 3), fill=0)

    neighbor = base.copy()
    neighbor_draw = ImageDraw.Draw(neighbor)
    neighbor_draw.rectangle((roi["x0"], roi["y0"] + 18, roi["x1"] - 1, roi["y0"] + 19), fill=0)
    broad_roi = {**roi, "y1": min(CANVAS[1], roi["y1"] + 25)}

    return {
        "noise_bridge": {
            "physical_interpretation": "disconnected regions with a one-pixel noise path",
            "native_roi": _roi_measurements(noise, roi),
        },
        "separate_glyph_components": {
            "physical_interpretation": "one printed row represented by separated glyph components and spaces",
            "native_roi": _roi_measurements(glyphs, roi),
        },
        "neighbor_row_ink": {
            "physical_interpretation": "ink belongs to a neighboring row, not the token baseline",
            "token_band_roi": _roi_measurements(neighbor, roi),
            "broad_roi": _roi_measurements(neighbor, broad_roi),
        },
    }


def _package_versions() -> dict[str, str]:
    names = ("normalize", "Pillow", "pytesseract", "pytest", "numpy", "opencv-python-headless", "PyMuPDF", "rapidfuzz")
    result = {}
    for name in names:
        try:
            result[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            result[name] = "not installed"
    return result


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPOSITORY_ROOT, check=True, text=True, capture_output=True).stdout.strip()


def _artifact_inventory(root: Path) -> list[dict[str, Any]]:
    artifacts = []
    for path in sorted(root.rglob("*")):
        if (
            not path.is_file()
            or path.name == "manifest.json"
            or "__pycache__" in path.parts
            or path.suffix == ".pyc"
        ):
            continue
        artifacts.append({
            "path": str(path.relative_to(REPOSITORY_ROOT)),
            "sha256": _sha256(path),
            "size_bytes": path.stat().st_size,
        })
    return artifacts


def run_experiment(root: Path = DEFAULT_ROOT, *, write_manifest: bool = True) -> dict[str, Any]:
    if _git("rev-parse", "HEAD") != BASELINE_COMMIT:
        raise AssertionError("experiment must run against the verified starting revision")
    root.mkdir(parents=True, exist_ok=True)

    two_rows = [
        _row("same", x=10, y=20, width=10, word=1),
        _row("same", x=25, y=20, width=10, word=2),
        _row("ocr-wide", x=30, y=20, width=115, word=3),
        _row("same", x=145, y=20, width=10, word=4),
        _row("same", x=160, y=20, width=10, word=5),
    ]
    one_rows = [
        _row("same", x=10, y=20, width=10, word=1),
        _row("ocr-wide", x=20, y=20, width=130, word=2),
        _row("same", x=150, y=20, width=10, word=3),
    ]
    cases = [
        (
            "two_ordinary_tokens_each_side",
            _shared_input(two_rows),
            {"x0": 35, "x1": 145, "y0": 20, "y1": 30},
        ),
        (
            "one_ordinary_token_each_side",
            _shared_input(one_rows),
            {"x0": 20, "x1": 150, "y0": 20, "y1": 30},
        ),
    ]

    pixel_root = root / "pixel-cases"
    overlay_root = root / "overlays"
    pixel_root.mkdir(parents=True, exist_ok=True)
    overlay_root.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for name, payload, roi in cases:
        continuous = _source_image(payload["rows"], roi, continuous=True)
        disconnected = _source_image(payload["rows"], roi, continuous=False)
        pair = _pair_result(name, payload, continuous, disconnected, roi)
        continuous.save(pixel_root / f"{name}__continuous.png")
        disconnected.save(pixel_root / f"{name}__disconnected.png")
        _overlay(continuous, payload["rows"]).save(overlay_root / f"{name}__continuous-overlay.png")
        _overlay(disconnected, payload["rows"]).save(overlay_root / f"{name}__disconnected-overlay.png")
        results.append(pair)

    defective = _source_image(two_rows, cases[0][2], continuous=True)
    defective_check = {
        "source_pixel_arrays_differ": defective.tobytes() != defective.tobytes(),
        "bridge_roi_measurements_differ": _roi_measurements(defective, cases[0][2]) != _roi_measurements(defective, cases[0][2]),
    }
    if any(defective_check.values()):
        raise AssertionError("identical defective pixel pair was incorrectly accepted")

    adversarial = _adversarial_measurements(two_rows, cases[0][2])
    result = {
        "schema": "normalize-pixel-discrimination-experiment-v1",
        "authority": "Synthetic pixels are controlled illustrations; preserved scan-derived geometry remains the observed source evidence.",
        "baseline_commit": BASELINE_COMMIT,
        "geometry_module_import_path": str(Path(geometry.__file__).resolve()),
        "pairs": results,
        "deliberately_identical_pair_rejected": defective_check,
        "adversarial_measurements": adversarial,
        "conclusions": {
            "established": "Identical box/TSV inputs cannot cause the current box-only algorithm to distinguish different pixel observations.",
            "demonstrated": "The corrected paired images differ in the intended bridge-region pixel evidence while producing equivalent complete box-only assignment states.",
            "not_established": "No generally reliable pixel-derived criterion for assigning arbitrary document tokens to physical lines.",
        },
    }
    output_path = root / "pixel-experiment-results.json"
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if write_manifest:
        residual_root = REPOSITORY_ROOT / "research/geometry/residual-forensics"
        diagnostic_root = REPOSITORY_ROOT / "research/geometry/diagnostic-investigation"
        source_refs = []
        for path in (
            residual_root / "forensic-report.md",
            residual_root / "manifest.json",
            diagnostic_root / "investigation-report.md",
            diagnostic_root / "manifest.json",
            REPOSITORY_ROOT / "fixtures/preprocessing.json",
        ):
            source_refs.append({"path": str(path.relative_to(REPOSITORY_ROOT)), "sha256": _sha256(path)})
        try:
            tesseract = subprocess.run(["tesseract", "--version"], check=True, text=True, capture_output=True).stdout.splitlines()[0]
        except (FileNotFoundError, subprocess.CalledProcessError):
            tesseract = "unavailable"
        manifest = {
            "schema": "normalize-evidence-corrections-v1",
            "generated_at_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            "experiment_start": {
                "git_commit_sha": BASELINE_COMMIT,
                "git_branch": "evidence-corrections-pixel-experiments",
                "git_status": "clean (verified before research edits)",
                "starting_commit_verified": _git("rev-parse", "HEAD") == BASELINE_COMMIT,
            },
            "generation_state": {
                "git_commit_sha": _git("rev-parse", "HEAD"),
                "git_branch": _git("branch", "--show-current"),
                "git_status_porcelain": _git("status", "--short"),
            },
            "environment": {
                "python": sys.version,
                "python_executable": sys.executable,
                "packages": _package_versions(),
                "tesseract": tesseract,
                "geometry_module_import_path": str(Path(geometry.__file__).resolve()),
            },
            "commands": [
                ".venv/bin/python research/geometry/evidence-corrections/pixel_experiments.py",
                ".venv/bin/python -m pytest -q tests/test_evidence_corrections.py",
                ".venv/bin/python -m pytest -q",
            ],
            "input_provenance": {
                "synthetic_box_inputs": [
                    {"pair_id": item["pair_id"], "sha256": item["input_sha256"], "source": "this manifest's controlled TSV payload"}
                    for item in results
                ],
                "preserved_evidence_references": source_refs,
                "source_pdfs_copied": False,
            },
            "roi_definitions_and_measurements": [
                {"pair_id": item["pair_id"], "roi": item["region_of_interest"], "continuous": item["continuous"]["measurements"], "disconnected": item["disconnected"]["measurements"]}
                for item in results
            ],
            "observed_assignment_state_comparisons": [
                {"pair_id": item["pair_id"], "checks": item["checks"], "continuous_state_sha256": item["continuous"]["box_only_output"]["canonical_state_sha256"], "disconnected_state_sha256": item["disconnected"]["box_only_output"]["canonical_state_sha256"]}
                for item in results
            ],
            "artifact_paths_and_hashes": _artifact_inventory(root),
            "restrictions": {
                "production_geometry_modified": False,
                "identity_complete_oracle_modified": False,
                "fixture_contracts_modified": False,
                "source_pdfs_committed": False,
                "dependencies_installed": False,
                "symphony_modified": False,
            },
        }
        (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    result = run_experiment(args.output_root)
    print(json.dumps({"output": str(args.output_root), "pairs": len(result["pairs"]), "manifest": str(args.output_root / "manifest.json")}, indent=2))


if __name__ == "__main__":
    main()
