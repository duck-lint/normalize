"""Identity-complete comparison helpers for Slice 2 geometry observations.

The production geometry payload uses generated token and line labels for
serialization.  This helper deliberately does not use those labels as
identity: token identity is the fixture/side/source-row tuple, while line
labels are reconstructed from observable geometric order.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import SimpleNamespace
from typing import Any


def token_identity(fixture_id: str, side: str, source_row: int) -> tuple[str, str, int]:
    """Return the stable identity contract for an admitted TSV token."""

    return fixture_id, side, source_row


def _source_row(token_id: str) -> int:
    return int(token_id.removeprefix("token-"))


def _line_sort_key(line: Mapping[str, Any]) -> tuple[Any, ...]:
    """Order generated lines by geometry, never by their generated ID."""

    def finite_or_inf(value: Any) -> float:
        return float("inf") if value is None else float(value)

    return (
        finite_or_inf(line.get("median_center_y_px")),
        finite_or_inf(line.get("top_px")),
        finite_or_inf(line.get("left_px")),
        finite_or_inf(line.get("right_px")),
        finite_or_inf(line.get("bottom_px")),
        tuple(sorted(line.get("token_ids", ()))),
        tuple(sorted(line.get("unresolved_token_source_rows", ()))),
    )


def _canonical_value(value: Any, line_labels: Mapping[str, str]) -> Any:
    """Replace incidental line IDs recursively while preserving structure."""

    if isinstance(value, str) and value in line_labels:
        return line_labels[value]
    if isinstance(value, Mapping):
        return tuple(
            (key, _canonical_value(item, line_labels))
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(_canonical_value(item, line_labels) for item in value)
    return value


def canonical_geometry_state(
    fixture_id: str,
    side: str,
    tokens: Sequence[Any],
    lines: Sequence[Mapping[str, Any]],
    unresolved: Sequence[Mapping[str, Any]],
    measurements: Mapping[str, Any],
) -> tuple[Any, ...]:
    """Canonicalize the complete observable assignment state.

    The state includes every admitted token, resolved membership or absence,
    candidate-line sets, uncertainty code, token measurements, line members,
    line measurements, and page measurements.  Source-row identity is scoped
    by fixture and physical side, so duplicate text remains distinguishable.
    """

    ordered_lines = sorted(lines, key=_line_sort_key)
    line_labels = {
        line["line_id"]: f"physical-line-{index:04d}"
        for index, line in enumerate(ordered_lines, start=1)
    }

    resolved_by_row: dict[int, str] = {}
    line_members: dict[str, tuple[tuple[str, str, int], ...]] = {}
    for line in ordered_lines:
        members = tuple(
            sorted(
                token_identity(fixture_id, side, _source_row(token_id))
                for token_id in line.get("token_ids", ())
            )
        )
        line_members[line["line_id"]] = members
        for token_id in line.get("token_ids", ()):
            source_row = _source_row(token_id)
            if source_row in resolved_by_row:
                raise AssertionError(f"token source row assigned to multiple lines: {source_row}")
            resolved_by_row[source_row] = line["line_id"]

    unresolved_by_row = {item["token_source_row"]: item for item in unresolved}
    if len(unresolved_by_row) != len(unresolved):
        raise AssertionError("unresolved assignment rows must be unique")

    token_state = []
    for token in sorted(tokens, key=lambda item: item.source_row):
        source_row = token.source_row
        identity = token_identity(fixture_id, side, source_row)
        unresolved_item = unresolved_by_row.get(source_row)
        if unresolved_item is not None:
            candidate_ids = tuple(
                sorted(line_labels[line_id] for line_id in unresolved_item["candidate_line_ids"])
            )
            assignment = None
            uncertainty = unresolved_item["code"]
        else:
            line_id = resolved_by_row.get(source_row)
            candidate_ids = () if line_id is None else (line_labels[line_id],)
            assignment = None if line_id is None else line_labels[line_id]
            uncertainty = None

        token_state.append(
            (
                identity,
                token.text,
                assignment,
                candidate_ids,
                uncertainty,
                token.x,
                token.y,
                token.width,
                token.height,
                token.confidence,
            )
        )

    canonical_lines = []
    for line in ordered_lines:
        unresolved_members = tuple(
            sorted(token_identity(fixture_id, side, source_row) for source_row in line.get("unresolved_token_source_rows", ()))
        )
        canonical_lines.append(
            (
                line_labels[line["line_id"]],
                line_members[line["line_id"]],
                unresolved_members,
                tuple(
                    (key, _canonical_value(line.get(key), line_labels))
                    for key in (
                        "left_px",
                        "top_px",
                        "right_px",
                        "bottom_px",
                        "line_height_px",
                        "median_center_y_px",
                        "vertical_gap_to_next_px",
                    )
                ),
            )
        )

    canonical_measurements = _canonical_value(measurements, line_labels)
    return tuple(token_state), tuple(canonical_lines), canonical_measurements


def canonical_serialized_page_state(
    fixture_id: str,
    page: Mapping[str, Any],
) -> tuple[Any, ...]:
    """Apply the same oracle to one serialized geometry page."""

    tokens = [
        SimpleNamespace(
            source_row=token["source_row"],
            text=token["text"],
            confidence=token["confidence"],
            x=token["x_px"],
            y=token["y_px"],
            width=token["width_px"],
            height=token["height_px"],
        )
        for token in page["tokens"]
    ]
    unresolved = [
        {
            "code": "ambiguous_line_assignment" if token["candidate_line_ids"] else "unassigned_line_assignment",
            "token_source_row": token["source_row"],
            "candidate_line_ids": token["candidate_line_ids"],
        }
        for token in page["tokens"]
        if token["physical_line_id"] is None
    ]
    return canonical_geometry_state(
        fixture_id,
        page["side"],
        tokens,
        page["physical_lines"],
        unresolved,
        page["measurements"],
    )
