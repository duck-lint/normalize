"""Deterministic, evidence-only geometry extraction for Slice 2.

This module deliberately keeps the two authority boundaries visible: Tesseract
text and identifiers are retained as locating evidence, while coordinates and
the physical rows derived from them describe only observed page geometry.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

import pytesseract
from PIL import Image, ImageDraw
from pytesseract import Output

from .rendering import FAILURE, SUCCESS, UNCERTAIN, validate_metadata_contract

GEOMETRY_SCHEMA = "geometry-probe-v1"
TSV_HEADER = (
    "level",
    "page_num",
    "block_num",
    "par_num",
    "line_num",
    "word_num",
    "left",
    "top",
    "width",
    "height",
    "conf",
    "text",
)
GEOMETRY_ERROR_CODES = (
    "input_schema_invalid",
    "preprocessing_not_success",
    "image_missing",
    "image_dimension_mismatch",
    "tesseract_invocation",
    "tsv_invalid",
    "geometry_invalid",
    "provenance_mismatch",
    "serialization_failure",
    "annotation_failure",
    "publication_failure",
    "cleanup_unverified",
)
GEOMETRY_UNCERTAINTY_CODES = (
    "ambiguous_line_assignment",
    "unassigned_line_assignment",
    "no_tokens_on_declared_nonblank_page",
)
_INTEGER = re.compile(r"[0-9]+\Z")
_DECIMAL = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)\Z")


class GeometryError(RuntimeError):
    """A user-facing geometry input or publication failure."""

    def __init__(self, code: str, reason: str, *, fixture_id: str | None = None):
        super().__init__(reason)
        self.code = code
        self.reason = reason
        self.fixture_id = fixture_id


@dataclass(frozen=True)
class _PreprocessedPage:
    side: str
    image_path: Path
    width: int
    height: int
    blank: bool
    record: Mapping[str, Any]


@dataclass(frozen=True)
class _PreprocessedInput:
    directory: Path
    metadata_path: Path
    metadata: Mapping[str, Any]
    metadata_digest: str
    pages: tuple[_PreprocessedPage, ...]


@dataclass(frozen=True)
class _Token:
    source_row: int
    text: str
    confidence: float
    level: int
    page_num: int
    block_num: int
    par_num: int
    line_num: int
    word_num: int
    x: int
    y: int
    width: int
    height: int

    @property
    def x1(self) -> int:
        return self.x + self.width

    @property
    def y1(self) -> int:
        return self.y + self.height

    @property
    def center_y(self) -> float:
        return (self.y + self.y1) / 2

    def payload(self) -> tuple[Any, ...]:
        return (
            self.text,
            self.confidence,
            self.level,
            self.page_num,
            self.block_num,
            self.par_num,
            self.line_num,
            self.word_num,
            self.x,
            self.y,
            self.width,
            self.height,
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_digest(record: Mapping[str, Any]) -> str:
    encoded = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def _error_payload(fixture_id: str | None, code: str, reason: str) -> dict[str, Any]:
    return {
        "schema": GEOMETRY_SCHEMA,
        "status": FAILURE,
        "fixture_id": fixture_id,
        "errors": [code],
        "error_details": [{"code": code, "reason": reason}],
        "uncertainties": [],
        "pages": [],
    }


def _metadata_path(directory: Path) -> Path:
    if not directory.is_dir():
        raise GeometryError("input_schema_invalid", f"preprocessed path is not a directory: {directory}")
    paths = sorted(directory.glob("*.preprocess.json"))
    if len(paths) != 1:
        raise GeometryError(
            "input_schema_invalid",
            f"expected exactly one *.preprocess.json in {directory}, found {len(paths)}",
        )
    return paths[0]


def _load_input(directory: Path) -> _PreprocessedInput:
    directory = directory.resolve()
    metadata_path = _metadata_path(directory)
    try:
        with metadata_path.open(encoding="utf-8") as handle:
            metadata = json.load(handle)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GeometryError("input_schema_invalid", f"cannot load preprocessing metadata: {exc}") from exc
    if not isinstance(metadata, dict):
        raise GeometryError("input_schema_invalid", "preprocessing metadata root must be an object")
    try:
        validate_metadata_contract(metadata)
    except ValueError as exc:
        raise GeometryError("input_schema_invalid", str(exc)) from exc
    if metadata.get("schema") != "preprocessing-metadata-v1":
        raise GeometryError("input_schema_invalid", "preprocessing metadata schema is not preprocessing-metadata-v1")
    fixture_id = metadata.get("fixture_id")
    if not isinstance(fixture_id, str) or not fixture_id:
        raise GeometryError("input_schema_invalid", "preprocessing metadata fixture_id is invalid")
    if metadata.get("status") != SUCCESS:
        raise GeometryError(
            "preprocessing_not_success",
            f"preprocessing status is {metadata.get('status')!r}; geometry requires success",
            fixture_id=fixture_id,
        )
    source_pdf = metadata.get("source_pdf")
    source_hash = metadata.get("source_pdf_sha256")
    local_page = metadata.get("fixture_pdf_page_index_1_based")
    source_page = metadata.get("source_pdf_page_index_1_based")
    if (
        not isinstance(source_pdf, str)
        or not source_pdf
        or not isinstance(source_hash, str)
        or not re.fullmatch(r"[0-9a-f]{64}", source_hash)
        or isinstance(local_page, bool)
        or not isinstance(local_page, int)
        or local_page < 1
        or isinstance(source_page, bool)
        or not isinstance(source_page, int)
        or source_page < 1
    ):
        raise GeometryError("provenance_mismatch", "successful preprocessing metadata has incomplete source provenance", fixture_id=fixture_id)
    # The preprocessing metadata is the provenance declaration, but it is not
    # evidence that the declared source still exists or is unchanged.  Anchor
    # relative declarations to the metadata file so geometry does not depend
    # on the caller's current working directory.
    source_pdf_path = Path(source_pdf)
    if not source_pdf_path.is_absolute():
        source_pdf_path = metadata_path.parent / source_pdf_path
    source_pdf_path = source_pdf_path.resolve()
    if not source_pdf_path.is_file() or not os.access(source_pdf_path, os.R_OK):
        raise GeometryError(
            "provenance_mismatch",
            f"declared source PDF is not a readable regular file: {source_pdf_path}",
            fixture_id=fixture_id,
        )
    try:
        actual_source_hash = _sha256(source_pdf_path)
    except OSError as exc:
        raise GeometryError(
            "provenance_mismatch",
            f"declared source PDF cannot be hashed: {source_pdf_path}: {exc}",
            fixture_id=fixture_id,
        ) from exc
    if actual_source_hash != source_hash:
        raise GeometryError(
            "provenance_mismatch",
            f"declared source PDF hash does not match metadata: {source_pdf_path}",
            fixture_id=fixture_id,
        )
    pages = metadata.get("pages")
    output_files = metadata.get("output_files")
    if not isinstance(pages, list) or not pages or not isinstance(output_files, dict):
        raise GeometryError("input_schema_invalid", "successful preprocessing metadata has no valid pages/output_files", fixture_id=fixture_id)
    declared_dpi = metadata.get("dpi")
    if isinstance(declared_dpi, bool) or not isinstance(declared_dpi, int) or declared_dpi <= 0:
        raise GeometryError("input_schema_invalid", "preprocessing dpi must be a positive integer", fixture_id=fixture_id)

    parsed_pages: list[_PreprocessedPage] = []
    for index, record in enumerate(pages):
        if not isinstance(record, dict):
            raise GeometryError("input_schema_invalid", f"page {index} is not an object", fixture_id=fixture_id)
        side = record.get("side")
        output_path = record.get("output_path")
        width = record.get("width_px")
        height = record.get("height_px")
        blank = record.get("blank")
        if (
            not isinstance(side, str)
            or not side
            or not isinstance(output_path, str)
            or not output_path
            or isinstance(width, bool)
            or not isinstance(width, int)
            or width <= 0
            or isinstance(height, bool)
            or not isinstance(height, int)
            or height <= 0
            or not isinstance(blank, bool)
        ):
            raise GeometryError("input_schema_invalid", f"page {index} has invalid side/path/dimensions/blank fields", fixture_id=fixture_id)
        if output_files.get(side) != output_path:
            raise GeometryError("provenance_mismatch", f"page {side!r} is not associated with its declared output file", fixture_id=fixture_id)
        image_path = (directory / output_path).resolve()
        try:
            image_path.relative_to(directory)
        except ValueError as exc:
            raise GeometryError("provenance_mismatch", f"page {side!r} output path escapes preprocessing directory", fixture_id=fixture_id) from exc
        if not image_path.is_file():
            raise GeometryError("image_missing", f"metadata-listed image is missing: {image_path}", fixture_id=fixture_id)
        try:
            with Image.open(image_path) as image:
                actual_dimensions = image.size
                image.verify()
        except (OSError, SyntaxError) as exc:
            raise GeometryError("image_missing", f"metadata-listed image cannot be opened: {image_path}: {exc}", fixture_id=fixture_id) from exc
        if actual_dimensions != (width, height):
            raise GeometryError(
                "image_dimension_mismatch",
                f"{image_path} is {actual_dimensions}, metadata declares {(width, height)}",
                fixture_id=fixture_id,
            )
        parsed_pages.append(_PreprocessedPage(side, image_path, width, height, blank, record))

    return _PreprocessedInput(
        directory=directory,
        metadata_path=metadata_path,
        metadata=metadata,
        metadata_digest=_sha256(metadata_path),
        pages=tuple(parsed_pages),
    )


def _parse_int(value: str) -> int:
    if not _INTEGER.fullmatch(value):
        raise ValueError(value)
    return int(value)


def _parse_confidence(value: str) -> float:
    if not _DECIMAL.fullmatch(value):
        raise ValueError(value)
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(value)
    return parsed


def _row_error(code: str, row: int, reason: str) -> dict[str, Any]:
    return {"code": code, "source_row": row, "reason": reason}


def parse_tsv_rows(tsv: str, width: int, height: int) -> tuple[list[_Token], list[dict[str, Any]]]:
    """Admit TSV rows using the closed, deterministic Slice 2 token table."""

    reader = csv.reader(io.StringIO(tsv), delimiter="\t")
    try:
        header = next(reader)
    except StopIteration:
        return [], [_row_error("tsv_invalid", 0, "TSV is empty; expected the exact header")]
    if tuple(header) != TSV_HEADER:
        return [], [_row_error("tsv_invalid", 0, "TSV header differs from the exact 12-column contract")]

    tokens: list[_Token] = []
    errors: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for source_row, row in enumerate(reader, start=1):
        if not row or all(value == "" for value in row):
            continue
        if len(row) != len(TSV_HEADER):
            errors.append(_row_error("tsv_invalid", source_row, "TSV row does not contain 12 columns"))
            continue
        try:
            level, page_num, block_num, par_num, line_num, word_num = (
                _parse_int(value) for value in row[:6]
            )
            x, y, token_width, token_height = (_parse_int(value) for value in row[6:10])
            confidence = _parse_confidence(row[10])
        except (TypeError, ValueError):
            errors.append(_row_error("tsv_invalid", source_row, "hierarchy, geometry, or confidence is not valid decimal syntax"))
            continue
        if not 1 <= level <= 5 or min(page_num, block_num, par_num, line_num, word_num) < 0:
            errors.append(_row_error("tsv_invalid", source_row, "hierarchy values are outside the declared integer domain"))
            continue
        text = row[11]
        if confidence == -1 or not text.strip():
            continue
        if not 0 <= confidence <= 100:
            errors.append(_row_error("tsv_invalid", source_row, "non-sentinel confidence is outside [0, 100]"))
            continue
        if token_width <= 0 or token_height <= 0 or x < 0 or y < 0 or x + token_width > width or y + token_height > height:
            errors.append(_row_error("geometry_invalid", source_row, "token rectangle is non-positive or outside the image"))
            continue
        token = _Token(
            source_row,
            text,
            confidence,
            level,
            page_num,
            block_num,
            par_num,
            line_num,
            word_num,
            x,
            y,
            token_width,
            token_height,
        )
        if token.payload() not in seen:
            seen.add(token.payload())
            tokens.append(token)
    return tokens, errors


def _median(values: Iterable[float]) -> float | None:
    values = list(values)
    return float(median(values)) if values else None


def _adjusted_center_y(token: _Token, slope: float) -> float:
    """Measure a token against a page baseline with the observed slope removed."""

    return token.center_y - slope * token.x


def _horizontal_gap_limit(tokens: Sequence[_Token]) -> float:
    """Return the largest gap admissible inside one observed physical line.

    A baseline model may only join tokens that also form a continuous visible
    horizontal region.  Two token groups separated by a column gutter or a
    large blank region must remain separate even if a slope happens to make
    their adjusted vertical centers coincide.  The limit is derived from the
    observed token widths, so it remains in the page's pixel coordinate system
    and does not introduce a document-specific threshold.
    """

    widths = [token.width for token in tokens if token.width > 0]
    return max(1.0, 2.0 * median(widths)) if widths else 1.0


def _split_horizontal_regions(
    bands: Sequence[Sequence[_Token]], gap_limit: float
) -> list[list[_Token]]:
    """Split bands using covered extent, with a guard for bridge-only boxes."""

    regions: list[list[_Token]] = []
    for band in bands:
        ordered = sorted(band, key=lambda token: (token.x, token.source_row))
        supported_bridge_ids = _supported_bridge_ids(ordered, gap_limit)
        current: list[_Token] = []
        covered_right: int | None = None
        for token in ordered:
            if current and (
                covered_right is not None and token.x - covered_right > gap_limit
            ):
                regions.append(current)
                current = []
            current.append(token)
            if not _is_oversized(token, gap_limit) or id(token) in supported_bridge_ids:
                covered_right = max(covered_right or token.x1, token.x1)
            elif covered_right is None:
                # An unsupported wide box may start a region, but its full
                # extent is not allowed to bridge a later ordinary group.
                covered_right = token.x
        if current:
            regions.append(current)
    return regions


def _horizontally_adjacent(left: _Token, right: _Token, gap_limit: float) -> bool:
    """Return whether two tokens provide horizontal continuity evidence."""

    if left.x == right.x:
        # Same-column tokens do not establish that two nearby vertical boxes
        # belong to one row; this preserves stacked-row ambiguity.
        return False
    first, second = sorted((left, right), key=lambda token: (token.x, token.source_row))
    return second.x - first.x1 <= gap_limit


def _is_oversized(token: _Token, gap_limit: float) -> bool:
    """Classify boxes wider than three page-local median token widths.

    ``gap_limit`` is two median widths, so the additional half-gap keeps
    ordinary wide words in the connectivity evidence while isolating boxes
    whose extent is materially abnormal.
    """

    return token.width > gap_limit + gap_limit / 2


def _supported_bridge_ids(tokens: Sequence[_Token], gap_limit: float) -> set[int]:
    """Return wide boxes supported by ordinary tokens on both sides."""

    ordinary = [token for token in tokens if not _is_oversized(token, gap_limit)]
    components: list[list[_Token]] = []
    for token in ordinary:
        if components and token.x - components[-1][-1].x1 <= gap_limit:
            components[-1].append(token)
        else:
            components.append([token])
    supported: set[int] = set()
    for left_component, right_component in zip(components, components[1:]):
        left = left_component[-1]
        right = right_component[0]
        if right.x - left.x1 <= gap_limit:
            continue
        for token in tokens:
            if (
                _is_oversized(token, gap_limit)
                and token.x <= left.x1
                and token.x1 >= right.x
                and len(left_component) >= 2
                and len(right_component) >= 2
            ):
                supported.add(id(token))
    return supported


def _horizontal_candidate_supported(
    band: Sequence[_Token], token: _Token, gap_limit: float
) -> bool:
    """Keep guarded region boundaries consistent during final assignment."""

    combined = sorted((*band, token), key=lambda item: (item.x, item.source_row))
    ordinary = [item for item in combined if not _is_oversized(item, gap_limit)]
    supported_bridge_ids = _supported_bridge_ids(combined, gap_limit)
    for index, (left, right) in enumerate(zip(ordinary, ordinary[1:])):
        if right.x - left.x1 <= gap_limit:
            continue
        bridge_tokens = [
            item
            for item in combined
            if _is_oversized(item, gap_limit) and item.x <= left.x1 and item.x1 >= right.x
        ]
        if bridge_tokens and not any(id(item) in supported_bridge_ids for item in bridge_tokens):
            return False
    return True


def _line_bands(tokens: Sequence[_Token], tolerance: int, slope: float) -> list[list[_Token]]:
    ordered = sorted(
        tokens,
        key=lambda token: (_adjusted_center_y(token, slope), token.x, token.source_row),
    )
    bands: list[list[_Token]] = []
    gap_limit = _horizontal_gap_limit(tokens)
    for token in ordered:
        if bands:
            current_median = median(
                _adjusted_center_y(item, slope) for item in bands[-1]
            )
            median_support = abs(_adjusted_center_y(token, slope) - current_median) <= tolerance
            neighbor_support = any(
                abs(_adjusted_center_y(token, slope) - _adjusted_center_y(item, slope)) <= tolerance
                and _horizontally_adjacent(item, token, gap_limit)
                for item in bands[-1]
            )
            if median_support or neighbor_support:
                bands[-1].append(token)
                continue
        bands.append([token])
    return _split_horizontal_regions(bands, _horizontal_gap_limit(tokens))


def _estimate_baseline_slope(tokens: Sequence[_Token], tolerance: int) -> float:
    """Choose a slope only when coordinate evidence supports multiple rows.

    The source images retain visible page skew because Slice 1 deliberately did
    not deskew them. A horizontal band therefore fragments a single printed
    line as its baseline rises or falls across the page. This bounded search
    models that observed geometry without changing the image or consulting
    Tesseract's line labels. A candidate is admissible only if it preserves at
    least two multi-token horizontal regions; this prevents a slope from
    collapsing distinct page regions into one synthetic row. Ties prefer the
    smallest absolute slope.
    """

    best_slope = 0.0
    best_score = -1
    best_abs_slope = float("inf")
    zero_slope_bands = _line_bands(tokens, tolerance, 0.0)
    zero_slope_score = sum(len(band) * (len(band) - 1) // 2 for band in zero_slope_bands)
    for slope_milli in range(-100, 101):
        slope = slope_milli / 1000
        bands = _line_bands(tokens, tolerance, slope)
        if slope != 0.0 and (
            len(bands) < 2 or any(len(band) < 2 for band in bands)
        ):
            continue
        cohesion_score = sum(len(band) * (len(band) - 1) // 2 for band in bands)
        if slope != 0.0 and cohesion_score <= zero_slope_score:
            continue
        if cohesion_score > best_score or (
            cohesion_score == best_score and abs(slope) < best_abs_slope
        ):
            best_slope = slope
            best_score = cohesion_score
            best_abs_slope = abs(slope)
    return best_slope


def group_physical_lines(tokens: Sequence[_Token]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Group observed token rows without consulting Tesseract line IDs."""

    if not tokens:
        return [], [], {
            "token_height_median_px": None,
            "tolerance_formula": "max(1, floor(token_height_median_px / 4 + 0.5))",
            "tolerance_px": None,
            "horizontal_gap_formula": "2 * median(token_width_px); region extent is cumulative and unsupported oversized bridge boxes split",
            "horizontal_gap_limit_px": None,
            "baseline_slope_formula": "bounded coordinate cohesion search from -0.100 to 0.100 px/px in 0.001 px/px steps; nonzero candidates require >=2 multi-token continuous bands and improved cohesion",
            "baseline_slope_px_per_px": 0.0,
            "line_height_median_px": None,
            "line_gaps": [],
        }
    token_height_median = float(median(token.height for token in tokens if token.height > 0))
    tolerance = max(1, math.floor(token_height_median / 4 + 0.5))
    baseline_slope = _estimate_baseline_slope(tokens, tolerance)
    bands = _line_bands(tokens, tolerance, baseline_slope)
    horizontal_gap_limit = _horizontal_gap_limit(tokens)
    ordered_bands = sorted(
        enumerate(bands),
        key=lambda pair: (
            median(_adjusted_center_y(item, baseline_slope) for item in pair[1]),
            min(item.x for item in pair[1]),
            pair[0],
        ),
    )
    line_ids = {band_index: f"line-{ordinal:04d}" for ordinal, (band_index, _band) in enumerate(ordered_bands, start=1)}
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
                            _adjusted_center_y(token, baseline_slope)
                            - median(_adjusted_center_y(item, baseline_slope) for item in band)
                        ) <= tolerance
                        or any(
                            abs(_adjusted_center_y(token, baseline_slope) - _adjusted_center_y(item, baseline_slope)) <= tolerance
                            and _horizontally_adjacent(item, token, horizontal_gap_limit)
                            for item in band
                            if item is not token
                        )
                    )
                )
                or (
                    abs(
                        _adjusted_center_y(token, baseline_slope)
                        - median(_adjusted_center_y(item, baseline_slope) for item in band)
                    ) <= tolerance
                    and min(item.x for item in band) <= token.x <= max(item.x1 for item in band)
                    and _horizontal_candidate_supported(band, token, horizontal_gap_limit)
                )
            )
        ]
    assignments: dict[str, list[_Token]] = {line_id: [] for line_id in line_ids.values()}
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

    ambiguous_tokens_by_line: dict[str, list[_Token]] = {line_id: [] for line_id in line_ids.values()}
    has_unassigned_token = False
    for token in tokens:
        token_candidates = candidates[id(token)]
        if len(token_candidates) > 1:
            for candidate_line_id in token_candidates:
                ambiguous_tokens_by_line[candidate_line_id].append(token)
        elif not token_candidates:
            has_unassigned_token = True

    affected_line_ids = {
        line_id for line_id, unresolved_tokens in ambiguous_tokens_by_line.items() if unresolved_tokens
    }
    lines: list[dict[str, Any]] = []
    for band_index, band in ordered_bands:
        line_id = line_ids[band_index]
        assigned = sorted(assignments[line_id], key=lambda token: (token.x, token.y, token.source_row))
        # An ambiguous token remains evidence for every candidate line.  This
        # keeps numeric bounds conservative while abstaining from a falsely
        # precise line height or inter-line distance below.
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
        line_height = (
            None
            if has_unassigned_token or line_id in affected_line_ids
            else bounds["bottom_px"] - bounds["top_px"]
        )
        line = {
            "line_id": line_id,
            "token_ids": [f"token-{token.source_row:04d}" for token in assigned],
            "unresolved_token_source_rows": [item["token_source_row"] for item in unresolved if line_id in item["candidate_line_ids"]],
            **bounds,
            "line_height_px": line_height,
            "median_center_y_px": float(median(token.center_y for token in band)),
        }
        lines.append(line)
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
        "token_height_median_px": token_height_median,
        "tolerance_formula": "max(1, floor(token_height_median_px / 4 + 0.5))",
        "tolerance_px": tolerance,
        "horizontal_gap_formula": "2 * median(token_width_px); region extent is cumulative and unsupported oversized bridge boxes split",
        "horizontal_gap_limit_px": _horizontal_gap_limit(tokens),
        "baseline_slope_formula": "bounded coordinate cohesion search from -0.100 to 0.100 px/px in 0.001 px/px steps; nonzero candidates require >=2 multi-token continuous bands and improved cohesion",
        "baseline_slope_px_per_px": baseline_slope,
        "line_height_median_px": (
            None
            if has_unassigned_token or affected_line_ids
            else _median(line_heights)
        ),
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


