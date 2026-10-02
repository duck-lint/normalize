"""Geometry-backed structural blocks over immutable canonical source spans."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from statistics import median
from typing import Any, Mapping, Sequence

from .alignment import AlignmentResult, CanonicalToken, GeometryAnchor, align_monotonic, anchors_from_geometry, tokenize_canonical


@dataclass(frozen=True)
class PageSpan:
    page_id: str
    start: int
    end: int
    geometry: Mapping[str, Any]


@dataclass(frozen=True)
class StructuralBlock:
    kind: str
    text: str
    canonical_spans: tuple[tuple[str, int, int], ...]
    page_ids: tuple[str, ...]
    physical_line_ids: tuple[str, ...]
    anchor_ids: tuple[str, ...]
    confidence: str
    evidence: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NormalizedDocument:
    source_id: str
    blocks: tuple[StructuralBlock, ...]
    alignments: tuple[AlignmentResult, ...]
    diagnostics: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class _Line:
    page_id: str
    line_id: str | None
    token_indices: tuple[int, ...]
    left: float | None
    right: float | None
    top: float | None
    bottom: float | None
    height: float | None
    gap_after: float | None
    centered: bool


def _token_text(source: str, tokens: Sequence[CanonicalToken], indices: Sequence[int]) -> str:
    if not indices:
        return ""
    ordered = sorted(indices)
    parts = [tokens[ordered[0]].text]
    previous = ordered[0]
    for index in ordered[1:]:
        separator = source[tokens[previous].end:tokens[index].start] if index == previous + 1 else " "
        parts.extend((separator, tokens[index].text))
        previous = index
    return "".join(parts)


def _page_lines(page: PageSpan, alignment: AlignmentResult, source: str, source_id: str) -> tuple[list[_Line], list[CanonicalToken]]:
    tokens = list(alignment.canonical_tokens)
    token_lines: dict[int, list[GeometryAnchor]] = {}
    for link in alignment.links:
        group = [a for a in alignment.anchors if a.anchor_id in link.anchor_ids]
        for token_index in link.canonical_token_indices:
            token_lines.setdefault(token_index, []).extend(group)
    geom_lines = {str(line["line_id"]): line for line in page.geometry.get("physical_lines", [])}
    buckets: dict[str, list[int]] = {}
    unanchored: list[int] = []
    for index in range(len(tokens)):
        anchors = token_lines.get(index, [])
        line_ids = list(dict.fromkeys(a.physical_line_id for a in anchors if a.physical_line_id))
        if line_ids:
            # A canonical word split across two physical bands can be linked
            # to multiple OCR fragments; assign it once, to the first spatial
            # anchor, while retaining all anchor IDs in the alignment result.
            buckets.setdefault(line_ids[0], []).append(index)
        else:
            unanchored.append(index)
    lines: list[_Line] = []
    for line_id, indices in buckets.items():
        record = geom_lines.get(line_id, {})
        indices = sorted(set(indices))
        left = record.get("left_px")
        top = record.get("top_px")
        bottom = record.get("bottom_px")
        height = record.get("line_height_px")
        width = page.geometry.get("width_px")
        center = (record.get("left_px", 0) + record.get("right_px", 0)) / 2
        centered = bool(width and abs(center - width / 2) <= width * 0.11)
        lines.append(_Line(page.page_id, line_id, tuple(indices), left, record.get("right_px"), top, bottom, height,
                           record.get("vertical_gap_to_next_px"), centered))
    # Canonical material without a usable anchor remains in sequence. Attach it
    # to its nearest canonical neighbor's line; if neither exists, keep an
    # explicit unanchored line rather than dropping it.
    for index in unanchored:
        prior = next((line for line in reversed(lines) if line.token_indices[-1] < index), None)
        following = next((line for line in lines if line.token_indices[0] > index), None)
        chosen = prior or following
        if chosen:
            bucket = next(line for line in lines if line.line_id == chosen.line_id)
            replacement = _Line(bucket.page_id, bucket.line_id, tuple(sorted((*bucket.token_indices, index))), bucket.left, bucket.right, bucket.top, bucket.bottom, bucket.height, bucket.gap_after, bucket.centered)
            lines[lines.index(bucket)] = replacement
        else:
            lines.append(_Line(page.page_id, None, (index,), None, None, None, None, None, None, False))
    lines.sort(key=lambda line: min(line.token_indices))
    # If OCR order assigns nonadjacent source words to one physical band,
    # preserve canonical order by splitting the band into contiguous runs.
    ordered_runs: list[_Line] = []
    for line in lines:
        run: list[int] = []
        for index in sorted(line.token_indices):
            if run and index != run[-1] + 1:
                ordered_runs.append(_Line(line.page_id, line.line_id, tuple(run), line.left, line.right, line.top,
                                          line.bottom, line.height, line.gap_after, line.centered))
                run = []
            run.append(index)
        if run:
            ordered_runs.append(_Line(line.page_id, line.line_id, tuple(run), line.left, line.right, line.top,
                                      line.bottom, line.height, line.gap_after, line.centered))
    ordered_runs.sort(key=lambda line: min(line.token_indices))
    return ordered_runs, tokens


def _make_blocks(source: str, source_id: str, pages: Sequence[PageSpan], alignments: Sequence[AlignmentResult]) -> tuple[list[StructuralBlock], list[dict[str, Any]]]:
    diagnostics: list[dict[str, Any]] = []
    page_line_groups: list[tuple[PageSpan, list[_Line], list[CanonicalToken]]] = []
    for page, alignment in zip(pages, alignments, strict=True):
        lines, tokens = _page_lines(page, alignment, source, source_id)
        page_line_groups.append((page, lines, tokens))

    blocks: list[StructuralBlock] = []
    pending_text: list[str] = []
    pending_spans: list[tuple[str, int, int]] = []
    pending_pages: list[str] = []
    pending_lines: list[str] = []
    pending_anchors: list[str] = []
    pending_kind = "paragraph"
    pending_evidence: dict[str, Any] = {}

    def flush() -> None:
        nonlocal pending_text, pending_spans, pending_pages, pending_lines, pending_anchors, pending_kind, pending_evidence
        text = re.sub(r"\s+", " ", " ".join(part.strip() for part in pending_text if part.strip())).strip()
        if text:
            blocks.append(StructuralBlock(pending_kind, text, tuple(pending_spans), tuple(dict.fromkeys(pending_pages)), tuple(dict.fromkeys(pending_lines)), tuple(dict.fromkeys(pending_anchors)), "medium" if pending_lines else "low", dict(pending_evidence)))
        pending_text, pending_spans, pending_pages, pending_lines, pending_anchors = [], [], [], [], []
        pending_kind, pending_evidence = "paragraph", {}

    for page_index, (page, lines, tokens) in enumerate(page_line_groups):
        aligned_line_lefts = [line.left for line in lines if line.left is not None and line.line_id is not None]
        # The leftmost repeated body edge is a stable baseline even when a
        # small page slice contains equal numbers of indented and flush rows.
        body_left = min(aligned_line_lefts) if aligned_line_lefts else None
        page_height = page.geometry.get("height_px", 0)
        body_heights = [line.height for line in lines if line.height and line.height > 0
                        and (line.top is None or line.top > page_height * 0.20)]
        line_heights = body_heights or [line.height for line in lines if line.height and line.height > 0]
        typical_height = median(line_heights) if line_heights else None
        gaps = [line.gap_after for line in lines if line.gap_after is not None and line.gap_after >= 0]
        typical_gap = median(gaps) if gaps else None

        # A heading is an isolated top-page centered cluster with larger type,
        # followed by a substantial return to body text. This distinguishes a
        # centered first prose row from a title using layout, not its wording.
        candidate_headings = [line for line in lines if line.centered and line.top is not None
                              and line.top <= page_height * 0.22 and line.height is not None
                              and typical_height and line.height >= typical_height * 1.05]
        heading_indices: set[int] = set()
        if candidate_headings:
            last_candidate = max(candidate_headings, key=lambda item: item.top or 0)
            following = next((line for line in lines if line.top is not None and last_candidate.bottom is not None
                              and line.top >= last_candidate.bottom and line not in candidate_headings), None)
            if following and typical_height and following.top - (last_candidate.bottom or 0) >= typical_height * 1.5:
                heading_indices = {index for line in candidate_headings for index in line.token_indices}
                for title_line in candidate_headings:
                    for number_line in lines:
                        if number_line.top is None or title_line.top is None or not number_line.centered:
                            continue
                        distance = title_line.top - number_line.top
                        number_text = _token_text(source, tokens, number_line.token_indices).strip()
                        if 0 <= distance <= (typical_height or 0) * 4 and re.fullmatch(r"\d+[.)]?", number_text):
                            heading_indices.update(number_line.token_indices)

        # A figure label is a general textual locator. Nearby sparse,
        # spatially isolated labels are grouped only when the geometry forms
        # a cluster; OCR label wording is retained solely as provenance.
        figure_groups: list[set[int]] = []
        for caption_line in lines:
            caption_text = _token_text(source, tokens, caption_line.token_indices)
            if not re.search(r"\bFig(?:ure)?\.?\s*\d+\b", caption_text, re.IGNORECASE):
                continue
            if caption_line.top is None:
                continue
            nearby = [line for line in lines if line is not caption_line and line.top is not None
                      and typical_height and caption_line.top - typical_height * 7 <= line.top <= caption_line.top
                      and len(line.token_indices) <= 3 and line.left is not None and page.geometry.get("width_px")
                      and line.right is not None
                      and line.left > page.geometry["width_px"] * 0.18
                      and line.right < page.geometry["width_px"] * 0.92]
            if len(nearby) >= 3:
                group = {index for line in (*nearby, caption_line) for index in line.token_indices}
                figure_groups.append(group)
        figure_by_first = {min(group): group for group in figure_groups if group}
        figure_indices = set().union(*figure_groups) if figure_groups else set()
        consumed_figure_indices: set[int] = set()
        math_lines: dict[int, str] = {}
        for line_index, line in enumerate(lines):
            text = _token_text(source, tokens, line.token_indices)
            narrow_centered = bool(line.centered and line.left is not None and line.right is not None
                                   and page.geometry.get("width_px")
                                   and line.right - line.left <= page.geometry["width_px"] * 0.65)
            formula_like = bool(re.search(r"(?:=|√|[²³])", text)) or (
                len(line.token_indices) <= 3
                and all(len(tokens[index].match_form) <= 2 for index in line.token_indices)
                and any(tokens[index].match_form.isdigit() for index in line.token_indices)
            )
            if narrow_centered and len(line.token_indices) <= 6 and formula_like and not (set(line.token_indices) & figure_indices) and not (set(line.token_indices) & heading_indices):
                math_lines[line_index] = text
            elif (re.search(r"[√²³]", text) or ("=" in text and len(line.token_indices) <= 6)) and line.token_indices:
                diagnostics.append({"code": "possible_display_math_not_isolated", "page_id": page.page_id,
                                   "physical_line_id": line.line_id,
                                   "canonical_start": tokens[line.token_indices[0]].start,
                                   "canonical_end": tokens[line.token_indices[-1]].end,
                                   "canonical_text": text,
                                   "note": "formula-like canonical material lacks the centered, narrow geometry used for display-math classification"})

        for line_index, line in enumerate(lines):
            line_text = _token_text(source, tokens, line.token_indices)
            line_anchors = [anchor for link in alignments[page_index].links if set(link.canonical_token_indices) & set(line.token_indices) for anchor in alignments[page_index].anchors if anchor.anchor_id in link.anchor_ids]
            line_anchor_ids = [anchor.anchor_id for anchor in line_anchors]
            if set(line.token_indices) & consumed_figure_indices:
                continue
            is_heading = bool(line.token_indices) and set(line.token_indices).issubset(heading_indices)
            if min(line.token_indices, default=-1) in figure_by_first:
                flush()
                group = figure_by_first[min(line.token_indices)]
                consumed_figure_indices.update(group)
                member_lines = [candidate for candidate in lines if set(candidate.token_indices) & group]
                member_indices = sorted(group)
                member_texts = [_token_text(source, tokens, candidate.token_indices) for candidate in member_lines]
                first_token, last_token = tokens[member_indices[0]], tokens[member_indices[-1]]
                preceding = [candidate for candidate in lines if candidate.token_indices[-1] < member_indices[0]]
                following = [candidate for candidate in lines if candidate.token_indices[0] > member_indices[-1]]
                before_line = max(preceding, key=lambda candidate: candidate.token_indices[-1]) if preceding else None
                after_line = min(following, key=lambda candidate: candidate.token_indices[0]) if following else None
                embedded = bool(before_line and after_line and before_line.left is not None and after_line.left is not None
                                and typical_height and abs(after_line.left - before_line.left) < typical_height * 1.4)
                blocks.append(StructuralBlock(
                    "figure", re.sub(r"\s+", " ", " ".join(member_texts)).strip(),
                    tuple((source_id, tokens[index].start, tokens[index].end) for index in member_indices),
                    (page.page_id,), tuple(candidate.line_id for candidate in member_lines if candidate.line_id),
                    tuple(anchor.anchor_id for candidate in member_lines for link in alignments[page_index].links
                          if set(link.canonical_token_indices) & set(candidate.token_indices)
                          for anchor in alignments[page_index].anchors if anchor.anchor_id in link.anchor_ids),
                    "medium", {"isolated_sparse_label_cluster": True, "caption_locator": True,
                               "canonical_span": [first_token.start, last_token.end],
                               "embedded_in_prose_continuity": embedded}))
                continue
            if line_index in math_lines:
                flush()
                first_token, last_token = tokens[line.token_indices[0]], tokens[line.token_indices[-1]]
                block_text = re.sub(r"\s+", " ", line_text).strip()
                blocks.append(StructuralBlock("display_math", block_text,
                    ((source_id, first_token.start, last_token.end),), (page.page_id,),
                    (line.line_id,) if line.line_id else (), tuple(line_anchor.anchor_id for line_anchor in line_anchors),
                    "low", {"centered_isolated_line": True, "formula_like_canonical_text": True}))
                continue
            if is_heading and pending_text and pending_kind != "heading":
                flush()
            if pending_kind == "heading" and not is_heading:
                flush()
            if is_heading:
                pending_kind = "heading"
                pending_evidence.update({"centered": True, "top_region": True, "isolated_geometry": True})
            elif line_index > 0 and pending_text:
                prior = lines[line_index - 1]
                page_width = page.geometry.get("width_px", 0)
                indent_px = (line.left - body_left) if body_left is not None and line.left is not None else 0
                # A paragraph indent is modest relative to type size. A much
                # larger offset is more consistent with a detached line
                # fragment than with a first-line paragraph inset.
                plausible_indent = bool(typical_height and typical_height * 1.4 <= indent_px <= typical_height * 3.0)
                same_physical_band = bool(line.line_id and line.line_id == prior.line_id)
                band_already_in_paragraph = bool(line.line_id and line.line_id in pending_lines)
                geometry_order_conflict = bool(line.top is not None and prior.top is not None and line.top < prior.top)
                if geometry_order_conflict:
                    diagnostics.append({"code": "canonical_geometry_order_conflict", "page_id": page.page_id,
                                        "previous_line_id": prior.line_id, "line_id": line.line_id,
                                        "previous_top_px": prior.top, "top_px": line.top,
                                        "note": "alignment maps later canonical material above earlier geometry; no boundary inferred from this transition"})
                starts_new_left_edge = bool(line.left is not None and prior.left is not None and line.left - prior.left >= (typical_height or 0) * 0.8)
                indented = bool(not geometry_order_conflict and not same_physical_band and not band_already_in_paragraph and body_left is not None and typical_height and line.left is not None
                                and plausible_indent
                                and starts_new_left_edge
                                )
                large_gap = bool(not geometry_order_conflict and not same_physical_band and not band_already_in_paragraph and typical_height is not None and prior.gap_after is not None and prior.gap_after > typical_height * 0.8)
                # Start a paragraph on a stable indent or a distinctly large
                # vertical separation, never merely at a physical line break.
                if indented or large_gap:
                    flush()
                    pending_evidence.update({"first_line_indent_px": (line.left - body_left) if indented else None,
                                             "vertical_gap_px": line.gap_after if large_gap else None})
            elif line_index == 0 and page_index > 0 and pending_text:
                page_indent = (line.left - body_left) if body_left is not None and line.left is not None else 0
                page_start_indent = bool(body_left is not None and typical_height and line.left is not None
                                         and typical_height * 1.4 <= page_indent <= typical_height * 3.0)
                if page_start_indent:
                    flush()
                    pending_evidence.update({"page_start_indent_px": line.left - body_left})
            if line_text:
                pending_text.append(line_text)
                first, last = tokens[line.token_indices[0]], tokens[line.token_indices[-1]]
                pending_spans.append((source_id, first.start, last.end))
                pending_pages.append(page.page_id)
                if line.line_id:
                    pending_lines.append(line.line_id)
                pending_anchors.extend(line_anchor_ids)
        # Preserve page order and provenance but do not force a page boundary
        # into a paragraph. The next page's first-line indent may separate it.
        if page_index < len(page_line_groups) - 1:
            diagnostics.append({"code": "page_boundary_review", "page_id": page.page_id, "note": "paragraph continuation is decided from geometry; page boundary alone is not structural evidence"})
    flush()
    return blocks, diagnostics


def reconstruct_document(source: str, source_id: str, pages: Sequence[PageSpan]) -> NormalizedDocument:
    """Align each explicit canonical source span to its page geometry, then reconstruct blocks."""
    if not pages:
        raise ValueError("at least one ordered page span is required")
    if any(page.start < 0 or page.end < page.start or page.end > len(source) for page in pages):
        raise ValueError("page span is outside canonical source text")
    if list(pages) != sorted(pages, key=lambda p: p.start):
        raise ValueError("page spans must be supplied in canonical source order")
    if any(current.start < previous.end for previous, current in zip(pages, pages[1:])):
        raise ValueError("canonical page spans must not overlap")
    alignments = []
    diagnostics: list[Mapping[str, Any]] = []
    cursor = 0
    for page in pages:
        if page.start > cursor:
            diagnostics.append({"code": "canonical_source_range_outside_selected_pages", "start": cursor,
                                "end": page.start, "source_id": source_id,
                                "note": "caller-selected page spans omit this source range; classify it explicitly as fixture mapping or review evidence"})
        cursor = page.end
    if cursor < len(source):
        diagnostics.append({"code": "canonical_source_range_outside_selected_pages", "start": cursor,
                            "end": len(source), "source_id": source_id,
                            "note": "caller-selected page spans omit this source range; classify it explicitly as fixture mapping or review evidence"})
    for page in pages:
        tokens = tokenize_canonical(source[page.start:page.end], source_id, page.start)
        anchors = anchors_from_geometry({**page.geometry, "page_id": page.page_id})
        alignment = align_monotonic(tokens, anchors)
        alignments.append(alignment)
        diagnostics.extend({**item, "page_id": page.page_id} for item in alignment.diagnostics)
        if any(anchor.malformed for anchor in anchors):
            diagnostics.append({"code": "malformed_geometry_anchor", "page_id": page.page_id, "anchor_ids": [a.anchor_id for a in anchors if a.malformed]})
    blocks, structural_diagnostics = _make_blocks(source, source_id, pages, alignments)
    diagnostics.extend(structural_diagnostics)
    return NormalizedDocument(source_id, tuple(blocks), tuple(alignments), tuple(diagnostics))
