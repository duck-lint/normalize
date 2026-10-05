"""Lexical evidence artifacts derived from recognition observations.

Text in this module is a transcript projection of observer output. It is not
promoted to canonical wording merely because it is the available transcript.
"""

from __future__ import annotations

import csv
import hashlib
import io
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .books import stable_digest


@dataclass(frozen=True)
class ExternalLexicalSource:
    source_id: str
    path: Path
    sha256: str
    provenance: str
    text: str

    def record(self) -> dict[str, Any]:
        return {"source_id": self.source_id, "path": str(self.path),
                "sha256": self.sha256, "provenance": self.provenance}


@dataclass(frozen=True)
class LexicalObservation:
    page_id: str
    observer: Mapping[str, Any]
    source_image_sha256: str
    observations: tuple[Mapping[str, Any], ...]
    diagnostics: tuple[Mapping[str, Any], ...]
    status: str

    @property
    def sha256(self) -> str:
        return stable_digest(self.record())

    def record(self) -> dict[str, Any]:
        return {"schema": "lexical-observation-v1", "page_id": self.page_id,
                "observer": dict(self.observer), "source_image_sha256": self.source_image_sha256,
                "status": self.status,
                "observations": [dict(item) for item in self.observations],
                "diagnostics": [dict(item) for item in self.diagnostics]}


@dataclass(frozen=True)
class LexicalTranscript:
    transcript_id: str
    book_id: str
    method: str
    text: str
    pages: tuple[Mapping[str, Any], ...]
    provenance: Mapping[str, Any]
    diagnostics: tuple[Mapping[str, Any], ...]
    external_source: Mapping[str, Any] | None = None

    def record(self) -> dict[str, Any]:
        body = {"schema": "lexical-transcript-v1", "transcript_id": self.transcript_id,
                "book_id": self.book_id, "method": self.method, "text": self.text,
                "pages": [dict(page) for page in self.pages],
                "provenance": dict(self.provenance),
                "external_source": dict(self.external_source) if self.external_source else None,
                "diagnostics": [dict(item) for item in self.diagnostics]}
        return body


def observation_from_geometry(page_id: str, source_image_sha256: str,
                              geometry: Mapping[str, Any], observer: Mapping[str, Any],
                              *, raw_tsv: str | None = None) -> LexicalObservation:
    """Project word rows independently, attaching geometry when admission succeeded.

    The raw TSV is authoritative for what the observer reported. Geometry is a
    second projection of that same TSV and may reject a word's spatial fields.
    """
    tokens = {item.get("source_row"): item for item in geometry.get("tokens", [])
              if isinstance(item, dict) and isinstance(item.get("source_row"), int)}
    geometry_errors = {item.get("source_row"): item for item in geometry.get("error_details", [])
                       if isinstance(item, dict) and isinstance(item.get("source_row"), int)}
    observations: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    lexical_rows: list[tuple[int, str, float | None, Mapping[str, Any] | None]] = []
    if raw_tsv is not None:
        # Keep framing aligned with geometry: quotes are literal OCR text in
        # Tesseract TSV, never CSV syntax.
        reader = csv.reader(io.StringIO(raw_tsv), delimiter="\t", quoting=csv.QUOTE_NONE)
        next(reader, None)
        for source_row, row in enumerate(reader, start=1):
            if len(row) < 12 or row[11] == "":
                continue
            try:
                is_word = int(row[0]) == 5
            except (ValueError, IndexError):
                is_word = False
            if is_word:
                try:
                    confidence_value = float(row[10])
                    confidence = confidence_value if math.isfinite(confidence_value) else None
                except (ValueError, OverflowError):
                    confidence = None
                lexical_rows.append((source_row, row[11], confidence, tokens.get(source_row)))
    else:
        # Geometry-only callers can project admitted tokens directly. Rejected
        # TSV rows cannot be recovered here because raw observer output was not
        # supplied, so this path makes no claim about those lexical rows.
        for source_row, token in sorted(tokens.items()):
            text = token.get("text")
            if not isinstance(text, str) or not text:
                continue
            try:
                confidence_value = float(token.get("confidence"))
                confidence = confidence_value if math.isfinite(confidence_value) else None
            except (TypeError, ValueError, OverflowError):
                confidence = None
            lexical_rows.append((source_row, text, confidence, token))

    for source_row, observed_text, confidence, token in lexical_rows:
        observation_id = (token.get("token_id") if token else None) or f"{page_id}:row-{source_row:04d}"
        spatially_valid = token is not None
        item = {"observation_id": observation_id, "source_row": source_row,
                "text": observed_text, "confidence": confidence,
                "spatial_status": "usable" if spatially_valid else "unusable",
                "anchor_id": token.get("token_id") if token else None,
                "physical_line_id": token.get("physical_line_id") if token else None,
                "box": ([token.get(key) for key in ("x_px", "y_px", "width_px", "height_px")]
                        if token else None)}
        observations.append(item)
        if isinstance(confidence, (float, int)) and confidence >= 0 and confidence < 50:
            diagnostics.append({"code": "observer_confidence_below_50",
                                "observation_id": observation_id, "confidence": confidence})
        if not spatially_valid:
            detail = geometry_errors.get(source_row, {})
            diagnostics.append({"code": "malformed_spatial_observation",
                "observation_id": observation_id, "source_row": source_row,
                "observed_text": observed_text,
                "confidence": confidence,
                "reason": detail.get("reason", "geometry parser did not admit a spatial anchor"),
                "observer_code": detail.get("code")})
        elif not item["physical_line_id"]:
            diagnostics.append({"code": "observation_without_physical_line", "observation_id": observation_id})
    if not observations:
        diagnostics.append({"code": "empty_ocr_page", "page_id": page_id})
    # This function runs only after successful TSV acquisition. Geometry may
    # fail to admit rows, but that does not mean lexical observation failed.
    return LexicalObservation(page_id, dict(observer), source_image_sha256,
                              tuple(observations), tuple(diagnostics), "observed")


