"""Ordered physical-book orchestration with separate lexical evidence."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Mapping

from .books import (BOOK_MANIFEST_SCHEMA, BookContractError, BookManifest, BookProfile,
                    sha256_file, stable_digest, validate_profile_for_manifest)
from .engine import BookEngine
from .lexical import (LexicalObservation, external_source_from_manifest,
                      failed_observation, transcript_from_observations)
from .markdown import document_record
from .reconstruction import PageSpan


@dataclass(frozen=True)
class ReviewReport:
    book_id: str
    run_id: str
    diagnostics: tuple[Mapping[str, Any], ...]

    def record(self) -> dict[str, Any]:
        return {"schema": "normalize-review-v2", "book_id": self.book_id,
                "run_id": self.run_id, "diagnostics": [dict(item) for item in self.diagnostics]}


@dataclass(frozen=True)
class BookRun:
    run_id: str
    book_id: str
    status: str
    started_at: str
    completed_at: str
    manifest: Mapping[str, Any]
    profile: Mapping[str, Any]
    lexical: Mapping[str, Any]
    engine: Mapping[str, Any]
    global_config_sha256: str
    pages: tuple[Mapping[str, Any], ...]
    artifacts: Mapping[str, Any]
    review_diagnostic_count: int

    def record(self) -> dict[str, Any]:
        return {"schema": "normalize-book-run-v2", "run_id": self.run_id,
                "book_id": self.book_id, "started_at": self.started_at,
                "completed_at": self.completed_at, "manifest": dict(self.manifest),
                "profile": dict(self.profile), "lexical": dict(self.lexical),
                "engine": dict(self.engine), "global_config_sha256": self.global_config_sha256,
                "status": self.status, "pages": [dict(page) for page in self.pages],
                "artifacts": dict(self.artifacts),
                "review_diagnostic_count": self.review_diagnostic_count}


def _git_revision() -> str | None:
    try:
        package_root = Path(__file__).resolve().parents[2]
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=package_root,
                              check=True, capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _package_version() -> str:
    try:
        return version("normalize")
    except PackageNotFoundError:
        return "0.1.0"


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_cached_page(path: Path, cache_key: str) -> dict[str, Any] | None:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if (isinstance(record, dict) and record.get("cache_key") == cache_key
            and record.get("status") in {"succeeded", "needs_review"}
            and isinstance(record.get("result"), dict)):
        return record["result"]
    return None


def _empty_geometry(page_id: str, book_id: str, index: int, image_path: Path,
                    source_hash: str, dpi: int) -> dict[str, Any]:
    return {"page_id": page_id, "side": page_id, "width_px": 0, "height_px": 0,
            "tokens": [], "physical_lines": [], "status": "failure",
            "errors": ["page_processing_failed"], "uncertainties": [],
            "error_details": [], "measurements": {}, "engine": {},
            "provenance": {"book_id": book_id, "page_id": page_id, "page_index": index,
                           "source_image": str(image_path), "source_image_sha256": source_hash, "dpi": dpi}}


def _review_diagnostics(document_value: Mapping[str, Any], page_states: list[dict[str, Any]],
                        lexical_diagnostics: list[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    diagnostics: list[dict[str, Any]] = []
    for state in page_states:
        page_id = state["page_id"]
        if state["status"] == "failed":
            diagnostics.append({"code": "page_processing_failed", "page_id": page_id,
                                "reason": state.get("error"), "source_sha256": state.get("source_sha256")})
        diagnostics.extend({"page_id": page_id, **item} for item in state.get("geometry_diagnostics", []))
    diagnostics.extend(dict(item) for item in lexical_diagnostics)
    diagnostics.extend(dict(item) for item in document_value.get("diagnostics", []))
    unique: dict[str, dict[str, Any]] = {}
    for item in diagnostics:
        unique.setdefault(json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")), item)
    return tuple(unique.values())


def _external_transcript(manifest: BookManifest, source: Any) -> tuple[str, list[dict[str, Any]], dict[str, Any]] | None:
    spans = [page.canonical_span for page in manifest.pages]
    if manifest.schema != BOOK_MANIFEST_SCHEMA or source is None or not all(spans):
        return None
    assert source is not None
    concrete = [span for span in spans if span is not None]
    if (concrete[0].start != 0 or concrete[-1].end != len(source.text)
            or any(left.end != right.start for left, right in zip(concrete, concrete[1:]))):
        raise BookContractError("legacy v1 external lexical spans must cover the source contiguously in page order")
    return source.text, [{"page_id": page.page_id, "page_index": index,
                              "text": source.text[concrete[index].start:concrete[index].end],
                              "transcript_span": {"start": concrete[index].start, "end": concrete[index].end},
                              "status": "external_evidence"}
                             for index, page in enumerate(manifest.pages)], source.record()


def run_book(manifest: BookManifest, profile: BookProfile, output_dir: Path,
             *, engine: BookEngine | None = None, resume: bool = True) -> dict[str, Any]:
    """Run page observations, derive lexical input when needed, then reconstruct."""
    validate_profile_for_manifest(profile, manifest, require_frozen=True)
    if sha256_file(manifest.path) != manifest.record_sha256:
        raise BookContractError("book manifest changed after it was loaded; reload it and validate the profile again")
    if any(page.source_sha256 is None for page in manifest.pages):
        raise BookContractError("whole-book run requires source-validated page images")

    engine = engine or BookEngine()
    engine_identity = engine.identity
    observer_identity = engine.observation_identity
    output_dir = output_dir.resolve()
    pages_dir = output_dir / "pages"
    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(UTC).isoformat()
    global_config_sha256 = stable_digest(engine.config.record())
    external_source = external_source_from_manifest(manifest)
    external = _external_transcript(manifest, external_source)
    page_states: list[dict[str, Any]] = []
    geometry_by_id: dict[str, dict[str, Any]] = {}
    observations: list[LexicalObservation] = []
    calibrations = profile.page_calibrations

    for index, page in enumerate(manifest.pages):
        calibration = calibrations[page.page_id]
        source_error = None
        try:
            source_hash = sha256_file(page.image)
        except OSError as exc:
            source_hash = "unavailable"
            source_error = f"{type(exc).__name__}: {exc}"
        if page.source_sha256 and source_hash != page.source_sha256:
            source_error = "source image hash differs from manifest"
        page_engine_key = stable_digest({
            "book_id": manifest.book_id, "page_id": page.page_id, "page_index": index,
            "source_sha256": source_hash,
            "page_calibration": {"bounds": calibration.content_bounds,
                "content_status": calibration.content_status,
                "orientation_degrees": calibration.orientation_degrees,
                "orientation_status": calibration.orientation_status,
                "deskew_degrees": calibration.deskew_degrees,
                "deskew_status": calibration.deskew_status,
                "source": calibration.source, "note": calibration.note},
            "source_dpi": profile.source_dpi, "observer": observer_identity,
        })
        page_dir = pages_dir / page.page_id
        cached_path = page_dir / "page-result.json"
        page_result = _read_cached_page(cached_path, page_engine_key) if resume else None
        cache_hit = page_result is not None
        error = None
        if page_result is None:
            try:
                if source_error:
                    raise OSError(source_error)
                page_result = engine.process_page(page, calibration, book_id=manifest.book_id,
                    page_index=index, source_dpi=profile.source_dpi, source_sha256=source_hash)
                state = "needs_review" if (calibration.content_status == "unresolved"
                    or calibration.orientation_status == "unresolved"
                    or calibration.deskew_status == "unresolved"
                    or page_result["geometry"].get("status") != "success"
                    or page_result["lexical_observation"].get("diagnostics")) else "succeeded"
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                page_result = {"page_id": page.page_id, "page_index": index,
                    "source_image": str(page.image), "source_sha256": source_hash,
                    "geometry": _empty_geometry(page.page_id, manifest.book_id, index,
                                                page.image, source_hash, profile.source_dpi),
                    "lexical_observation": failed_observation(page.page_id, source_hash, error,
                                                               observer_identity).record()}
                state = "failed"
            _write_json(cached_path, {"schema": "book-page-observation-cache-v2", "cache_key": page_engine_key,
                                      "status": state, "error": error, "result": page_result})
        else:
            wrapper = json.loads(cached_path.read_text(encoding="utf-8"))
            state, error = wrapper.get("status", "needs_review"), wrapper.get("error")
        geometry = page_result["geometry"]
        geometry_by_id[page.page_id] = geometry
        obs_record = page_result.get("lexical_observation")
        if obs_record is None:
            obs_record = failed_observation(page.page_id, source_hash,
                "cached page lacks lexical observation", observer_identity).record()
        observation = LexicalObservation(page.page_id, obs_record.get("observer", observer_identity),
            obs_record.get("source_image_sha256", source_hash), tuple(obs_record.get("observations", [])),
            tuple(obs_record.get("diagnostics", [])), obs_record.get("status", "failed"))
        observations.append(observation)
        geometry_diagnostics = []
        for field in ("errors", "uncertainties"):
            for code in geometry.get(field, []):
                geometry_diagnostics.append({"code": code, "source": "geometry",
                    "severity": "error" if field == "errors" else "uncertainty"})
        geometry_diagnostics.extend({"source": "geometry", "severity": "error", **detail}
            for detail in geometry.get("error_details", []) if isinstance(detail, dict))
        page_states.append({"page_id": page.page_id, "page_index": index, "status": state,
            "cache_hit": cache_hit, "source_sha256": source_hash, "error": error,
            "geometry_diagnostics": geometry_diagnostics, "lexical_observation_sha256": observation.sha256})

    transcript = transcript_from_observations(manifest.book_id, observations)
    transcript_text = transcript.text
    transcript_pages = list(transcript.pages)
    external_record = None
    if external:
        transcript_text, transcript_pages, external_record = external
        # External text remains explicitly identified evidence. OCR observations
        # are still retained as locating anchors for the existing aligner.
        transcript_id = stable_digest({"method": "external-lexical-source-v1",
            "physical_manifest": manifest.physical_sha256, "external_source": external_record,
            "text": transcript_text, "pages": transcript_pages,
            "observations": [item.sha256 for item in observations]})
        transcript_method = "external-lexical-source-v1"
        transcript_diagnostics: list[Mapping[str, Any]] = []
    else:
        transcript_id, transcript_method = transcript.transcript_id, transcript.method
        transcript_diagnostics = list(transcript.diagnostics)
    page_spans = []
    for index, page in enumerate(manifest.pages):
        span_value = transcript_pages[index]["transcript_span"]
        page_spans.append(PageSpan(page.page_id, span_value["start"], span_value["end"], geometry_by_id[page.page_id]))
        page_states[index]["transcript_span"] = dict(span_value)

    document = engine.reconstruct(transcript_text, transcript_id, page_spans)
    serialized_document = dict(document_record(document))
    markdown = engine.emit(document)
    all_lexical_diagnostics = list(transcript_diagnostics)
    if external_record:
        all_lexical_diagnostics.extend({"page_id": obs.page_id, **dict(item)}
            for obs in observations for item in obs.diagnostics)
    review = ReviewReport(manifest.book_id, stable_digest({
        "physical_manifest": manifest.physical_sha256, "profile": profile.sha256,
        "observations": [item.sha256 for item in observations], "transcript": transcript_id,
        "engine": engine_identity, "global_config": global_config_sha256,
        "reconstruction_source": engine_identity.get("production_source_sha256")}),
        _review_diagnostics(serialized_document, page_states, all_lexical_diagnostics))
    run_id = review.run_id
    serialized_transcript = {"schema": "lexical-transcript-v1", "transcript_id": transcript_id,
        "book_id": manifest.book_id, "method": transcript_method, "text": transcript_text,
        "pages": transcript_pages,
        "provenance": {"observer_ids": [observer_identity.get("identity_sha256")],
            "observation_sha256": {item.page_id: item.sha256 for item in observations},
            "external_source": external_record},
        "diagnostics": [dict(item) for item in all_lexical_diagnostics]}

    (output_dir / "normalized.md").write_text(markdown, encoding="utf-8")
    _write_json(output_dir / "lexical-transcript.json", serialized_transcript)
    _write_json(output_dir / "provenance.json", serialized_document)
    _write_json(output_dir / "review.json", review.record())
    page_artifacts: dict[str, dict[str, Any]] = {}
    for index, page in enumerate(manifest.pages):
        page_dir = pages_dir / page.page_id
        geometry_path = page_dir / "geometry.json"
        observation_path = page_dir / "lexical-observation.json"
        alignment_path = page_dir / "alignment.json"
        _write_json(geometry_path, geometry_by_id[page.page_id])
        _write_json(observation_path, observations[index].record())
        alignment = document.alignments[index]
        _write_json(alignment_path, {"schema": "page-alignment-v2", "page_id": page.page_id,
            "transcript_span": page_states[index]["transcript_span"],
            "lexical_tokens": [{"source_id": token.source_id, "start": token.start,
                "end": token.end, "text": token.text} for token in alignment.canonical_tokens],
            "links": [{"token_indices": list(link.canonical_token_indices),
                "anchor_ids": list(link.anchor_ids), "physical_line_ids": list(link.physical_line_ids),
                "relation": link.relation, "cost": link.cost, "ambiguous": link.ambiguous}
                for link in alignment.links],
            "unmatched_token_indices": list(alignment.unmatched_canonical_indices),
            "unmatched_anchor_ids": list(alignment.unmatched_anchor_ids),
            "diagnostics": list(alignment.diagnostics)})
        result_path = page_dir / "page-result.json"
        page_states[index]["artifacts"] = {
            "geometry": {"path": str(geometry_path.relative_to(output_dir)), "sha256": sha256_file(geometry_path)},
            "lexical_observation": {"path": str(observation_path.relative_to(output_dir)), "sha256": sha256_file(observation_path)},
            "alignment": {"path": str(alignment_path.relative_to(output_dir)), "sha256": sha256_file(alignment_path)},
            "page_result": {"path": str(result_path.relative_to(output_dir)), "sha256": sha256_file(result_path)}}
    _write_json(output_dir / "review.json", review.record())
    completed_at = datetime.now(UTC).isoformat()
    run = BookRun(run_id, manifest.book_id,
        "failed" if any(item["status"] == "failed" for item in page_states)
        else "needs_review" if review.diagnostics or any(item["status"] == "needs_review" for item in page_states)
        else "succeeded", started_at, completed_at,
        {"path": str(manifest.path), "schema": manifest.schema, "sha256": manifest.sha256,
         "physical_sha256": manifest.physical_sha256, "record_sha256": manifest.record_sha256,
         "book_id": manifest.book_id, "page_order": [page.page_id for page in manifest.pages]},
        {"path": str(profile.path) if profile.path else None, "profile_id": profile.profile_id,
         "revision": profile.revision, "state": profile.state, "sha256": profile.sha256},
        {"transcript_id": transcript_id, "method": transcript_method,
         "external_source": external_record,
         "observation_ids": [item.sha256 for item in observations]},
        {"package_version": _package_version(), "git_revision": _git_revision(), **engine_identity},
        global_config_sha256, tuple(page_states),
        {"normalized_markdown": {"path": "normalized.md", "sha256": sha256_file(output_dir / "normalized.md")},
         "lexical_transcript": {"path": "lexical-transcript.json", "sha256": sha256_file(output_dir / "lexical-transcript.json")},
         "review": {"path": "review.json", "sha256": sha256_file(output_dir / "review.json")},
         "provenance": {"path": "provenance.json", "sha256": sha256_file(output_dir / "provenance.json")},
         "pages": {state["page_id"]: state["artifacts"] for state in page_states}}, len(review.diagnostics))
    record = run.record()
    _write_json(output_dir / "run.json", record)
    return record


__all__ = ["BookRun", "ReviewReport", "run_book"]