def _token_record(token: _Token, candidate_line_ids: Sequence[str]) -> dict[str, Any]:
    return {
        "token_id": f"token-{token.source_row:04d}",
        "source_row": token.source_row,
        "text": token.text,
        "confidence": token.confidence,
        "x_px": token.x,
        "y_px": token.y,
        "width_px": token.width,
        "height_px": token.height,
        "right_px": token.x1,
        "bottom_px": token.y1,
        "coordinate_system": {"origin": "top-left", "units": "px"},
        "physical_line_id": candidate_line_ids[0] if len(candidate_line_ids) == 1 else None,
        "candidate_line_ids": list(candidate_line_ids),
        "evidence_only": {
            "tesseract_block_num": token.block_num,
            "tesseract_par_num": token.par_num,
            "tesseract_line_num": token.line_num,
            "tesseract_word_num": token.word_num,
        },
    }


def _page_geometry(
    page: _PreprocessedPage,
    tsv: str,
    engine: Mapping[str, Any],
    provenance: Mapping[str, Any],
) -> dict[str, Any]:
    tokens, row_errors = parse_tsv_rows(tsv, page.width, page.height)
    lines, unresolved, measurements = group_physical_lines(tokens)
    page_errors = sorted({item["code"] for item in row_errors}, key=GEOMETRY_ERROR_CODES.index)
    page_uncertainties = sorted(
        {item["code"] for item in unresolved}, key=GEOMETRY_UNCERTAINTY_CODES.index
    )
    header_is_valid = tuple(tsv.splitlines()[0].split("\t")) == TSV_HEADER if tsv.splitlines() else False
    if not tokens and not page.blank and header_is_valid:
        page_uncertainties.append("no_tokens_on_declared_nonblank_page")
    page_uncertainties = sorted(set(page_uncertainties), key=GEOMETRY_UNCERTAINTY_CODES.index)
    token_line_candidates: dict[int, list[str]] = {}
    for line in lines:
        for token_id in line["token_ids"]:
            token_line_candidates[int(token_id.removeprefix("token-"))] = [line["line_id"]]
    # Recompute candidates from the serialized line records so the token record
    # remains stable even when an ambiguity is present.
    for item in unresolved:
        token_line_candidates[item["token_source_row"]] = item["candidate_line_ids"]
    token_records = [
        _token_record(token, token_line_candidates.get(token.source_row, []))
        for token in tokens
    ]
    blocks: dict[int, list[dict[str, Any]]] = {}
    for token in token_records:
        block_id = token["evidence_only"]["tesseract_block_num"]
        blocks.setdefault(block_id, []).append(token)
    block_evidence = [
        {
            "tesseract_block_num": block_id,
            "token_ids": [token["token_id"] for token in block_tokens],
            "left_px": min(token["x_px"] for token in block_tokens),
            "right_px": max(token["right_px"] for token in block_tokens),
            "top_px": min(token["y_px"] for token in block_tokens),
            "bottom_px": max(token["bottom_px"] for token in block_tokens),
            "evidence_only": True,
        }
        for block_id, block_tokens in sorted(blocks.items())
    ]
    status = FAILURE if page_errors else UNCERTAIN if page_uncertainties else SUCCESS
    return {
        "side": page.side,
        "image_path": page.record["output_path"],
        "width_px": page.width,
        "height_px": page.height,
        "blank": page.blank,
        "provenance": {
            "fixture_id": provenance["fixture_id"],
            "fixture_pdf_page_index_1_based": provenance["fixture_pdf_page_index_1_based"],
            "source_pdf_page_index_1_based": provenance["source_pdf_page_index_1_based"],
            "dpi": provenance["dpi"],
            "metadata_order": provenance["metadata_order"],
            "source_stage": page.record.get("source_stage"),
            "source_rect_px": page.record.get("source_rect_px"),
        },
        "coordinate_system": {"origin": "top-left", "units": "px"},
        "status": status,
        "errors": page_errors,
        "error_details": row_errors,
        "uncertainties": page_uncertainties,
        "tokens": token_records,
        "physical_lines": lines,
        "block_evidence": block_evidence,
        "measurements": measurements,
        "engine": dict(engine),
    }