def failed_observation(page_id: str, source_image_sha256: str, error: str,
                       observer: Mapping[str, Any]) -> LexicalObservation:
    return LexicalObservation(page_id, dict(observer), source_image_sha256, (),
                              ({"code": "ocr_page_failed", "reason": error},), "failed")


def transcript_from_observations(book_id: str, observations: Sequence[LexicalObservation],
                                 *, method: str = "single-observer-transcript-v1") -> LexicalTranscript:
    """Join each page's OCR tokens in preserved Tesseract row order."""
    parts: list[str] = []
    page_records: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    cursor = 0
    token_records: list[dict[str, Any]] = []
    for page_index, observation in enumerate(observations):
        if page_index:
            parts.append("\n\n")
            cursor += 2
        page_start = cursor
        if page_records:
            # Attribute the explicit page separator to the preceding page so
            # derived page spans remain contiguous for the existing aligner.
            page_records[-1]["transcript_span"]["end"] = page_start
        page_text_parts: list[str] = []
        page_token_records: list[dict[str, Any]] = []
        for item in observation.observations:
            text = item.get("text")
            if not isinstance(text, str) or not text:
                continue
            # Each previously emitted token contributes one joining space
            # before the current token.
            start = page_start + sum(len(part) for part in page_text_parts) + len(page_text_parts)
            page_text_parts.append(text)
            end = start + len(text)
            page_token_records.append({"observation_id": item["observation_id"],
                                       "start": start, "end": end,
                                       "text": text, "confidence": item.get("confidence")})
            token_records.append({"page_id": observation.page_id, **page_token_records[-1]})
        page_text = " ".join(page_text_parts)
        parts.append(page_text)
        cursor += len(page_text)
        page_records.append({"page_id": observation.page_id, "page_index": page_index,
                             "text": page_text, "transcript_span": {"start": page_start, "end": cursor},
                             "observation_sha256": observation.sha256,
                             "token_ranges": page_token_records,
                             "status": observation.status})
        diagnostics.extend({"page_id": observation.page_id, **dict(item)}
                           for item in observation.diagnostics)
    text = "".join(parts)
    provenance = {"observer_ids": sorted({str(item.observer.get("identity_sha256", "unknown")) for item in observations}),
                  "page_order": [item.page_id for item in observations],
                  "observation_sha256": {item.page_id: item.sha256 for item in observations},
                  "token_ranges": token_records}
    identity = stable_digest({"method": method, "book_id": book_id, "text": text,
                              "provenance": provenance, "pages": page_records,
                              "diagnostics": diagnostics})
    return LexicalTranscript(identity, book_id, method, text, tuple(page_records), provenance,
                             tuple(diagnostics))


def external_source_from_manifest(manifest: Any) -> ExternalLexicalSource | None:
    if manifest.canonical_source is None:
        return None
    content = manifest.canonical_source.read_text(encoding="utf-8")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return ExternalLexicalSource("external:" + digest[:16], manifest.canonical_source, digest,
                                 "BookManifest v1 independently supplied lexical source", content)


__all__ = ["ExternalLexicalSource", "LexicalObservation", "LexicalTranscript",
           "observation_from_geometry", "failed_observation", "transcript_from_observations",
           "external_source_from_manifest"]
