"""Book-neutral engine adapter over the established page algorithms."""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytesseract
from PIL import Image
from pytesseract import Output

from .books import BookPage, PageCalibration, stable_digest
from .geometry import GeometryError, _PreprocessedPage, _engine_record, _page_geometry
from .markdown import emit_markdown
from .rendering import preprocess_page_pixels
from .reconstruction import NormalizedDocument, PageSpan, reconstruct_document


def _observe_image_geometry(image: Image.Image, page_id: str, *, book_id: str,
                            page_index: int, dpi: int, source_image: str,
                            source_sha256: str) -> dict[str, Any]:
    """Adapt in-memory book pixels to the established geometry serializer.

    Private geometry helpers are intentionally consumed here so geometry.py
    and its independently hashed algorithm contract stay unchanged.
    """
    if not page_id or not book_id or page_index < 0 or dpi <= 0:
        raise ValueError("page identity, non-negative order, and positive DPI are required")
    try:
        tsv = pytesseract.image_to_data(image, lang="eng", config="--psm 6", output_type=Output.STRING)
    except Exception as exc:
        raise GeometryError("tesseract_invocation", f"Tesseract failed on page {page_id}: {exc}") from exc
    page = _PreprocessedPage(page_id, Path("."), image.width, image.height, False,
                             {"output_path": "in-memory"})
    record = _page_geometry(
        page, tsv, _engine_record(),
        {"fixture_id": book_id, "fixture_pdf_page_index_1_based": page_index + 1,
         "source_pdf_page_index_1_based": page_index + 1, "dpi": dpi,
         "metadata_order": [page_id]},
    )
    record["page_id"] = page_id
    record["provenance"] = {
        "book_id": book_id, "page_id": page_id, "page_index": page_index,
        "source_image": source_image, "source_image_sha256": source_sha256,
        "dpi": dpi, "preprocessed_dimensions_px": [image.width, image.height],
    }
    return record


@dataclass(frozen=True)
class EngineConfig:
    """Global fixed semantics; book profiles cannot override these values."""

    contract: str = "normalize-engine-v1"
    target_dpi: int = 144
    ocr_language: str = "eng"
    ocr_config: str = "--psm 6"
    rotation_resampling: str = "pillow-bicubic"
    rotation_expand: bool = True
    rotation_fill_rgb: tuple[int, int, int] = (255, 255, 255)
    downsample_resampling: str = "lanczos"
    dimension_rounding: str = "half-up"

    def record(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "target_dpi": self.target_dpi,
            "ocr_language": self.ocr_language,
            "ocr_config": self.ocr_config,
            "rotation_resampling": self.rotation_resampling,
            "rotation_expand": self.rotation_expand,
            "rotation_fill_rgb": list(self.rotation_fill_rgb),
            "downsample_resampling": self.downsample_resampling,
            "dimension_rounding": self.dimension_rounding,
        }


class BookEngine:
    """Apply fixed engine behavior to page pixels and validated calibration."""

    def __init__(self, config: EngineConfig | None = None):
        self.config = config or EngineConfig()
        self._validate_config()

    def _validate_config(self) -> None:
        if self.config != EngineConfig():
            raise ValueError("BookEngine v1 uses fixed global configuration; profiles cannot retune it")

    @property
    def identity(self) -> dict[str, Any]:
        try:
            tesseract_version = str(pytesseract.get_tesseract_version()).strip()
        except Exception:
            # Version discovery failure is retained in identity while the
            # runner still isolates the actual OCR failure per page.
            tesseract_version = "unavailable"
        source_root = Path(__file__).parent
        source_digest = hashlib.sha256()
        for source_path in sorted(source_root.glob("*.py"), key=lambda path: path.name):
            source_digest.update(source_path.name.encode("utf-8"))
            source_digest.update(b"\0")
            source_digest.update(source_path.read_bytes())
            source_digest.update(b"\0")
        return {
            **self.config.record(),
            "tesseract_version": tesseract_version,
            "tesseract_executable": str(getattr(pytesseract.pytesseract, "tesseract_cmd", "tesseract")),
            "production_source_sha256": source_digest.hexdigest(),
            "identity_sha256": stable_digest({**self.config.record(), "tesseract_version": tesseract_version}),
        }

    def preprocess(self, image: Image.Image, calibration: PageCalibration, source_dpi: int) -> tuple[Image.Image, dict[str, Any]]:
        """Apply crop, rigid rotation, and fixed target-DPI sampling in order."""
        try:
            working, provenance = preprocess_page_pixels(
                image,
                content_bounds=calibration.content_bounds,
                orientation_degrees=calibration.orientation_degrees or 0,
                deskew_degrees=calibration.deskew_degrees,
                source_dpi=source_dpi,
                target_dpi=self.config.target_dpi,
            )
        except ValueError as exc:
            raise ValueError(f"page {calibration.page_id}: {exc}") from exc
        provenance.update({
            "content_status": calibration.content_status,
            "orientation_status": calibration.orientation_status,
            "deskew_status": calibration.deskew_status,
        })
        return working, provenance

    def process_page(self, page: BookPage, calibration: PageCalibration, *, book_id: str,
                     page_index: int, source_dpi: int, source_sha256: str) -> dict[str, Any]:
        if page.source_sha256 and page.source_sha256 != source_sha256:
            raise ValueError(f"page {page.page_id}: source hash differs from manifest")
        try:
            with Image.open(page.image) as image:
                prepared, transform_record = self.preprocess(image, calibration, source_dpi)
        except (OSError, ValueError) as exc:
            raise ValueError(f"page {page.page_id}: cannot decode/preprocess source image: {exc}") from exc
        geometry = _observe_image_geometry(
            prepared,
            page.page_id,
            book_id=book_id,
            page_index=page_index,
            dpi=self.config.target_dpi,
            source_image=str(page.image),
            source_sha256=source_sha256,
        )
        encoded = io.BytesIO()
        prepared.save(encoded, format="PNG", optimize=False)
        return {
            "page_id": page.page_id,
            "page_index": page_index,
            "source_image": str(page.image),
            "source_sha256": source_sha256,
            "transforms": transform_record,
            "processed_pixel_sha256": hashlib.sha256(encoded.getvalue()).hexdigest(),
            "geometry": geometry,
        }

    def reconstruct(self, canonical_source: str, source_id: str,
                    ordered_pages: list[PageSpan]) -> NormalizedDocument:
        """Align canonical spans and reconstruct structure through fixed stages."""
        return reconstruct_document(canonical_source, source_id, ordered_pages)

    def emit(self, document: NormalizedDocument) -> str:
        """Serialize a reconstructed document using the established Markdown rules."""
        return emit_markdown(document)


__all__ = ["BookEngine", "EngineConfig"]