def _engine_record() -> dict[str, Any]:
    command = str(getattr(pytesseract.pytesseract, "tesseract_cmd", "tesseract"))
    try:
        version = str(pytesseract.get_tesseract_version()).strip()
    except Exception as exc:
        raise GeometryError("tesseract_invocation", f"cannot query Tesseract version: {exc}") from exc
    return {
        "executable": command,
        "version": version,
        "language": "eng",
        "config": "--psm 6",
        "output": "TSV",
    }


def _annotate(page: _PreprocessedPage, geometry: Mapping[str, Any], destination: Path) -> None:
    with Image.open(page.image_path) as source:
        image = source.convert("RGB")
        draw = ImageDraw.Draw(image)
        for token in geometry["tokens"]:
            x0, y0 = token["x_px"], token["y_px"]
            x1, y1 = token["right_px"], token["bottom_px"]
            draw.rectangle((x0, y0, x1, y1), outline=(40, 120, 220), width=2)
        for line in geometry["physical_lines"]:
            if any(line[field] is None for field in ("left_px", "top_px", "right_px", "bottom_px")):
                continue
            draw.rectangle(
                (line["left_px"], line["top_px"], line["right_px"], line["bottom_px"]),
                outline=(220, 70, 40),
                width=2,
            )
        for block in geometry["block_evidence"]:
            draw.rectangle(
                (block["left_px"], block["top_px"], block["right_px"], block["bottom_px"]),
                outline=(40, 170, 80),
                width=1,
            )
        image.save(destination, format="PNG")
        if image.size != (page.width, page.height):
            raise GeometryError("annotation_failure", f"annotation dimensions changed for {page.side}")


