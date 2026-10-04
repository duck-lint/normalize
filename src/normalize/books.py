"""Book source and calibration contracts, independent of engine algorithms."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

BOOK_MANIFEST_SCHEMA = "book-manifest-v1"
BOOK_MANIFEST_V2_SCHEMA = "book-manifest-v2"
BOOK_PROFILE_V1_SCHEMA = "book-profile-v1"
BOOK_PROFILE_V2_SCHEMA = "book-profile-v2"
BOOK_PROFILE_SCHEMA = BOOK_PROFILE_V1_SCHEMA
CALIBRATION_SOURCES = {"human", "measured", "detector", "imported"}


class BookContractError(ValueError):
    """A manifest or calibration profile violates its declared contract."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class CanonicalSpan:
    start: int
    end: int


@dataclass(frozen=True)
class BookPage:
    page_id: str
    image: Path
    source_sha256: str | None
    canonical_span: CanonicalSpan | None


@dataclass(frozen=True)
class BookManifest:
    book_id: str
    source_dpi: int
    canonical_source: Path | None
    pages: tuple[BookPage, ...]
    path: Path
    sha256: str
    record_sha256: str
    canonical_source_sha256: str | None
    schema: str
    physical_sha256: str


@dataclass(frozen=True)
class PageCalibration:
    page_id: str
    content_bounds: tuple[int, int, int, int] | None
    content_status: str
    orientation_degrees: int | None
    orientation_status: str
    deskew_degrees: float | None
    deskew_status: str
    source: str
    note: str


@dataclass(frozen=True)
class BookProfile:
    profile_id: str
    revision: int
    book_id: str
    manifest_sha256: str | None
    source_dpi: int
    source_dpi_source: str
    source_dpi_note: str
    state: str
    calibration_pages: tuple[str, ...]
    pages: tuple[PageCalibration, ...]
    created_at: str
    frozen_at: str | None
    path: Path | None = None
    frozen_content_sha256: str | None = None
    physical_manifest_sha256: str | None = None
    schema: str = BOOK_PROFILE_V1_SCHEMA

    @property
    def page_calibrations(self) -> Mapping[str, PageCalibration]:
        return {cal.page_id: cal for cal in self.pages}

    @property
    def sha256(self) -> str:
        return stable_digest(profile_record(self))


