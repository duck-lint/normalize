"""Monotonic alignment from canonical lexical spans to OCR geometry anchors.

OCR strings locate canonical text; they are never copied into emitted text.
The dynamic program admits only locally similar 1:1, 1:2, and 2:1 matches,
plus explicit gaps, so unrelated words cannot be joined by a global fuzzy score.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class CanonicalToken:
    source_id: str
    start: int
    end: int
    text: str
    match_form: str


@dataclass(frozen=True)
class GeometryAnchor:
    anchor_id: str
    page_id: str
    text: str
    confidence: float | None
    box: tuple[float, float, float, float]
    physical_line_id: str | None
    order: int
    malformed: bool = False


@dataclass(frozen=True)
class AlignmentLink:
    canonical_token_indices: tuple[int, ...]
    anchor_ids: tuple[str, ...]
    physical_line_ids: tuple[str, ...]
    relation: str
    cost: float
    ambiguous: bool = False


@dataclass(frozen=True)
class AlignmentResult:
    canonical_tokens: tuple[CanonicalToken, ...]
    anchors: tuple[GeometryAnchor, ...]
    links: tuple[AlignmentLink, ...]
    unmatched_canonical_indices: tuple[int, ...]
    unmatched_anchor_ids: tuple[str, ...]
    ambiguous_links: tuple[int, ...]
    diagnostics: tuple[Mapping[str, Any], ...]


_WORD = re.compile(r"\S+", re.UNICODE)
_EDGE_PUNCTUATION = "\u2018\u2019\u201c\u201d\"'.,;:!?()[]{}<>"


def matching_form(text: str) -> str:
    """Normalize only a disposable alignment key, preserving source spans."""
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = normalized.replace("\u00ad", "")
    normalized = normalized.translate(str.maketrans({"’": "'", "‘": "'", "–": "-", "—": "-"}))
    return normalized.strip(_EDGE_PUNCTUATION)


def tokenize_canonical(text: str, source_id: str, offset: int = 0) -> tuple[CanonicalToken, ...]:
    return tuple(
        CanonicalToken(source_id, offset + match.start(), offset + match.end(), match.group(), matching_form(match.group()))
        for match in _WORD.finditer(text)
    )


def anchors_from_geometry(page: Mapping[str, Any]) -> tuple[GeometryAnchor, ...]:
    """Read geometry-probe-v1 token and line records without altering them."""
    lines = {line["line_id"]: line for line in page.get("physical_lines", [])}
    token_line: dict[str, str] = {}
    for line_id, line in lines.items():
        for token_id in line.get("token_ids", []):
            token_line[token_id] = line_id
    output = []
    for order, token in enumerate(page.get("tokens", [])):
        box = token.get("box", {})
        if not box:
            box = token
        x = float(box.get("x_px", box.get("left_px", 0)))
        y = float(box.get("y_px", box.get("top_px", 0)))
        width = float(box.get("width_px", 0))
        height = float(box.get("height_px", 0))
        token_id = str(token["token_id"])
        line_id = token.get("physical_line_id") or token_line.get(token_id)
        output.append(GeometryAnchor(
            token_id, str(page.get("page_id", page.get("printed_page", "page"))),
            str(token.get("text", "")), token.get("confidence"),
            (x, y, x + width, y + height), line_id, order,
            width <= 3 or height <= 3,
        ))
    return tuple(output)


def _similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, left, right, autojunk=False).ratio() if left and right else 0.0


def _match_cost(canonical: Sequence[CanonicalToken], anchors: Sequence[GeometryAnchor], i: int, j: int, a_count: int, o_count: int) -> tuple[float, str] | None:
    left = "".join(token.match_form for token in canonical[i:i + a_count])
    right = "".join(matching_form(anchor.text) for anchor in anchors[j:j + o_count])
    if not left or not right:
        return None
    similarity = _similarity(left, right)
    # Grouped merges/splits should be nearly exact after concatenation. The
    # looser bounded edit floor applies only to a single token on each side.
    minimum_similarity = 0.68 if (a_count, o_count) == (1, 1) else 0.88
    if similarity < minimum_similarity:
        return None
    if left == right:
        base = 0.0
    else:
        base = 0.28 + (1.0 - similarity) * 1.3
    # Grouping incurs a small cost so a direct token match is preferred.
    base += 0.12 * (a_count + o_count - 2)
    return base, "exact" if left == right else "fuzzy"


def align_monotonic(
    canonical: Sequence[CanonicalToken], anchors: Sequence[GeometryAnchor]
) -> AlignmentResult:
    """Globally align ordered sequences with explicit unmatched material.

    A canonical or OCR gap costs 0.82. Single-token substitutions require at
    least 0.68 character similarity; grouped merge/split matches require 0.88
    similarity after concatenation. This lets a bounded typo match while
    demanding near identity when OCR changes token boundaries. Equal-cost
    alternatives are reported at sequence scope; links are not all marked
    ambiguous without localized evidence.
    """
    n, m = len(canonical), len(anchors)
    inf = float("inf")
    cost = [[inf] * (m + 1) for _ in range(n + 1)]
    paths = [[0] * (m + 1) for _ in range(n + 1)]
    back: list[list[tuple[int, int, str, float] | None]] = [[None] * (m + 1) for _ in range(n + 1)]
    cost[0][0], paths[0][0] = 0.0, 1
    gap = 0.82
    epsilon = 1e-9

    def offer(ni: int, nj: int, candidate: float, previous: tuple[int, int, str, float]) -> None:
        if candidate + epsilon < cost[ni][nj]:
            cost[ni][nj] = candidate
            paths[ni][nj] = paths[previous[0]][previous[1]]
            back[ni][nj] = previous
        elif abs(candidate - cost[ni][nj]) <= epsilon:
            paths[ni][nj] = min(2, paths[ni][nj] + paths[previous[0]][previous[1]])

    for i in range(n + 1):
        for j in range(m + 1):
            if cost[i][j] == inf:
                continue
            if i < n:
                offer(i + 1, j, cost[i][j] + gap, (i, j, "canonical_gap", gap))
            if j < m:
                offer(i, j + 1, cost[i][j] + gap, (i, j, "anchor_gap", gap))
            for ac in (1, 2):
                for oc in (1, 2):
                    if i + ac > n or j + oc > m or (ac, oc) == (2, 2):
                        continue
                    match = _match_cost(canonical, anchors, i, j, ac, oc)
                    if match:
                        match_cost, kind = match
                        offer(i + ac, j + oc, cost[i][j] + match_cost, (i, j, f"{kind}:{ac}:{oc}", match_cost))

    i, j = n, m
    if cost[i][j] == inf:
        raise ValueError("alignment has no path")
    steps = []
    while i or j:
        previous = back[i][j]
        if previous is None:
            raise ValueError("alignment traceback is incomplete")
        pi, pj, relation, step_cost = previous
        steps.append((pi, pj, i - pi, j - pj, relation, step_cost))
        i, j = pi, pj
    steps.reverse()
    links: list[AlignmentLink] = []
    unmatched_canonical: list[int] = []
    unmatched_anchors: list[str] = []
    for ci, aj, ac, oc, relation, step_cost in steps:
        if relation == "canonical_gap":
            unmatched_canonical.append(ci)
        elif relation == "anchor_gap":
            unmatched_anchors.append(anchors[aj].anchor_id)
        else:
            selected_anchors = anchors[aj:aj + oc]
            line_ids = tuple(dict.fromkeys(a.physical_line_id for a in selected_anchors if a.physical_line_id))
            links.append(AlignmentLink(tuple(range(ci, ci + ac)), tuple(a.anchor_id for a in selected_anchors), line_ids, relation, step_cost))

    # The dynamic program can have multiple equivalent paths around gaps.
    # That only establishes sequence-level uncertainty; marking every chosen
    # link ambiguous would claim more localization than the score supports.
    ambiguous = paths[n][m] > 1
    diagnostics = []
    if unmatched_canonical:
        diagnostics.append({"code": "unmatched_canonical_material", "token_indices": unmatched_canonical})
    if unmatched_anchors:
        diagnostics.append({"code": "unmatched_ocr_anchors", "anchor_ids": unmatched_anchors})
    if ambiguous:
        diagnostics.append({"code": "ambiguous_alignment_path", "optimal_path_count_lower_bound": 2,
                            "scope": "sequence; individual links are not localized as ambiguous"})
    return AlignmentResult(tuple(canonical), tuple(anchors), tuple(links), tuple(unmatched_canonical), tuple(unmatched_anchors), (), tuple(diagnostics))
