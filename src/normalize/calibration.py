"""Generic proposal validation and explicitly authorized profile updates."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image

from .books import (
    BOOK_MANIFEST_V2_SCHEMA,
    CALIBRATION_SOURCES,
    BookContractError,
    BookManifest,
    BookProfile,
    draft_profile_from_record,
    stable_digest,
    validate_profile_for_manifest,
)

CALIBRATION_PROPOSAL_SCHEMA = "calibration-proposal-v1"
CALIBRATION_ACCEPTANCE_SCHEMA = "calibration-acceptance-v1"
PROPOSED_FIELDS = ("content_bounds", "orientation_degrees", "deskew_degrees")
_PRODUCER_FIELDS = {"source", "method", "evidence_sha256", "note"}
_PROPOSAL_FIELDS = {
    "schema", "proposal_id", "book_id", "physical_manifest_sha256", "producer", "pages",
}


@dataclass(frozen=True)
class CalibrationProposal:
    """A physical-manifest-bound set of sparse candidate values."""

    proposal_id: str
    book_id: str
    physical_manifest_sha256: str
    producer: Mapping[str, str]
    pages: tuple[Mapping[str, Any], ...]

    def record(self) -> dict[str, Any]:
        return {
            "schema": CALIBRATION_PROPOSAL_SCHEMA,
            "proposal_id": self.proposal_id,
            "book_id": self.book_id,
            "physical_manifest_sha256": self.physical_manifest_sha256,
            "producer": dict(self.producer),
            "pages": [dict(page) for page in self.pages],
        }


def _identity_payload(book_id: str, physical_manifest_sha256: str,
                      producer: Mapping[str, str],
                      pages: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    # The payload has no source paths or output locations. Evidence is linked
    # only by its content digest, so relocating files does not change identity.
    return {
        "schema": CALIBRATION_PROPOSAL_SCHEMA,
        "book_id": book_id,
        "physical_manifest_sha256": physical_manifest_sha256,
        "producer": dict(producer),
        "pages": [dict(page) for page in pages],
    }


def _validate_manifest(manifest: BookManifest) -> None:
    if manifest.schema != BOOK_MANIFEST_V2_SCHEMA:
        raise BookContractError("calibration proposals require book-manifest-v2")


def _validate_producer(producer: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(producer, Mapping):
        raise BookContractError("proposal.producer must be an object")
    if set(producer) != _PRODUCER_FIELDS:
        raise BookContractError(f"proposal producer fields must be {sorted(_PRODUCER_FIELDS)}")
    source, method, evidence_hash, note = (producer[key] for key in
                                           ("source", "method", "evidence_sha256", "note"))
    if not isinstance(source, str) or source not in CALIBRATION_SOURCES:
        raise BookContractError(f"proposal producer.source must be one of {sorted(CALIBRATION_SOURCES)}")
    if not isinstance(method, str) or not method.strip():
        raise BookContractError("proposal producer.method must be a non-empty string")
    if (not isinstance(evidence_hash, str) or len(evidence_hash) != 64
            or any(char not in "0123456789abcdef" for char in evidence_hash)):
        raise BookContractError("proposal producer.evidence_sha256 must be a lowercase SHA-256 digest")
    if not isinstance(note, str) or not note.strip():
        raise BookContractError("proposal producer.note must be non-empty")
    return {"source": source, "method": method, "evidence_sha256": evidence_hash, "note": note}


def _validate_page_values(manifest: BookManifest, values: Mapping[str, Any], index: int) -> dict[str, Any]:
    if not isinstance(values, Mapping):
        raise BookContractError(f"proposal.pages[{index}] values must be an object")
    provided_fields = set(values) - {"page_id"}
    if not provided_fields or not provided_fields <= set(PROPOSED_FIELDS):
        raise BookContractError(
            f"proposal.pages[{index}].values must contain at least one of {list(PROPOSED_FIELDS)}"
        )
    normalized = dict(values)
    page_id = values.get("page_id")
    if not isinstance(page_id, str) or not page_id:
        raise BookContractError(f"proposal.pages[{index}].page_id must be non-empty")
    if any(value is None for key, value in values.items() if key != "page_id"):
        raise BookContractError(f"proposal.pages[{index}] uses null; omit fields without a proposed value")

    if "content_bounds" in values:
        bounds = values["content_bounds"]
        if (not isinstance(bounds, list) or len(bounds) != 4
                or any(isinstance(value, bool) or not isinstance(value, int) for value in bounds)):
            raise BookContractError(f"proposal page {page_id}.content_bounds must be [x0,y0,x1,y1]")
        x0, y0, x1, y1 = bounds
        if x0 < 0 or y0 < 0 or x1 <= x0 or y1 <= y0:
            raise BookContractError(f"proposal page {page_id}.content_bounds must be a non-empty half-open rectangle")
        page = next((item for item in manifest.pages if item.page_id == page_id), None)
        if page is None:
            raise BookContractError(f"proposal page {page_id!r} is not in BookManifest v2")
        try:
            with Image.open(page.image) as image:
                width, height = image.size
        except OSError as exc:
            raise BookContractError(f"proposal page {page_id}: cannot inspect source image dimensions: {exc}") from exc
        if x1 > width or y1 > height:
            raise BookContractError(
                f"proposal page {page_id}.content_bounds {bounds} exceed image dimensions {(width, height)}"
            )

    if "orientation_degrees" in values:
        orientation = values["orientation_degrees"]
        if (isinstance(orientation, bool) or not isinstance(orientation, int)
                or orientation not in {0, 90, 180, 270}):
            raise BookContractError(
                f"proposal page {page_id}.orientation_degrees must be one of 0, 90, 180, 270"
            )

    if "deskew_degrees" in values:
        angle = values["deskew_degrees"]
        if (isinstance(angle, bool) or not isinstance(angle, (int, float))
                or not math.isfinite(float(angle)) or abs(float(angle)) > 45):
            raise BookContractError(
                f"proposal page {page_id}.deskew_degrees must be finite and have magnitude at most 45"
            )
        normalized["deskew_degrees"] = float(angle)
    normalized["page_id"] = page_id
    return normalized


def create_calibration_proposal(manifest: BookManifest, producer: Mapping[str, Any],
                                pages: Sequence[Mapping[str, Any]]) -> CalibrationProposal:
    """Validate sparse candidate values and assign a content-derived identity."""
    _validate_manifest(manifest)
    normalized_producer = _validate_producer(producer)
    if not isinstance(pages, Sequence) or isinstance(pages, (str, bytes)) or not pages:
        raise BookContractError("proposal.pages must be a non-empty ordered list")
    order = {page.page_id: index for index, page in enumerate(manifest.pages)}
    normalized_pages = []
    seen: set[str] = set()
    last_order = -1
    for index, page in enumerate(pages):
        if not isinstance(page, Mapping) or set(page) != {"page_id", "values"}:
            raise BookContractError(f"proposal.pages[{index}] must contain page_id and values")
        page_id = page["page_id"]
        if not isinstance(page_id, str) or page_id not in order:
            raise BookContractError(f"proposal.pages[{index}].page_id is not in BookManifest v2")
        if page_id in seen:
            raise BookContractError(f"proposal contains duplicate page ID {page_id!r}")
        if order[page_id] <= last_order:
            raise BookContractError("proposal pages must follow BookManifest v2 order")
        values = dict(page["values"]) if isinstance(page["values"], Mapping) else page["values"]
        if not isinstance(values, dict):
            raise BookContractError(f"proposal.pages[{index}].values must be an object")
        if "page_id" in values:
            raise BookContractError(f"proposal.pages[{index}].values must not repeat page_id")
        normalized = _validate_page_values(manifest, {"page_id": page_id, **values}, index)
        normalized_pages.append({"page_id": page_id,
                                 "values": {key: value for key, value in normalized.items()
                                            if key != "page_id"}})
        seen.add(page_id)
        last_order = order[page_id]

    payload = _identity_payload(manifest.book_id, manifest.physical_sha256,
                                normalized_producer, normalized_pages)
    return CalibrationProposal(stable_digest(payload), manifest.book_id,
                               manifest.physical_sha256, normalized_producer,
                               tuple(normalized_pages))


def create_empty_calibration_draft(manifest: BookManifest, *, profile_id: str) -> BookProfile:
    """Create a v2 draft with no accepted calibration values."""
    _validate_manifest(manifest)
    if not isinstance(profile_id, str) or not profile_id.strip():
        raise BookContractError("profile_id must be a non-empty string")
    record = {
        "source_dpi": manifest.source_dpi,
        "source_dpi_provenance": {
            "source": "imported",
            "note": "Nominal source DPI declared by BookManifest v2.",
        },
        "calibration_pages": [],
        "pages": [
            {"page_id": page.page_id, "content_bounds": None, "content_status": "unresolved",
             "orientation_degrees": None, "orientation_status": "unresolved",
             "deskew_degrees": None, "deskew_status": "unresolved",
             "source": "human", "note": "No calibration proposal accepted; awaiting review."}
            for page in manifest.pages
        ],
    }
    return draft_profile_from_record(record, manifest, profile_id=profile_id)


def validate_calibration_proposal(proposal: CalibrationProposal,
                                  manifest: BookManifest) -> None:
    """Validate a proposal without constructing or requiring a BookProfile."""
    _validate_manifest(manifest)
    if proposal.book_id != manifest.book_id:
        raise BookContractError("proposal.book_id does not match BookManifest v2")
    if proposal.physical_manifest_sha256 != manifest.physical_sha256:
        raise BookContractError("proposal.physical_manifest_sha256 does not match BookManifest v2")
    rebuilt = create_calibration_proposal(manifest, proposal.producer, proposal.pages)
    if proposal.proposal_id != rebuilt.proposal_id:
        raise BookContractError("calibration proposal identity digest mismatch")


def proposal_from_record(record: Mapping[str, Any], manifest: BookManifest) -> CalibrationProposal:
    if not isinstance(record, Mapping) or set(record) != _PROPOSAL_FIELDS:
        raise BookContractError("calibration proposal has an invalid shape")
    if record["schema"] != CALIBRATION_PROPOSAL_SCHEMA:
        raise BookContractError(f"calibration proposal schema must be {CALIBRATION_PROPOSAL_SCHEMA}")
    proposal = create_calibration_proposal(manifest, record["producer"], record["pages"])
    if record["book_id"] != proposal.book_id:
        raise BookContractError("proposal.book_id does not match BookManifest v2")
    if record["physical_manifest_sha256"] != proposal.physical_manifest_sha256:
        raise BookContractError("proposal.physical_manifest_sha256 does not match BookManifest v2")
    if record["proposal_id"] != proposal.proposal_id:
        raise BookContractError("calibration proposal identity digest mismatch")
    return proposal


def load_calibration_proposal(path: Path, manifest: BookManifest) -> CalibrationProposal:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BookContractError(f"{path}: cannot read calibration proposal: {exc}") from exc
    if not isinstance(raw, dict):
        raise BookContractError(f"{path}: calibration proposal root must be an object")
    return proposal_from_record(raw, manifest)


def save_calibration_proposal(proposal: CalibrationProposal, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(proposal.record(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def _acceptance_note(proposal: CalibrationProposal, fields: Sequence[str]) -> str:
    return (f"Human accepted {', '.join(fields)} from proposal {proposal.proposal_id}; "
            f"producer={proposal.producer['source']}; method={proposal.producer['method']}; "
            f"evidence_sha256={proposal.producer['evidence_sha256']}; "
            f"producer_note={proposal.producer['note']}.")


def accept_calibration_proposal(
    proposal: CalibrationProposal,
    manifest: BookManifest,
    profile: BookProfile,
    *,
    accepted_pages: Mapping[str, Sequence[str]],
) -> tuple[BookProfile, dict[str, Any]]:
    """Apply explicit page/field selections to a mutable v2 profile draft."""
    validate_calibration_proposal(proposal, manifest)
    validate_profile_for_manifest(profile, manifest)
    if profile.schema != "book-profile-v2":
        raise BookContractError("proposal acceptance requires book-profile-v2")
    if profile.state != "draft":
        raise BookContractError("proposal acceptance requires a draft profile")
    if not accepted_pages:
        raise BookContractError("explicitly select at least one page and field for acceptance")
    proposal_by_page = {page["page_id"]: page["values"] for page in proposal.pages}
    profile_by_page = {page.page_id: page for page in profile.pages}
    proposal_order = {page.page_id: index for index, page in enumerate(manifest.pages)}
    selected_ids = list(accepted_pages)
    if len(set(selected_ids)) != len(selected_ids):
        raise BookContractError("accepted page IDs contain duplicates")
    unknown_pages = sorted(set(selected_ids) - set(proposal_order))
    if unknown_pages:
        raise BookContractError(f"accepted page IDs are not in the physical manifest: {unknown_pages}")
    selected_ids.sort(key=proposal_order.__getitem__)

    updated_pages = dict(profile_by_page)
    accepted_records: list[dict[str, Any]] = []
    for page_id in selected_ids:
        requested_fields = accepted_pages[page_id]
        if page_id not in proposal_by_page:
            raise BookContractError(f"page {page_id!r} has no proposal entry")
        if page_id not in profile_by_page:
            raise BookContractError(f"page {page_id!r} has no profile row")
        if not requested_fields:
            raise BookContractError(f"page {page_id}: select at least one field")
        if not isinstance(requested_fields, Sequence) or isinstance(requested_fields, (str, bytes)):
            raise BookContractError(f"page {page_id}: accepted fields must be a list")
        if len(set(requested_fields)) != len(requested_fields):
            raise BookContractError(f"page {page_id}: accepted fields contain duplicates")
        unknown_fields = sorted(set(requested_fields) - set(PROPOSED_FIELDS))
        if unknown_fields:
            raise BookContractError(f"page {page_id}: unsupported fields {unknown_fields}")
        requested_fields = tuple(field for field in PROPOSED_FIELDS if field in requested_fields)
        values = proposal_by_page[page_id]
        absent = sorted(set(requested_fields) - set(values))
        if absent:
            raise BookContractError(f"page {page_id}: proposal has no values for requested fields {absent}")

        current = profile_by_page[page_id]
        updates: dict[str, Any] = {}
        for field in requested_fields:
            value = values[field]
            if field == "content_bounds":
                updates.update(content_bounds=tuple(value), content_status="measured")
            elif field == "orientation_degrees":
                updates.update(orientation_degrees=value,
                               orientation_status="no_transform" if value == 0 else "measured")
            elif field == "deskew_degrees":
                updates.update(deskew_degrees=float(value),
                               deskew_status="no_transform" if value == 0 else "measured")

        note_line = _acceptance_note(proposal, requested_fields)
        note_parts = current.note.splitlines()
        if note_line not in note_parts:
            note_parts.append(note_line)
        updated_pages[page_id] = replace(current, **updates, source="human",
                                         note="\n".join(note_parts))
        accepted_records.append({"page_id": page_id,
                                 "fields": list(requested_fields)})

    manifest_page_order = [page.page_id for page in manifest.pages]
    calibration_pages = list(dict.fromkeys([
        *profile.calibration_pages,
        *(page_id for page_id in manifest_page_order if page_id in accepted_pages),
    ]))
    updated_profile = replace(
        profile,
        pages=tuple(updated_pages[page_id] for page_id in manifest_page_order),
        calibration_pages=tuple(calibration_pages),
    )
    validate_profile_for_manifest(updated_profile, manifest)

    acceptance = {
        "schema": CALIBRATION_ACCEPTANCE_SCHEMA,
        "book_id": manifest.book_id,
        "physical_manifest_sha256": manifest.physical_sha256,
        "input_profile_sha256": profile.sha256,
        "output_profile_sha256": updated_profile.sha256,
        "proposal_id": proposal.proposal_id,
        "accepted_pages": accepted_records,
        "accepted_at": datetime.now(UTC).isoformat(),
        "acceptance_provenance": {"action": "explicit human acceptance through normalize calibrate accept"},
    }
    return updated_profile, acceptance


def save_acceptance_record(record: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(record), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")
