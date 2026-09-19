"""Loading and validation for the tracked fixture metadata contract."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping


class MetadataError(ValueError):
    """Raised when a fixture metadata record is malformed or incomplete."""


_REQUIRED_FIELDS = (
    "fixture_id",
    "source_pdf",
    "raw_fixture",
    "normalized_reference",
    "fixture_pdf_page_index_1_based",
    "source_pdf_page_index_1_based",
)


def _positive_index(record: Mapping[str, Any], field: str, path: Path) -> int:
    value = record.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise MetadataError(f"{path}: {field} must be a positive integer")
    return value


def _sibling_path(metadata_path: Path, record: Mapping[str, Any], field: str) -> Path:
    value = record.get(field)
    if not isinstance(value, str) or not value:
        raise MetadataError(f"{metadata_path}: {field} must be a non-empty filename")
    path = (metadata_path.parent / value).resolve()
    if path.parent != metadata_path.parent.resolve():
        raise MetadataError(f"{metadata_path}: {field} must name a sibling fixture file")
    return path


@dataclass(frozen=True)
class FixtureMetadata:
    """Validated metadata plus resolved paths for one fixture.

    ``fixture_pdf_page_index_1_based`` selects a page in the local one-page
    asset. ``source_pdf_page_index_1_based`` is retained provenance and is
    never used to open the local asset.
    """

    fixture_id: str
    metadata_path: Path
    source_pdf: Path
    raw_fixture: Path
    normalized_reference: Path
    fixture_pdf_page_index_1_based: int
    source_pdf_page_index_1_based: int
    record: Mapping[str, Any]

    @property
    def pdf_available(self) -> bool:
        return self.source_pdf.is_file()


def parse_fixture_metadata(metadata_path: Path) -> FixtureMetadata:
    """Parse one expected JSON record without requiring its local PDF."""

    metadata_path = metadata_path.resolve()
    try:
        with metadata_path.open(encoding="utf-8") as handle:
            record = json.load(handle)
    except FileNotFoundError as exc:
        raise MetadataError(f"fixture metadata not found: {metadata_path}") from exc
    except json.JSONDecodeError as exc:
        raise MetadataError(f"{metadata_path}: invalid JSON: {exc}") from exc

    if not isinstance(record, dict):
        raise MetadataError(f"{metadata_path}: metadata root must be an object")
    missing = [field for field in _REQUIRED_FIELDS if field not in record]
    if missing:
        raise MetadataError(f"{metadata_path}: missing required field(s): {', '.join(missing)}")

    fixture_id = record["fixture_id"]
    if not isinstance(fixture_id, str) or not fixture_id:
        raise MetadataError(f"{metadata_path}: fixture_id must be a non-empty string")

    source_pdf = _sibling_path(metadata_path, record, "source_pdf")
    raw_fixture = _sibling_path(metadata_path, record, "raw_fixture")
    normalized_reference = _sibling_path(metadata_path, record, "normalized_reference")
    for field, path in (
        ("raw_fixture", raw_fixture),
        ("normalized_reference", normalized_reference),
    ):
        if not path.is_file():
            raise MetadataError(f"{metadata_path}: referenced {field} does not exist: {path}")

    return FixtureMetadata(
        fixture_id=fixture_id,
        metadata_path=metadata_path,
        source_pdf=source_pdf,
        raw_fixture=raw_fixture,
        normalized_reference=normalized_reference,
        fixture_pdf_page_index_1_based=_positive_index(
            record, "fixture_pdf_page_index_1_based", metadata_path
        ),
        source_pdf_page_index_1_based=_positive_index(
            record, "source_pdf_page_index_1_based", metadata_path
        ),
        record=dict(record),
    )


def _repository_root(root: Path | None) -> Path:
    if root is not None:
        return root.resolve()
    for candidate in (Path.cwd(), *Path.cwd().parents):
        if (candidate / "fixtures").is_dir():
            return candidate
    raise MetadataError("could not find repository root containing a fixtures directory")


@dataclass(frozen=True)
class FixtureCatalog:
    """Deterministic collection of all expected fixture records."""

    root: Path
    items: tuple[FixtureMetadata, ...]

    @classmethod
    def load(cls, root: Path | None = None) -> "FixtureCatalog":
        repository_root = _repository_root(root)
        paths = sorted((repository_root / "fixtures").glob("*/*.expected.json"))
        if not paths:
            raise MetadataError(f"no fixture metadata found under {repository_root / 'fixtures'}")
        items = tuple(parse_fixture_metadata(path) for path in paths)
        ids = [item.fixture_id for item in items]
        if len(ids) != len(set(ids)):
            raise MetadataError("fixture_id values must be unique")
        return cls(repository_root, items)

    def __iter__(self) -> Iterator[FixtureMetadata]:
        return iter(self.items)

    def get(self, fixture_id: str) -> FixtureMetadata:
        for item in self.items:
            if item.fixture_id == fixture_id:
                return item
        known = ", ".join(item.fixture_id for item in self.items)
        raise MetadataError(f"unknown fixture_id {fixture_id!r}; known fixtures: {known}")


def load_fixture_metadata(root: Path | None = None) -> tuple[FixtureMetadata, ...]:
    """Load all fixture metadata records, independent of PDF availability."""

    return FixtureCatalog.load(root).items