def _load_json(path: Path, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BookContractError(f"{path}: cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise BookContractError(f"{path}: {label} root must be an object")
    return value


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise BookContractError(f"{field} must be a positive integer")
    return value


def load_manifest(path: Path, *, validate_sources: bool = True) -> BookManifest:
    path = path.resolve()
    raw = _load_json(path, "book manifest")
    schema = raw.get("schema")
    if schema == BOOK_MANIFEST_SCHEMA:
        required_manifest_fields = {"schema", "book_id", "source_dpi", "canonical_source", "pages"}
        if set(raw) != required_manifest_fields:
            raise BookContractError(
                f"{path}: book-manifest-v1 fields must be {sorted(required_manifest_fields)}"
            )
    elif schema == BOOK_MANIFEST_V2_SCHEMA:
        required_manifest_fields = {"schema", "book_id", "source_dpi", "pages"}
        if set(raw) != required_manifest_fields:
            raise BookContractError(
                f"{path}: book-manifest-v2 fields must be {sorted(required_manifest_fields)}"
            )
    else:
        raise BookContractError(f"{path}: schema must be {BOOK_MANIFEST_SCHEMA} or {BOOK_MANIFEST_V2_SCHEMA}")
    book_id = raw["book_id"]
    if not isinstance(book_id, str) or not book_id.strip():
        raise BookContractError(f"{path}: book_id must be a non-empty string")
    dpi = _positive_int(raw["source_dpi"], "source_dpi")
    canonical_path: Path | None = None
    if schema == BOOK_MANIFEST_SCHEMA:
        canonical_ref = raw["canonical_source"]
        if not isinstance(canonical_ref, str) or not canonical_ref:
            raise BookContractError(f"{path}: canonical_source must be a path string")
        canonical_path = (path.parent / canonical_ref).resolve()
        if validate_sources and not canonical_path.is_file():
            raise BookContractError(f"canonical_source: file does not exist: {canonical_path}")
    page_records = raw["pages"]
    if not isinstance(page_records, list) or not page_records:
        raise BookContractError(f"{path}: pages must be a non-empty ordered list")
    pages: list[BookPage] = []
    page_ids: set[str] = set()
    previous_span_end = 0
    for index, record in enumerate(page_records):
        field = f"pages[{index}]"
        allowed_page_fields = {"page_id", "image", "source_sha256"}
        if schema == BOOK_MANIFEST_SCHEMA:
            allowed_page_fields.add("canonical_span")
        if (not isinstance(record, dict) or set(record) - allowed_page_fields
                or not {"page_id", "image"} <= set(record)):
            raise BookContractError(f"{field}: page fields are invalid for {schema}")
        page_id, image_ref = record["page_id"], record["image"]
        if not isinstance(page_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", page_id):
            raise BookContractError(f"{field}.page_id must be a path-safe stable identifier")
        if page_id in page_ids:
            raise BookContractError(f"{field}.page_id duplicates {page_id!r}")
        page_ids.add(page_id)
        if not isinstance(image_ref, str) or not image_ref:
            raise BookContractError(f"{field}.image must be a path string")
        image_path = (path.parent / image_ref).resolve()
        if validate_sources and not image_path.is_file():
            raise BookContractError(f"{field}.image: file does not exist: {image_path}")
        expected_hash = record.get("source_sha256")
        if schema == BOOK_MANIFEST_V2_SCHEMA and expected_hash is None:
            raise BookContractError(f"{field}.source_sha256 is required for book-manifest-v2")
        if expected_hash is not None and (not isinstance(expected_hash, str) or len(expected_hash) != 64 or any(c not in "0123456789abcdef" for c in expected_hash)):
            raise BookContractError(f"{field}.source_sha256 must be a lowercase SHA-256 digest")
        span_value = record.get("canonical_span") if schema == BOOK_MANIFEST_SCHEMA else None
        span = None
        if span_value is not None:
            if not isinstance(span_value, dict) or set(span_value) != {"start", "end"}:
                raise BookContractError(f"{field}.canonical_span must contain start and end")
            start, end = span_value["start"], span_value["end"]
            if any(isinstance(value, bool) or not isinstance(value, int) for value in (start, end)) or start < 0 or end <= start:
                raise BookContractError(f"{field}.canonical_span must be a non-empty half-open range")
            if start < previous_span_end:
                raise BookContractError(f"{field}.canonical_span overlaps or reorders preceding page spans")
            previous_span_end = end
            span = CanonicalSpan(start, end)
        pages.append(BookPage(page_id, image_path, expected_hash, span))
    canonical_hash = None
    if validate_sources and schema == BOOK_MANIFEST_SCHEMA:
        assert canonical_path is not None
        try:
            canonical_bytes = canonical_path.read_bytes()
            canonical_length = len(canonical_bytes.decode("utf-8"))
            canonical_hash = hashlib.sha256(canonical_bytes).hexdigest()
        except (OSError, UnicodeDecodeError) as exc:
            raise BookContractError(f"canonical_source: must be readable UTF-8: {exc}") from exc
    if validate_sources:
        actual_pages = []
        for index, page in enumerate(pages):
            if page.canonical_span and page.canonical_span.end > canonical_length:
                raise BookContractError(f"pages[{index}].canonical_span.end exceeds canonical source length {canonical_length}")
            actual_hash = sha256_file(page.image)
            if page.source_sha256 and actual_hash != page.source_sha256:
                raise BookContractError(f"pages[{index}].source_sha256 does not match {page.image}")
            # Freeze the observed source digest into the in-memory manifest
            # even when the human-readable record omitted it.
            actual_pages.append(BookPage(page.page_id, page.image, actual_hash, page.canonical_span))
        pages = actual_pages
    record_hash = sha256_file(path)
    physical_hash = stable_digest({
        "schema": "normalize-physical-book-identity-v1",
        "book_id": book_id,
        "source_dpi": dpi,
        "ordered_pages": [
            {"page_id": page.page_id, "source_sha256": page.source_sha256}
            for page in pages
        ],
    })
    legacy_identity_hash = stable_digest({
        "schema": schema,
        "book_id": book_id,
        "source_dpi": dpi,
        "canonical_source_sha256": canonical_hash if schema == BOOK_MANIFEST_SCHEMA else None,
        "ordered_pages": [{"page_id": page.page_id, "image": str(page.image),
                           "source_sha256": page.source_sha256,
                           "canonical_span": None if page.canonical_span is None else
                           {"start": page.canonical_span.start, "end": page.canonical_span.end}}
                          for page in pages],
    })
    # V2 is a physical-source contract. V1 preserves its historical full
    # record identity for controlled lexical fixtures.
    identity_hash = physical_hash if schema == BOOK_MANIFEST_V2_SCHEMA else legacy_identity_hash
    return BookManifest(book_id, dpi, canonical_path, tuple(pages), path, identity_hash,
                        record_hash, canonical_hash, schema, physical_hash)


def manifest_record(manifest: BookManifest, *, relative_to: Path | None = None) -> dict[str, Any]:
    """Serialize the declared source order and materialized hashes."""
    root = (relative_to or manifest.path.parent).resolve()
    record = {
        "schema": manifest.schema,
        "book_id": manifest.book_id,
        "source_dpi": manifest.source_dpi,
        "pages": [
            {"page_id": page.page_id, "image": os.path.relpath(page.image, root),
             **({"source_sha256": page.source_sha256} if page.source_sha256 else {}),
             **({"canonical_span": {"start": page.canonical_span.start, "end": page.canonical_span.end}}
                if manifest.schema == BOOK_MANIFEST_SCHEMA and page.canonical_span else {})}
            for page in manifest.pages
        ],
    }
    if manifest.schema == BOOK_MANIFEST_SCHEMA:
        assert manifest.canonical_source is not None
        record["canonical_source"] = os.path.relpath(manifest.canonical_source, root)
    return record


def save_manifest(manifest: BookManifest, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest_record(manifest, relative_to=path.parent), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _parse_calibration(record: Any, index: int) -> PageCalibration:
    field = f"pages[{index}]"
    required = {"page_id", "content_bounds", "content_status", "orientation_degrees",
                "orientation_status", "deskew_degrees", "deskew_status", "source", "note"}
    if not isinstance(record, dict) or set(record) != required:
        raise BookContractError(f"{field}: calibration fields must be {sorted(required)}")
    page_id = record["page_id"]
    if not isinstance(page_id, str) or not page_id:
        raise BookContractError(f"{field}.page_id must be non-empty")
    source, note = record["source"], record["note"]
    if not isinstance(source, str) or source not in CALIBRATION_SOURCES:
        raise BookContractError(f"{field}.source must be one of {sorted(CALIBRATION_SOURCES)}")
    if not isinstance(note, str) or not note.strip():
        raise BookContractError(f"{field}.note must explain measurement provenance")
    bounds = record["content_bounds"]
    if bounds is not None:
        if not isinstance(bounds, list) or len(bounds) != 4 or any(isinstance(v, bool) or not isinstance(v, int) for v in bounds):
            raise BookContractError(f"{field}.content_bounds must be null or [x0,y0,x1,y1]")
        x0, y0, x1, y1 = bounds
        if x0 < 0 or y0 < 0 or x1 <= x0 or y1 <= y0:
            raise BookContractError(f"{field}.content_bounds must be a non-empty half-open rectangle")
        bounds_value = (x0, y0, x1, y1)
    else:
        bounds_value = None
    content_status = record["content_status"]
    if not isinstance(content_status, str) or content_status not in {"measured", "full_page", "unresolved"}:
        raise BookContractError(f"{field}.content_status is invalid")
    if (content_status == "measured") != (bounds_value is not None):
        raise BookContractError(f"{field}.content_status must be measured exactly when content_bounds is provided")
    orientation = record["orientation_degrees"]
    orientation_status = record["orientation_status"]
    if not isinstance(orientation_status, str) or orientation_status not in {"measured", "no_transform", "unresolved"}:
        raise BookContractError(f"{field}.orientation_status is invalid")
    if orientation is not None and (isinstance(orientation, bool) or not isinstance(orientation, int) or orientation not in {0, 90, 180, 270}):
        raise BookContractError(f"{field}.orientation_degrees must be null or one of 0, 90, 180, 270")
    if orientation_status == "unresolved" and orientation is not None:
        raise BookContractError(f"{field}.orientation_degrees must be null when orientation is unresolved")
    if orientation_status == "no_transform" and orientation != 0:
        raise BookContractError(f"{field}.orientation_degrees must be 0 for no_transform")
    if orientation_status == "measured" and orientation is None:
        raise BookContractError(f"{field}.orientation_degrees is required for measured orientation")
    angle = record["deskew_degrees"]
    deskew_status = record["deskew_status"]
    if not isinstance(deskew_status, str) or deskew_status not in {"measured", "no_transform", "unresolved"}:
        raise BookContractError(f"{field}.deskew_status is invalid")
    if angle is not None:
        if isinstance(angle, bool) or not isinstance(angle, (int, float)) or not math.isfinite(float(angle)) or abs(float(angle)) > 45:
            raise BookContractError(f"{field}.deskew_degrees must be a finite angle with magnitude at most 45")
        angle = float(angle)
    if deskew_status == "unresolved" and angle is not None:
        raise BookContractError(f"{field}.deskew_degrees must be null when deskew is unresolved")
    if deskew_status == "no_transform" and angle != 0:
        raise BookContractError(f"{field}.deskew_degrees must be 0 for no_transform")
    if deskew_status == "measured" and angle is None:
        raise BookContractError(f"{field}.deskew_degrees is required for measured deskew")
    return PageCalibration(page_id, bounds_value, content_status, orientation, orientation_status,
                           angle, deskew_status, source, note)


def load_profile(path: Path) -> BookProfile:
    path = path.resolve()
    raw = _load_json(path, "book profile")
    schema = raw.get("schema")
    common_fields = {"schema", "profile_id", "revision", "book_id", "source_dpi",
                     "source_dpi_provenance", "state", "calibration_pages", "created_at",
                     "frozen_at", "frozen_content_sha256", "pages"}
    if schema == BOOK_PROFILE_V1_SCHEMA:
        required = common_fields | {"manifest_sha256"}
        manifest_hash = raw.get("manifest_sha256")
        physical_hash = None
    elif schema == BOOK_PROFILE_V2_SCHEMA:
        required = common_fields | {"physical_manifest_sha256"}
        manifest_hash = None
        physical_hash = raw.get("physical_manifest_sha256")
    else:
        raise BookContractError(f"{path}: schema must be {BOOK_PROFILE_V1_SCHEMA} or {BOOK_PROFILE_V2_SCHEMA}")
    if set(raw) != required:
        raise BookContractError(f"{path}: invalid {schema} shape")
    profile_id = raw["profile_id"]
    if not isinstance(profile_id, str) or not profile_id.strip():
        raise BookContractError("profile_id must be a non-empty string")
    revision = _positive_int(raw["revision"], "revision")
    book_id = raw["book_id"]
    if not isinstance(book_id, str) or not book_id:
        raise BookContractError("book_id must be a non-empty string")
    identity_hash = manifest_hash if schema == BOOK_PROFILE_V1_SCHEMA else physical_hash
    identity_field = "manifest_sha256" if schema == BOOK_PROFILE_V1_SCHEMA else "physical_manifest_sha256"
    if not isinstance(identity_hash, str) or len(identity_hash) != 64 or any(char not in "0123456789abcdef" for char in identity_hash):
        raise BookContractError(f"{identity_field} must be a SHA-256 digest")
    dpi = _positive_int(raw["source_dpi"], "source_dpi")
    dpi_provenance = raw["source_dpi_provenance"]
    if not isinstance(dpi_provenance, dict) or set(dpi_provenance) != {"source", "note"}:
        raise BookContractError("source_dpi_provenance must contain source and note")
    dpi_source, dpi_note = dpi_provenance["source"], dpi_provenance["note"]
    if not isinstance(dpi_source, str) or dpi_source not in CALIBRATION_SOURCES:
        raise BookContractError(f"source_dpi_provenance.source must be one of {sorted(CALIBRATION_SOURCES)}")
    if not isinstance(dpi_note, str) or not dpi_note.strip():
        raise BookContractError("source_dpi_provenance.note must explain the DPI provenance")
    state = raw["state"]
    if not isinstance(state, str) or state not in {"draft", "frozen"}:
        raise BookContractError("state must be draft or frozen")
    calibration_pages = raw["calibration_pages"]
    if not isinstance(calibration_pages, list) or any(not isinstance(p, str) or not p for p in calibration_pages):
        raise BookContractError("calibration_pages must be a list of page IDs")
    created_at = raw["created_at"]
    frozen_at = raw["frozen_at"]
    if not isinstance(created_at, str) or not created_at:
        raise BookContractError("created_at must be a timestamp")
    if (state == "frozen") != (isinstance(frozen_at, str) and bool(frozen_at)):
        raise BookContractError("frozen_at must be present exactly for frozen profiles")
    page_values = raw["pages"]
    if not isinstance(page_values, list) or not page_values:
        raise BookContractError("pages must contain per-page calibration observations")
    pages = tuple(_parse_calibration(value, index) for index, value in enumerate(page_values))
    if len({page.page_id for page in pages}) != len(pages):
        raise BookContractError("profile has duplicate page calibration entries")
    if len(set(calibration_pages)) != len(calibration_pages):
        raise BookContractError("calibration_pages contains duplicate page IDs")
    frozen_digest = raw["frozen_content_sha256"]
    profile = BookProfile(profile_id, revision, book_id, manifest_hash, dpi, dpi_source, dpi_note,
                          state, tuple(calibration_pages), pages, created_at, frozen_at, path,
                          frozen_digest, physical_hash, schema)
    if state == "frozen":
        if not isinstance(frozen_digest, str) or len(frozen_digest) != 64 or frozen_digest != _freeze_digest(profile):
            raise BookContractError("frozen profile integrity digest mismatch")
    elif frozen_digest is not None:
        raise BookContractError("draft profile cannot contain frozen_content_sha256")
    return profile


def profile_record(profile: BookProfile) -> dict[str, Any]:
    record = {
        "schema": profile.schema,
        "profile_id": profile.profile_id,
        "revision": profile.revision,
        "book_id": profile.book_id,
        "source_dpi": profile.source_dpi,
        "source_dpi_provenance": {"source": profile.source_dpi_source, "note": profile.source_dpi_note},
        "state": profile.state,
        "calibration_pages": list(profile.calibration_pages),
        "created_at": profile.created_at,
        "frozen_at": profile.frozen_at,
        "frozen_content_sha256": profile.frozen_content_sha256,
        "pages": [
            {"page_id": page.page_id, "content_bounds": list(page.content_bounds) if page.content_bounds else None,
             "content_status": page.content_status, "orientation_degrees": page.orientation_degrees,
             "orientation_status": page.orientation_status, "deskew_degrees": page.deskew_degrees,
             "deskew_status": page.deskew_status, "source": page.source, "note": page.note}
            for page in profile.pages
        ],
    }
    if profile.schema == BOOK_PROFILE_V1_SCHEMA:
        record["manifest_sha256"] = profile.manifest_sha256
    elif profile.schema == BOOK_PROFILE_V2_SCHEMA:
        record["physical_manifest_sha256"] = profile.physical_manifest_sha256
    else:
        raise BookContractError(f"unsupported profile schema {profile.schema!r}")
    return record


def _freeze_digest(profile: BookProfile) -> str:
    record = profile_record(profile)
    record.pop("frozen_content_sha256")
    return stable_digest(record)


def validate_profile_for_manifest(profile: BookProfile, manifest: BookManifest, *, require_frozen: bool = False) -> None:
    if profile.book_id != manifest.book_id:
        raise BookContractError(f"profile.book_id {profile.book_id!r} does not match manifest.book_id {manifest.book_id!r}")
    if manifest.schema == BOOK_MANIFEST_SCHEMA:
        if profile.schema != BOOK_PROFILE_V1_SCHEMA:
            raise BookContractError("book-manifest-v1 requires book-profile-v1")
        if profile.manifest_sha256 != manifest.sha256:
            raise BookContractError("profile.manifest_sha256 does not match the loaded v1 manifest identity")
    elif manifest.schema == BOOK_MANIFEST_V2_SCHEMA:
        if profile.schema != BOOK_PROFILE_V2_SCHEMA:
            raise BookContractError("book-manifest-v2 requires book-profile-v2")
        if profile.physical_manifest_sha256 != manifest.physical_sha256:
            raise BookContractError("profile.physical_manifest_sha256 does not match physical book identity")
    else:
        raise BookContractError(f"unsupported manifest schema {manifest.schema!r}")
    if profile.source_dpi != manifest.source_dpi:
        raise BookContractError("profile.source_dpi does not match manifest.source_dpi")
    manifest_ids = [page.page_id for page in manifest.pages]
    profile_ids = [page.page_id for page in profile.pages]
    unknown = sorted(set(profile_ids) - set(manifest_ids))
    missing = sorted(set(manifest_ids) - set(profile_ids))
    if any(not isinstance(page_id, str) for page_id in profile.calibration_pages):
        raise BookContractError("calibration_pages must contain only page IDs")
    calibration_unknown = sorted(set(profile.calibration_pages) - set(manifest_ids))
    if unknown or missing or calibration_unknown:
        raise BookContractError(f"profile page calibration mismatch; unknown={unknown}, missing={missing}, unknown_calibration_pages={calibration_unknown}")
    if require_frozen and profile.state != "frozen":
        raise BookContractError("whole-book run requires a frozen BookProfile")
    for source_page, cal in zip(manifest.pages, (profile.page_calibrations[p] for p in manifest_ids), strict=True):
        if cal.content_bounds:
            try:
                from PIL import Image
                with Image.open(source_page.image) as image:
                    width, height = image.size
            except OSError as exc:
                raise BookContractError(f"page {source_page.page_id}: cannot inspect image dimensions: {exc}") from exc
            x0, y0, x1, y1 = cal.content_bounds
            if x1 > width or y1 > height:
                raise BookContractError(f"page {source_page.page_id}.content_bounds {cal.content_bounds} exceed image dimensions {(width, height)}")


def freeze_profile(profile: BookProfile, manifest: BookManifest) -> BookProfile:
    validate_profile_for_manifest(profile, manifest)
    if profile.state != "draft":
        raise BookContractError("profile is already frozen; create an explicit new revision to recalibrate")
    candidate = BookProfile(profile.profile_id, profile.revision, profile.book_id, profile.manifest_sha256,
                            profile.source_dpi, profile.source_dpi_source, profile.source_dpi_note,
                            "frozen", profile.calibration_pages, profile.pages,
                            profile.created_at, datetime.now(UTC).isoformat(), profile.path,
                            physical_manifest_sha256=profile.physical_manifest_sha256,
                            schema=profile.schema)
    frozen = BookProfile(candidate.profile_id, candidate.revision, candidate.book_id,
                         candidate.manifest_sha256, candidate.source_dpi, candidate.source_dpi_source,
                         candidate.source_dpi_note, candidate.state, candidate.calibration_pages,
                         candidate.pages, candidate.created_at, candidate.frozen_at,
                         candidate.path, _freeze_digest(candidate),
                         candidate.physical_manifest_sha256, candidate.schema)
    validate_profile_for_manifest(frozen, manifest, require_frozen=True)
    return frozen


def revise_profile(profile: BookProfile, manifest: BookManifest) -> BookProfile:
    """Start a new identifiable draft revision without mutating a frozen one."""
    validate_profile_for_manifest(profile, manifest)
    return BookProfile(profile.profile_id, profile.revision + 1, profile.book_id, profile.manifest_sha256,
                       profile.source_dpi, profile.source_dpi_source, profile.source_dpi_note,
                       "draft", profile.calibration_pages, profile.pages,
                       datetime.now(UTC).isoformat(), None,
                       physical_manifest_sha256=profile.physical_manifest_sha256,
                       schema=profile.schema)


def save_profile(profile: BookProfile, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile_record(profile), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def draft_profile_from_record(record: Mapping[str, Any], manifest: BookManifest, *, profile_id: str) -> BookProfile:
    """Validate supplied manual/imported measurements and bind a draft to a manifest."""
    if not isinstance(record, Mapping) or set(record) != {"source_dpi", "source_dpi_provenance", "calibration_pages", "pages"}:
        raise BookContractError("calibration measurements must contain source_dpi, source_dpi_provenance, calibration_pages, pages")
    dpi = _positive_int(record["source_dpi"], "source_dpi")
    dpi_provenance = record["source_dpi_provenance"]
    if not isinstance(dpi_provenance, dict) or set(dpi_provenance) != {"source", "note"}:
        raise BookContractError("source_dpi_provenance must contain source and note")
    dpi_source, dpi_note = dpi_provenance["source"], dpi_provenance["note"]
    if not isinstance(dpi_source, str) or dpi_source not in CALIBRATION_SOURCES or not isinstance(dpi_note, str) or not dpi_note.strip():
        raise BookContractError("source_dpi_provenance requires a supported source and non-empty note")
    calibration_page_ids = record["calibration_pages"]
    if not isinstance(calibration_page_ids, list) or any(not isinstance(page_id, str) or not page_id for page_id in calibration_page_ids):
        raise BookContractError("calibration_pages must be a list of non-empty page IDs")
    if len(set(calibration_page_ids)) != len(calibration_page_ids):
        raise BookContractError("calibration_pages contains duplicate page IDs")
    pages_value = record["pages"]
    if not isinstance(pages_value, list):
        raise BookContractError("calibration pages must be a list")
    pages = tuple(_parse_calibration(value, index) for index, value in enumerate(pages_value))
    if manifest.schema == BOOK_MANIFEST_SCHEMA:
        profile = BookProfile(profile_id, 1, manifest.book_id, manifest.sha256, dpi,
                              dpi_source, dpi_note, "draft", tuple(calibration_page_ids), pages,
                              datetime.now(UTC).isoformat(), None, schema=BOOK_PROFILE_V1_SCHEMA)
    else:
        profile = BookProfile(profile_id, 1, manifest.book_id, None, dpi, dpi_source, dpi_note,
                              "draft", tuple(calibration_page_ids), pages,
                              datetime.now(UTC).isoformat(), None,
                              physical_manifest_sha256=manifest.physical_sha256,
                              schema=BOOK_PROFILE_V2_SCHEMA)
    validate_profile_for_manifest(profile, manifest)
    return profile


def revised_draft_from_record(record: Mapping[str, Any], manifest: BookManifest,
                              previous: BookProfile) -> BookProfile:
    """Build a new draft revision from replacement measurements explicitly."""
    validate_profile_for_manifest(previous, manifest, require_frozen=True)
    draft = draft_profile_from_record(record, manifest, profile_id=previous.profile_id)
    return BookProfile(draft.profile_id, previous.revision + 1, draft.book_id,
                       draft.manifest_sha256, draft.source_dpi,
                       draft.source_dpi_source, draft.source_dpi_note, "draft",
                       draft.calibration_pages, draft.pages, draft.created_at, None,
                       physical_manifest_sha256=draft.physical_manifest_sha256,
                       schema=draft.schema)