def _safe_remove(path: Path) -> bool:
    try:
        if not os.path.lexists(path):
            return True
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
        return not os.path.lexists(path)
    except OSError:
        return False


def _recognized_publication(output_dir: Path) -> tuple[bool, str | None]:
    """Return whether ``output_dir`` is a complete geometry publication.

    Pre-publication failures are allowed to remove only an artifact that this
    process can prove it owns.  In particular, a symlink, malformed JSON, an
    unexpected top-level member, or an annotation path escaping the
    annotations directory is user data outside that proof and must remain
    untouched.
    """

    if not os.path.lexists(output_dir):
        return False, None
    if output_dir.is_symlink() or not output_dir.is_dir():
        return False, None
    try:
        if {path.name for path in output_dir.iterdir()} != {"geometry.json", "annotations"}:
            return False, None
        geometry_path = output_dir / "geometry.json"
        annotations_dir = output_dir / "annotations"
        if geometry_path.is_symlink() or not geometry_path.is_file():
            return False, None
        if annotations_dir.is_symlink() or not annotations_dir.is_dir():
            return False, None

        # A symlink or non-file anywhere below annotations could make an
        # apparently safe recursive deletion reach outside the requested
        # publication directory.  Keep the complete inventory so declared
        # files can be compared with every descendant before deletion.
        annotation_members = list(annotations_dir.rglob("*"))
        if any(path.is_symlink() or not path.is_file() for path in annotation_members):
            return False, None

        with geometry_path.open(encoding="utf-8") as handle:
            geometry = json.load(handle)
        if not isinstance(geometry, dict):
            return False, None
        if geometry.get("schema") != GEOMETRY_SCHEMA:
            return False, None
        fixture_id = geometry.get("fixture_id")
        if not isinstance(fixture_id, str) or not fixture_id:
            return False, None
        if geometry.get("status") not in (SUCCESS, UNCERTAIN):
            return False, None
        annotation_paths = geometry.get("annotation_paths")
        if not isinstance(annotation_paths, list) or not annotation_paths:
            return False, None
        declared_annotation_files: set[Path] = set()
        for relative_path in annotation_paths:
            if not isinstance(relative_path, str):
                return False, None
            relative = Path(relative_path)
            if relative.is_absolute() or ".." in relative.parts:
                return False, None
            candidate = output_dir / relative_path
            try:
                candidate.relative_to(annotations_dir)
            except ValueError:
                return False, None
            if candidate.is_symlink() or not candidate.is_file():
                return False, None
            declared_annotation_files.add(candidate.relative_to(output_dir))
        if len(declared_annotation_files) != len(annotation_paths):
            return False, None
        actual_annotation_files = {
            path.relative_to(output_dir) for path in annotation_members
        }
        if actual_annotation_files != declared_annotation_files:
            return False, None
        return True, fixture_id
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return False, None


