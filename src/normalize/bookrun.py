"""Deterministic ordered-book orchestration and factual review aggregation."""

from __future__ import annotations

import json
import hashlib
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Mapping

from .books import BookContractError, BookManifest, BookProfile, sha256_file, stable_digest, validate_profile_for_manifest
from .engine import BookEngine
from .markdown import document_record
from .reconstruction import PageSpan


@dataclass(frozen=True)
class ReviewReport:
    book_id: str
    run_id: str
    diagnostics: tuple[Mapping[str, Any], ...]

    def record(self) -> dict[str, Any]:
        return {"schema": "normalize-review-v1", "book_id": self.book_id,
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
    canonical_source: Mapping[str, Any]
    engine: Mapping[str, Any]
    global_config_sha256: str
    pages: tuple[Mapping[str, Any], ...]
    artifacts: Mapping[str, Any]
    review_diagnostic_count: int

    def record(self) -> dict[str, Any]:
        return {
            "schema": "normalize-book-run-v1", "run_id": self.run_id, "book_id": self.book_id,
            "started_at": self.started_at, "completed_at": self.completed_at,
            "manifest": dict(self.manifest), "profile": dict(self.profile),
            "canonical_source": dict(self.canonical_source), "engine": dict(self.engine),
            "global_config_sha256": self.global_config_sha256, "status": self.status,
            "pages": [dict(page) for page in self.pages], "artifacts": dict(self.artifacts),
            "review_diagnostic_count": self.review_diagnostic_count,
        }


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


def _empty_geometry(page_id: str, book_id: str, index: int, image_path: Path, source_hash: str, dpi: int) -> dict[str, Any]:
    """Keep failed pages in order so their canonical text is still projected."""
    return {
        "page_id": page_id, "side": page_id, "width_px": 0, "height_px": 0,
        "tokens": [], "physical_lines": [], "status": "failure",
        "errors": ["page_processing_failed"], "uncertainties": [],
        "error_details": [], "measurements": {}, "engine": {},
        "provenance": {"book_id": book_id, "page_id": page_id, "page_index": index,
                       "source_image": str(image_path), "source_image_sha256": source_hash, "dpi": dpi},
    }


def _review_diagnostics(document_record_value: Mapping[str, Any], page_states: list[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    diagnostics: list[dict[str, Any]] = []
    for state in page_states:
        page_id = state["page_id"]
        if state["status"] == "failed":
            diagnostics.append({"code": "page_processing_failed", "page_id": page_id,
                                "reason": state.get("error"), "source_sha256": state.get("source_sha256")})
        for item in state.get("geometry_diagnostics", []):
            diagnostics.append({"page_id": page_id, **item})
    for item in document_record_value.get("diagnostics", []):
        diagnostics.append(dict(item))
    # Stable de-duplication keeps repeated stage references factual but concise.
    unique: dict[str, dict[str, Any]] = {}
    for item in diagnostics:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        unique.setdefault(key, item)
    return tuple(unique.values())


def run_book(manifest: BookManifest, profile: BookProfile, output_dir: Path,
             *, engine: BookEngine | None = None, resume: bool = True) -> dict[str, Any]:
    """Run ordered page images through fixed engine stages and emit reviewable artifacts."""
    validate_profile_for_manifest(profile, manifest, require_frozen=True)
    if sha256_file(manifest.path) != manifest.record_sha256:
        raise BookContractError("book manifest changed after it was loaded; reload it and validate the profile again")
    if manifest.canonical_source_sha256 is None or sha256_file(manifest.canonical_source) != manifest.canonical_source_sha256:
        raise BookContractError("canonical source changed after manifest validation; reload the manifest and freeze a matching profile")
    if any(page.source_sha256 is None for page in manifest.pages):
        raise BookContractError("whole-book run requires a source-validated BookManifest")
    if not all(page.canonical_span for page in manifest.pages):
        missing = [page.page_id for page in manifest.pages if page.canonical_span is None]
        raise BookContractError(f"whole-book run requires canonical spans for every page; missing={missing}")
    spans = [page.canonical_span for page in manifest.pages]
    assert all(span is not None for span in spans)
    canonical_bytes = manifest.canonical_source.read_bytes()
    try:
        canonical_source = canonical_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BookContractError(f"canonical source is not UTF-8: {exc}") from exc
    if spans[0].start != 0 or spans[-1].end != len(canonical_source) or any(
        left.end != right.start for left, right in zip(spans, spans[1:])
    ):
        raise BookContractError("whole-book canonical spans must cover the complete source contiguously in page order")

    engine = engine or BookEngine()
    engine_identity = engine.identity
    output_dir = output_dir.resolve()
    pages_dir = output_dir / "pages"
    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(UTC).isoformat()
    raw_text_hash = hashlib.sha256(canonical_bytes).hexdigest()
    engine_build = {"package_version": _package_version(), "git_revision": _git_revision(), **engine_identity}
    global_config_sha256 = stable_digest(engine.config.record())
    run_identity = {
        "manifest_sha256": manifest.sha256,
        "manifest_record_sha256": manifest.record_sha256,
        "profile_sha256": profile.sha256,
        "canonical_source_sha256": raw_text_hash,
        "engine": engine_build,
        "global_config_sha256": global_config_sha256,
    }
    run_id = stable_digest(run_identity)
    page_states: list[dict[str, Any]] = []
    geometry_by_id: dict[str, dict[str, Any]] = {}
    calibrations = profile.page_calibrations

    for index, page in enumerate(manifest.pages):
        calibration = calibrations[page.page_id]
        source_error = None
        try:
            source_hash = sha256_file(page.image)
        except OSError as exc:
            source_hash = "unavailable"
            source_error = f"{type(exc).__name__}: {exc}"
        page_engine_key = stable_digest({
            "book_id": manifest.book_id,
            "page_id": page.page_id,
            "page_index": index,
            "source_path": str(page.image),
            "source_sha256": source_hash,
            "page_calibration": {
                "bounds": calibration.content_bounds,
                "content_status": calibration.content_status,
                "orientation_degrees": calibration.orientation_degrees,
                "orientation_status": calibration.orientation_status,
                "deskew_degrees": calibration.deskew_degrees,
                "deskew_status": calibration.deskew_status,
                "source": calibration.source,
                "note": calibration.note,
            },
            "source_dpi": profile.source_dpi,
            "engine_identity": engine_identity,
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
                                                  page_index=index, source_dpi=profile.source_dpi,
                                                  source_sha256=source_hash)
                state = "needs_review" if (
                    calibration.content_status == "unresolved" or calibration.orientation_status == "unresolved"
                    or calibration.deskew_status == "unresolved"
                    or page_result["geometry"].get("status") != "success"
                ) else "succeeded"
            except Exception as exc:  # isolate a failed page and continue preserving order
                error = f"{type(exc).__name__}: {exc}"
                page_result = {"page_id": page.page_id, "page_index": index,
                               "source_image": str(page.image), "source_sha256": source_hash,
                               "geometry": _empty_geometry(page.page_id, manifest.book_id, index,
                                                            page.image, source_hash, profile.source_dpi)}
                state = "failed"
            _write_json(cached_path, {"schema": "book-page-cache-v1", "cache_key": page_engine_key,
                                      "status": state, "error": error, "result": page_result})
        else:
            cache_wrapper = json.loads(cached_path.read_text(encoding="utf-8"))
            state = cache_wrapper.get("status", "needs_review")
            error = cache_wrapper.get("error")
        geometry = page_result["geometry"]
        geometry_by_id[page.page_id] = geometry
        geometry_diagnostics = []
        for field in ("errors", "uncertainties"):
            for code in geometry.get(field, []):
                severity = "error" if field == "errors" else "uncertainty"
                geometry_diagnostics.append({"code": code, "source": "geometry", "severity": severity})
        geometry_diagnostics.extend(
            {"source": "geometry", "severity": "error", **detail}
            for detail in geometry.get("error_details", []) if isinstance(detail, dict)
        )
        page_states.append({"page_id": page.page_id, "page_index": index, "status": state,
                            "cache_hit": cache_hit, "source_sha256": source_hash, "error": error,
                            "geometry_diagnostics": geometry_diagnostics,
                            "canonical_span": {"start": spans[index].start, "end": spans[index].end}})

    page_spans = [PageSpan(page.page_id, spans[index].start, spans[index].end, geometry_by_id[page.page_id])
                  for index, page in enumerate(manifest.pages)]
    document = engine.reconstruct(canonical_source, str(manifest.canonical_source), page_spans)
    serialized_document = document_record(document)
    markdown = engine.emit(document)
    review = ReviewReport(manifest.book_id, run_id, _review_diagnostics(serialized_document, page_states))
    (output_dir / "normalized.md").write_text(markdown, encoding="utf-8")
    _write_json(output_dir / "provenance.json", serialized_document)
    review_record = review.record()
    _write_json(output_dir / "review.json", review_record)
    page_artifacts: dict[str, dict[str, Any]] = {}
    for index, page in enumerate(manifest.pages):
        alignment = document.alignments[index]
        geometry_path = pages_dir / page.page_id / "geometry.json"
        alignment_path = pages_dir / page.page_id / "alignment.json"
        _write_json(geometry_path, geometry_by_id[page.page_id])
        _write_json(alignment_path, {
            "schema": "page-alignment-v1", "page_id": page.page_id,
            "canonical_span": {"start": spans[index].start, "end": spans[index].end},
            "canonical_tokens": [
                {"source_id": token.source_id, "start": token.start, "end": token.end, "text": token.text}
                for token in alignment.canonical_tokens
            ],
            "links": [
                {"canonical_token_indices": list(link.canonical_token_indices), "anchor_ids": list(link.anchor_ids),
                 "physical_line_ids": list(link.physical_line_ids), "relation": link.relation,
                 "cost": link.cost, "ambiguous": link.ambiguous}
                for link in alignment.links
            ],
            "unmatched_canonical_indices": list(alignment.unmatched_canonical_indices),
            "unmatched_anchor_ids": list(alignment.unmatched_anchor_ids),
            "diagnostics": list(alignment.diagnostics),
        })
        result_path = pages_dir / page.page_id / "page-result.json"
        page_states[index]["artifacts"] = {
            "geometry": {"path": str(geometry_path.relative_to(output_dir)), "sha256": sha256_file(geometry_path)},
            "alignment": {"path": str(alignment_path.relative_to(output_dir)), "sha256": sha256_file(alignment_path)},
            "page_result": {"path": str(result_path.relative_to(output_dir)), "sha256": sha256_file(result_path)},
        }
    completed_at = datetime.now(UTC).isoformat()
    run = BookRun(
        run_id=run_id,
        book_id=manifest.book_id,
        started_at=started_at,
        completed_at=completed_at,
        manifest={"path": str(manifest.path), "sha256": manifest.sha256,
                  "record_sha256": manifest.record_sha256,
                  "canonical_source_sha256": manifest.canonical_source_sha256,
                  "book_id": manifest.book_id,
                  "page_order": [page.page_id for page in manifest.pages]},
        profile={"path": str(profile.path) if profile.path else None, "profile_id": profile.profile_id,
                 "revision": profile.revision, "state": profile.state, "sha256": profile.sha256},
        canonical_source={"path": str(manifest.canonical_source), "sha256": raw_text_hash},
        engine=engine_build,
        global_config_sha256=global_config_sha256,
        status="failed" if any(state["status"] == "failed" for state in page_states)
        else "needs_review" if review.diagnostics or any(state["status"] == "needs_review" for state in page_states)
        else "succeeded",
        pages=tuple(page_states),
        artifacts={
            "normalized_markdown": {"path": "normalized.md", "sha256": sha256_file(output_dir / "normalized.md")},
            "review": {"path": "review.json", "sha256": sha256_file(output_dir / "review.json")},
            "provenance": {"path": "provenance.json", "sha256": sha256_file(output_dir / "provenance.json")},
            "pages": {state["page_id"]: state["artifacts"] for state in page_states},
        },
        review_diagnostic_count=len(review.diagnostics),
    )
    run_record = run.record()
    _write_json(output_dir / "run.json", run_record)
    return run_record


__all__ = ["BookRun", "ReviewReport", "run_book"]
