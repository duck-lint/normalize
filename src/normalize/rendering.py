"""Exact local fixture page rendering with provenance preserved."""

from __future__ import annotations

from dataclasses import dataclass

import pymupdf
from PIL import Image

from .fixtures import FixtureMetadata


class FixtureUnavailableError(RuntimeError):
    """Raised when the exact local PDF required by a fixture is unavailable."""


@dataclass(frozen=True)
class RenderedPage:
    image: Image.Image
    fixture_id: str
    source_pdf: str
    fixture_pdf_page_index_1_based: int
    source_pdf_page_index_1_based: int


def render_fixture_page(metadata: FixtureMetadata, dpi: int = 144) -> RenderedPage:
    """Render the configured local page; never substitute another fixture PDF."""

    if not metadata.source_pdf.is_file():
        raise FixtureUnavailableError(
            f"Fixture PDF unavailable for {metadata.fixture_id}: expected the exact local file "
            f"{metadata.source_pdf}. No alternate PDF will be selected. "
            "Materialize the ignored fixture PDF before running geometry-dependent checks."
        )
    if dpi <= 0:
        raise ValueError("dpi must be positive")

    try:
        document = pymupdf.open(str(metadata.source_pdf))
    except Exception as exc:
        raise FixtureUnavailableError(
            f"Fixture PDF could not be opened for {metadata.fixture_id}: "
            f"{metadata.source_pdf} ({exc})"
        ) from exc

    try:
        page_index = metadata.fixture_pdf_page_index_1_based - 1
        if page_index < 0 or page_index >= document.page_count:
            raise FixtureUnavailableError(
                f"Fixture page {metadata.fixture_pdf_page_index_1_based} is outside the exact "
                f"PDF for {metadata.fixture_id}; PDF has {document.page_count} page(s)."
            )
        page = document.load_page(page_index)
        scale = dpi / 72.0
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    finally:
        document.close()

    return RenderedPage(
        image=image,
        fixture_id=metadata.fixture_id,
        source_pdf=str(metadata.source_pdf),
        fixture_pdf_page_index_1_based=metadata.fixture_pdf_page_index_1_based,
        source_pdf_page_index_1_based=metadata.source_pdf_page_index_1_based,
    )