def _invalidate_publication(output_dir: Path, fixture_id: str | None) -> None:
    """Remove a proven publication or durably mark it as non-consumable.

    This is intentionally called only for input/provenance failures that occur
    before staging.  A failed removal falls back to an atomic failure payload;
    if that payload cannot be verified, the caller reports cleanup_unverified.
    """

    recognized, published_fixture_id = _recognized_publication(output_dir)
    if not recognized:
        return
    if _safe_remove(output_dir):
        return

    invalidation = _error_payload(
        published_fixture_id or fixture_id,
        "cleanup_unverified",
        "previous geometry output could not be removed and was marked non-consumable",
    )
    geometry_path = output_dir / "geometry.json"
    temporary_path: Path | None = None
    try:
        fd, temporary_name = tempfile.mkstemp(
            prefix=".geometry-invalid-",
            suffix=".json",
            dir=output_dir,
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(invalidation, handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, geometry_path)
        temporary_path = None
        with geometry_path.open(encoding="utf-8") as handle:
            verified = json.load(handle)
        if not (
            isinstance(verified, dict)
            and verified.get("schema") == GEOMETRY_SCHEMA
            and verified.get("status") == FAILURE
            and verified.get("errors") == ["cleanup_unverified"]
        ):
            raise OSError("failure invalidation did not verify")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        if temporary_path is not None:
            _safe_remove(temporary_path)
        raise GeometryError(
            "cleanup_unverified",
            f"previous geometry output could not be removed or invalidated: {output_dir}: {exc}",
            fixture_id=fixture_id or published_fixture_id,
        ) from exc


def _remove_staging_or_raise(staging: Path, error: BaseException, fixture_id: str) -> None:
    """Turn an unverifiable staging cleanup into the declared failure code."""

    if _safe_remove(staging):
        return
    if isinstance(error, GeometryError):
        context = f"{error.code}: {error.reason}"
    else:
        context = f"{type(error).__name__}: {error}"
    raise GeometryError(
        "cleanup_unverified",
        f"staging cleanup could not be verified after {context}: {staging}",
        fixture_id=fixture_id,
    ) from error


def _publish(staging: Path, output_dir: Path, fixture_id: str) -> None:
    # Preserve the final path itself when checking for a symlink. ``resolve``
    # would follow a user-owned alias before the safety check.
    output_dir = Path(os.path.abspath(output_dir))
    parent = output_dir.parent
    if os.path.lexists(output_dir) and (output_dir.is_symlink() or not output_dir.is_dir()):
        raise GeometryError("publication_failure", f"geometry output is not a regular directory: {output_dir}", fixture_id=fixture_id)
    if os.path.lexists(output_dir):
        recognized, published_fixture_id = _recognized_publication(output_dir)
        if not recognized or published_fixture_id != fixture_id:
            raise GeometryError(
                "publication_failure",
                f"existing geometry output is not an owned publication for {fixture_id}: {output_dir}",
                fixture_id=fixture_id,
            )
    parent.mkdir(parents=True, exist_ok=True)
    previous: Path | None = None
    try:
        if os.path.lexists(output_dir):
            previous = Path(tempfile.mkdtemp(prefix=f".{fixture_id}.geometry-previous-", dir=parent))
            previous.rmdir()
            os.replace(output_dir, previous)
        os.replace(staging, output_dir)
        recognized, published_fixture_id = _recognized_publication(output_dir)
        if not recognized or published_fixture_id != fixture_id:
            raise OSError("published geometry inventory is incomplete or has the wrong fixture")
        if previous is not None and not _safe_remove(previous):
            raise GeometryError("cleanup_unverified", f"previous geometry output cleanup could not be verified: {previous}", fixture_id=fixture_id)
    except GeometryError as exc:
        if os.path.lexists(output_dir) and output_dir != staging and not _safe_remove(output_dir):
            raise GeometryError("cleanup_unverified", f"publication failed and new output cleanup failed: {output_dir}", fixture_id=fixture_id) from exc
        if previous is not None and os.path.lexists(previous):
            try:
                os.replace(previous, output_dir)
            except OSError as restore_exc:
                raise GeometryError("cleanup_unverified", f"publication failed and restoration failed: {restore_exc}", fixture_id=fixture_id) from restore_exc
        raise
    except OSError as exc:
        if os.path.lexists(output_dir) and not _safe_remove(output_dir):
            raise GeometryError("cleanup_unverified", f"publication failed and new output cleanup failed: {output_dir}", fixture_id=fixture_id) from exc
        if previous is not None and os.path.lexists(previous):
            try:
                os.replace(previous, output_dir)
            except OSError as restore_exc:
                raise GeometryError("cleanup_unverified", f"publication failed and restoration failed: {restore_exc}", fixture_id=fixture_id) from restore_exc
        raise GeometryError("publication_failure", str(exc), fixture_id=fixture_id) from exc


def run_geometry(preprocessed_dir: Path, output_dir: Path) -> dict[str, Any]:
    """Run one fixture's geometry probe and publish one complete artifact set."""

    fixture_id: str | None = None
    try:
        prepared = _load_input(preprocessed_dir)
        fixture_id = str(prepared.metadata["fixture_id"])
        engine = _engine_record()
        page_records: list[dict[str, Any]] = []
        page_provenance = {
            "fixture_id": fixture_id,
            "fixture_pdf_page_index_1_based": prepared.metadata.get("fixture_pdf_page_index_1_based"),
            "source_pdf_page_index_1_based": prepared.metadata.get("source_pdf_page_index_1_based"),
            "dpi": prepared.metadata.get("dpi"),
            "metadata_order": [page.side for page in prepared.pages],
        }
        for page in prepared.pages:
            try:
                with Image.open(page.image_path) as image:
                    tsv = pytesseract.image_to_data(
                        image,
                        lang="eng",
                        config="--psm 6",
                        output_type=Output.STRING,
                    )
            except Exception as exc:
                raise GeometryError("tesseract_invocation", f"Tesseract failed on {page.side}: {exc}", fixture_id=fixture_id) from exc
            page_records.append(_page_geometry(page, tsv, engine, page_provenance))

        errors = sorted({code for page in page_records for code in page["errors"]}, key=GEOMETRY_ERROR_CODES.index)
        uncertainties = sorted({code for page in page_records for code in page["uncertainties"]}, key=GEOMETRY_UNCERTAINTY_CODES.index)
        status = FAILURE if errors else UNCERTAIN if uncertainties else SUCCESS
        root: dict[str, Any] = {
            "schema": GEOMETRY_SCHEMA,
            "status": status,
            "fixture_id": fixture_id,
            "errors": errors,
            "error_details": [detail for page in page_records for detail in page["error_details"]],
            "uncertainties": uncertainties,
            "coordinate_system": {"origin": "top-left", "units": "px"},
            "engine": engine,
            "grouping": {
                "rule": "coordinate rows use adjusted center_y tolerance with horizontal-neighbor support, split gaps beyond cumulative covered extent, guard unsupported oversized bridge boxes, and admit nonzero slope only for at least two multi-token continuous bands with improved cohesion",
                "line_ids": "ordered by band median center_y, leftmost x0, creation ordinal",
            },
            "provenance": {
                "fixture_id": fixture_id,
                "source_pdf": prepared.metadata.get("source_pdf"),
                "source_pdf_sha256": prepared.metadata.get("source_pdf_sha256"),
                "fixture_pdf_page_index_1_based": prepared.metadata.get("fixture_pdf_page_index_1_based"),
                "source_pdf_page_index_1_based": prepared.metadata.get("source_pdf_page_index_1_based"),
                "preprocessing_metadata_path": str(prepared.metadata_path),
                "preprocessing_schema": prepared.metadata.get("schema"),
                "preprocessing_metadata_sha256": prepared.metadata_digest,
                "preprocessing_metadata_digest": _json_digest(prepared.metadata),
                "dpi": prepared.metadata.get("dpi"),
                "transforms": prepared.metadata.get("transforms"),
                "result": prepared.metadata.get("result"),
            },
            "pages": page_records,
            "annotation_paths": [f"annotations/{page.side}.png" for page in prepared.pages],
            "authority": {
                "layout": "scanned page pixels",
                "lexical": "raw/browser-extracted text remains authoritative outside this artifact",
                "ocr": "non-authoritative locating evidence only",
                "structure": "physical rows are observed geometry, not inferred document structure",
            },
        }
        if errors:
            first_error = errors[0]
            raise GeometryError(
                first_error,
                f"geometry extraction produced {first_error} rows; no successful artifact is published",
                fixture_id=fixture_id,
            )

        output_dir = Path(os.path.abspath(output_dir))
        try:
            # Parent creation is part of publication, not input preparation.
            # Convert a regular-file parent (or another filesystem refusal)
            # into the same structured failure contract as later publication
            # operations, before staging can be advertised or leaked.
            output_dir.parent.mkdir(parents=True, exist_ok=True)
            staging = Path(tempfile.mkdtemp(prefix=f".{fixture_id}.geometry-staging-", dir=output_dir.parent))
        except OSError as exc:
            raise GeometryError("publication_failure", str(exc), fixture_id=fixture_id) from exc
        try:
            (staging / "annotations").mkdir()
            for page, record in zip(prepared.pages, page_records):
                _annotate(page, record, staging / "annotations" / f"{page.side}.png")
            (staging / "geometry.json").write_text(
                json.dumps(root, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            reloaded = json.loads((staging / "geometry.json").read_text(encoding="utf-8"))
            if reloaded != root:
                raise GeometryError("serialization_failure", "serialized geometry did not reload identically", fixture_id=fixture_id)
            for page in prepared.pages:
                with Image.open(staging / "annotations" / f"{page.side}.png") as image:
                    if image.size != (page.width, page.height):
                        raise GeometryError("annotation_failure", f"annotation dimensions do not match {page.side}", fixture_id=fixture_id)
            _publish(staging, output_dir, fixture_id)
            return root
        except GeometryError as exc:
            _remove_staging_or_raise(staging, exc, fixture_id)
            raise
        except (OSError, TypeError, ValueError) as exc:
            _remove_staging_or_raise(staging, exc, fixture_id)
            raise GeometryError("serialization_failure", str(exc), fixture_id=fixture_id) from exc
    except GeometryError as exc:
        if exc.code in {"input_schema_invalid", "preprocessing_not_success", "provenance_mismatch"}:
            try:
                _invalidate_publication(Path(os.path.abspath(output_dir)), exc.fixture_id or fixture_id)
            except GeometryError as cleanup_exc:
                exc = cleanup_exc
        payload = _error_payload(exc.fixture_id or fixture_id, exc.code, exc.reason)
        return payload


__all__ = [
    "GEOMETRY_ERROR_CODES",
    "GEOMETRY_SCHEMA",
    "GEOMETRY_UNCERTAINTY_CODES",
    "GeometryError",
    "group_physical_lines",
    "parse_tsv_rows",
    "run_geometry",
]
