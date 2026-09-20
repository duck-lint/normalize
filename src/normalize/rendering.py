"""Deterministic, derived-only page preprocessing for the Slice 1 boundary."""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import pymupdf
from PIL import Image

from .fixtures import FixtureMetadata

CONFIG_SCHEMA = "preprocessing-config-v1"
METADATA_SCHEMA = "preprocessing-metadata-v1"
SUCCESS = "success"
UNCERTAIN = "uncertain"
FAILURE = "failure"
UNCERTAINTY_CODES = {
    "rotation_unresolved",
    "result_kind_unresolved",
    "split_unresolved",
    "order_unresolved",
    "crop_unresolved",
    "deskew_unresolved",
}
ERROR_CODES = {
    "missing_fixture",
    "source_open",
    "source_page",
    "invalid_config",
    "source_alias",
    "output_error",
}
_KNOWN_FIXTURE_IDS = {
    "relativity_pdf10_pp26-27",
    "relativity_pdf17_pp40-41",
    "relativity_pdf23_pp52-53",
    "stella_maris_pdf03_session-I",
    "stella_maris_pdf06_dense-dialogue",
    "stella_maris_pdf18_session-II_p35",
}
_TRANSFORM_NAMES = ("rotation", "crop", "deskew", "split", "order")
_ROOT_KEYS = {
    "schema",
    "status",
    "fixture_id",
    "source_pdf",
    "source_pdf_sha256",
    "fixture_pdf_page_index_1_based",
    "source_pdf_page_index_1_based",
    "dpi",
    "source_pdf_dimensions_pt",
    "source_raster",
    "result",
    "transforms",
    "pages",
    "spread_output",
    "output_files",
    "uncertainty",
    "error",
}


class FixtureUnavailableError(RuntimeError):
    """Raised for an exact fixture that cannot be opened or selected."""


class PreprocessingConfigError(ValueError):
    """Raised when the operational preprocessing contract is malformed."""


@dataclass(frozen=True)
class PreprocessingProfile:
    result_kind: str
    rotation_degrees: int
    crop: tuple[int, int, int, int] | None
    deskew_degrees: float
    split_boundary: int | None
    output_order: tuple[str, ...]
    blank_sides: tuple[str, ...]
    uncertainty: dict[str, str] | None


@dataclass(frozen=True)
class PreprocessingConfig:
    path: Path
    dpi: int
    profiles: Mapping[str, PreprocessingProfile]

    def profile_for(self, fixture_id: str) -> PreprocessingProfile:
        try:
            return self.profiles[fixture_id]
        except KeyError as exc:
            raise PreprocessingConfigError(
                f"{self.path}: no preprocessing profile for {fixture_id!r}"
            ) from exc


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _parse_crop(value: Any, path: Path, fixture_id: str) -> tuple[int, int, int, int] | None:
    if value is None:
        return None
    if (
        not isinstance(value, list)
        or len(value) != 4
        or any(isinstance(item, bool) or not isinstance(item, int) for item in value)
    ):
        raise PreprocessingConfigError(f"{path}: {fixture_id}.crop must be null or [x0,y0,x1,y1]")
    x0, y0, x1, y1 = value
    if x0 < 0 or y0 < 0 or x1 <= x0 or y1 <= y0:
        raise PreprocessingConfigError(f"{path}: {fixture_id}.crop must be a non-empty rectangle")
    return (x0, y0, x1, y1)


def _parse_uncertainty(value: Any, path: Path, fixture_id: str) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"code", "field", "reason"}:
        raise PreprocessingConfigError(
            f"{path}: {fixture_id}.uncertainty must contain code, field, and reason"
        )
    code = value["code"]
    if not isinstance(code, str) or not code:
        raise PreprocessingConfigError(f"{path}: uncertainty code must be a non-empty string")
    if code not in UNCERTAINTY_CODES:
        raise PreprocessingConfigError(f"{path}: unknown uncertainty code {value['code']!r}")
    if not all(isinstance(value[key], str) and value[key] for key in ("field", "reason")):
        raise PreprocessingConfigError(f"{path}: uncertainty field and reason must be non-empty")
    expected_field = code.removesuffix("_unresolved")
    if value["field"] != expected_field:
        raise PreprocessingConfigError(
            f"{path}: uncertainty code {code!r} must name field {expected_field!r}"
        )
    return {key: value[key] for key in ("code", "field", "reason")}


def _parse_profile(value: Any, path: Path, fixture_id: str) -> PreprocessingProfile:
    required = {
        "result_kind",
        "rotation_degrees",
        "crop",
        "deskew_degrees",
        "split_boundary",
        "output_order",
        "blank_sides",
        "uncertainty",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise PreprocessingConfigError(
            f"{path}: profile {fixture_id} must contain exactly {sorted(required)}"
        )
    result_kind = value["result_kind"]
    if not isinstance(result_kind, str) or result_kind not in {"page", "spread"}:
        raise PreprocessingConfigError(f"{path}: {fixture_id}.result_kind must be page or spread")
    rotation = value["rotation_degrees"]
    if isinstance(rotation, bool) or not isinstance(rotation, int) or rotation not in {0, 90, 180, 270}:
        raise PreprocessingConfigError(f"{path}: {fixture_id}.rotation_degrees is unsupported")
    deskew = value["deskew_degrees"]
    # Compare integers before converting to float: JSON permits arbitrary-size
    # integers, while float() raises OverflowError for values beyond its range.
    # Keeping that conversion out of the integer path preserves this validator's
    # existing PreprocessingConfigError contract for every numeric input.
    if isinstance(deskew, int) and not isinstance(deskew, bool):
        deskew_is_valid = abs(deskew) <= 45
    else:
        deskew_is_valid = _is_number(deskew) and math.isfinite(float(deskew)) and abs(float(deskew)) <= 45
    if not deskew_is_valid:
        raise PreprocessingConfigError(f"{path}: {fixture_id}.deskew_degrees must be finite and <= 45")
    split = value["split_boundary"]
    if split is not None and (isinstance(split, bool) or not isinstance(split, int) or split <= 0):
        raise PreprocessingConfigError(
            f"{path}: {fixture_id}.split_boundary must be null or a positive integer"
        )
    order = value["output_order"]
    expected_order = ["page"] if result_kind == "page" else ["left", "right"]
    if order != expected_order:
        raise PreprocessingConfigError(
            f"{path}: {fixture_id}.output_order must be {expected_order!r} for {result_kind}"
        )
    if result_kind == "page" and split is not None:
        raise PreprocessingConfigError(f"{path}: page profile {fixture_id} cannot split")
    if result_kind == "spread" and split is None:
        raise PreprocessingConfigError(f"{path}: spread profile {fixture_id} requires split_boundary")
    blank_sides = value["blank_sides"]
    if not isinstance(blank_sides, list) or any(
        not isinstance(side, str) or side not in {"left", "right"} for side in blank_sides
    ):
        raise PreprocessingConfigError(f"{path}: {fixture_id}.blank_sides must contain left/right values")
    if len(blank_sides) != len(set(blank_sides)):
        raise PreprocessingConfigError(f"{path}: {fixture_id}.blank_sides must not repeat a side")
    if result_kind == "page" and blank_sides:
        raise PreprocessingConfigError(f"{path}: page profile {fixture_id} cannot declare blank sides")
    return PreprocessingProfile(
        result_kind=result_kind,
        rotation_degrees=rotation,
        crop=_parse_crop(value["crop"], path, fixture_id),
        deskew_degrees=float(deskew),
        split_boundary=split,
        output_order=tuple(order),
        blank_sides=tuple(blank_sides),
        uncertainty=_parse_uncertainty(value["uncertainty"], path, fixture_id),
    )


def load_preprocessing_config(path: Path) -> PreprocessingConfig:
    """Load the tracked operational config; expected JSON is never consulted."""

    path = path.resolve()
    try:
        with path.open(encoding="utf-8") as handle:
            record = json.load(handle)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise PreprocessingConfigError(f"{path}: cannot load preprocessing config: {exc}") from exc
    if not isinstance(record, dict) or set(record) != {"schema", "dpi", "profiles"}:
        raise PreprocessingConfigError(f"{path}: root must contain exactly schema, dpi, and profiles")
    if record["schema"] != CONFIG_SCHEMA:
        raise PreprocessingConfigError(f"{path}: schema must be {CONFIG_SCHEMA}")
    dpi = record["dpi"]
    if isinstance(dpi, bool) or not isinstance(dpi, int) or dpi <= 0:
        raise PreprocessingConfigError(f"{path}: dpi must be a positive integer")
    profiles = record["profiles"]
    if not isinstance(profiles, dict) or not profiles:
        raise PreprocessingConfigError(f"{path}: profiles must be a non-empty object")
    if set(profiles) != _KNOWN_FIXTURE_IDS:
        raise PreprocessingConfigError(
            f"{path}: profiles must name exactly the six selected fixture IDs"
        )
    return PreprocessingConfig(
        path=path,
        dpi=dpi,
        profiles={fixture_id: _parse_profile(profile, path, fixture_id) for fixture_id, profile in profiles.items()},
    )


def _ledger_entry(operation: str, parameters: Any, before: tuple[int, int], after: tuple[int, int]) -> dict[str, Any]:
    return {
        "operation": operation,
        "parameters": parameters,
        "input_dimensions_px": list(before),
        "output_dimensions_px": list(after),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _result_paths(fixture_id: str, kind: str) -> dict[str, str | None]:
    return {
        "spread": f"{fixture_id}.spread.png" if kind == "spread" else None,
        "page": f"{fixture_id}.page.png" if kind == "page" else None,
        "left": f"{fixture_id}.left.png" if kind == "spread" else None,
        "right": f"{fixture_id}.right.png" if kind == "spread" else None,
    }


def _base_metadata(metadata: FixtureMetadata, dpi: int, status: str) -> dict[str, Any]:
    return {
        "schema": METADATA_SCHEMA,
        "status": status,
        "fixture_id": metadata.fixture_id,
        "source_pdf": str(metadata.source_pdf),
        "source_pdf_sha256": None,
        "fixture_pdf_page_index_1_based": metadata.fixture_pdf_page_index_1_based,
        "source_pdf_page_index_1_based": metadata.source_pdf_page_index_1_based,
        "dpi": dpi,
        "source_pdf_dimensions_pt": None,
        "source_raster": None,
        "result": None,
        "transforms": {name: None for name in _TRANSFORM_NAMES},
        "pages": [],
        "spread_output": None,
        "output_files": {"spread": None, "page": None, "left": None, "right": None},
        "uncertainty": None,
        "error": None,
    }


def _reject_source_alias(path: Path, source_pdf: Path) -> None:
    if os.path.lexists(path) and os.path.samefile(path, source_pdf):
        raise FixtureUnavailableError("refusing to overwrite the source PDF with derived output")


@dataclass(frozen=True)
class _ArtifactInventory:
    """The bounded set of paths this fixture is allowed to publish or clean."""

    output_dir: Path
    metadata_path: Path
    image_paths: tuple[Path, ...]
    protected_paths: frozenset[Path]
    invalid_paths: tuple[Path, ...]

    @property
    def all_paths(self) -> tuple[Path, ...]:
        return (self.metadata_path, *self.image_paths)


def _result_image_names(fixture_id: str) -> tuple[str, ...]:
    """Return every output variant that a prior profile may have published."""

    return tuple(f"{fixture_id}.{kind}.png" for kind in ("spread", "page", "left", "right"))


def _path_is_source_alias(path: Path, source_pdf: Path) -> bool:
    if not os.path.lexists(path):
        return False
    try:
        return os.path.samefile(path, source_pdf)
    except OSError:
        return False


def _build_artifact_inventory(
    metadata: FixtureMetadata, output_dir: Path
) -> tuple[_ArtifactInventory | None, str | None]:
    """Create the exact artifact boundary before any rendering or cleanup."""

    output_dir = output_dir.resolve()
    try:
        if os.path.lexists(output_dir) and not output_dir.is_dir():
            return None, f"output path is not a directory: {output_dir}"
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return None, f"cannot prepare output directory {output_dir}: {exc}"

    metadata_path = output_dir / f"{metadata.fixture_id}.preprocess.json"
    image_paths = tuple(output_dir / name for name in _result_image_names(metadata.fixture_id))
    protected: set[Path] = set()
    invalid: list[Path] = []
    for path in (metadata_path, *image_paths):
        if _path_is_source_alias(path, metadata.source_pdf):
            protected.add(path)
        elif os.path.lexists(path) and (path.is_symlink() or not path.is_file()):
            # Exact directories and non-regular targets are preserved. In particular,
            # never recursively remove a user-owned directory named ``*.png``.
            invalid.append(path)
    return (
        _ArtifactInventory(
            output_dir=output_dir,
            metadata_path=metadata_path,
            image_paths=image_paths,
            protected_paths=frozenset(protected),
            invalid_paths=tuple(invalid),
        ),
        None,
    )


def _path_is_absent(path: Path) -> bool:
    return not os.path.lexists(path)


def _cleanup_inventory(inventory: _ArtifactInventory, source_pdf: Path) -> bool:
    """Remove only regular, non-aliased paths and verify the exact result."""

    if inventory.invalid_paths:
        return False
    try:
        for path in inventory.all_paths:
            if path in inventory.protected_paths or _path_is_absent(path):
                continue
            if path.is_symlink() or not path.is_file():
                return False
            _reject_source_alias(path, source_pdf)
            path.unlink()
    except (OSError, FixtureUnavailableError):
        return False
    return all(
        (
            _path_is_source_alias(path, source_pdf)
            if path in inventory.protected_paths
            else _path_is_absent(path)
        )
        for path in inventory.all_paths
    )


def _cleanup_staging(staging_dir: Path | None) -> bool:
    if staging_dir is None or not os.path.lexists(staging_dir):
        return True
    try:
        shutil.rmtree(staging_dir)
    except OSError:
        return False
    return not os.path.lexists(staging_dir)


def _write_staged_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _publish_diagnostic(
    inventory: _ArtifactInventory,
    metadata: Mapping[str, Any],
    source_pdf: Path,
) -> bool:
    """Publish a diagnostic only after staging teardown is verified.

    The diagnostic payload is assembled in a private directory first. That
    directory must be gone before the final metadata path is installed, so a
    teardown failure cannot leave a seemingly publishable diagnostic behind.
    """

    if inventory.metadata_path in inventory.protected_paths:
        return False
    staging_dir: Path | None = None
    temporary_publish_path: Path | None = None
    temporary_path: Path | None = None
    try:
        staging_dir = Path(tempfile.mkdtemp(prefix=".diagnostic-", dir=inventory.output_dir))
        temporary_path = staging_dir / inventory.metadata_path.name
        _write_staged_json(temporary_path, metadata)
        payload = temporary_path.read_bytes()
        if not _cleanup_staging(staging_dir):
            return False
        staging_dir = None

        if not _path_is_absent(inventory.metadata_path):
            return False
        _reject_source_alias(inventory.metadata_path, source_pdf)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".diagnostic-publish-", dir=inventory.output_dir
        )
        temporary_publish_path = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_publish_path, inventory.metadata_path)
        temporary_publish_path = None
        return inventory.metadata_path.is_file()
    except (OSError, FixtureUnavailableError, TypeError, ValueError):
        return False
    finally:
        if temporary_publish_path is not None:
            try:
                temporary_publish_path.unlink(missing_ok=True)
            except OSError:
                pass
        if staging_dir is not None:
            _cleanup_staging(staging_dir)


def _output_error(
    metadata: FixtureMetadata,
    dpi: int,
    inventory: _ArtifactInventory | None,
    reason: str,
) -> dict[str, Any]:
    return _diagnostic(
        metadata,
        dpi,
        FAILURE,
        error={"code": "output_error", "reason": reason},
    )


def _finish_non_success(
    metadata: FixtureMetadata,
    dpi: int,
    inventory: _ArtifactInventory | None,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Return a diagnostic only when its artifact state is verified."""

    if inventory is None:
        return _output_error(metadata, dpi, inventory, str(result.get("error")))
    if not _cleanup_inventory(inventory, metadata.source_pdf):
        return _output_error(
            metadata,
            dpi,
            inventory,
            "derived artifact cleanup or inspection could not be verified",
        )
    if _publish_diagnostic(inventory, result, metadata.source_pdf):
        return result
    # Cleanup has already removed any prior metadata. If diagnostic publication
    # fails, return output_error without claiming that a diagnostic is on disk.
    return _output_error(
        metadata,
        dpi,
        inventory,
        "diagnostic metadata publication failed; artifact state is unverified",
    )


def _diagnostic(
    metadata: FixtureMetadata,
    dpi: int,
    status: str,
    *,
    uncertainty: dict[str, str] | None = None,
    error: dict[str, str] | None = None,
) -> dict[str, Any]:
    result = _base_metadata(metadata, dpi, status)
    result["uncertainty"] = uncertainty
    result["error"] = error
    return result


def _apply_rotation(image: Image.Image, degrees: int) -> Image.Image:
    if degrees == 0:
        return image
    methods = {90: Image.Transpose.ROTATE_270, 180: Image.Transpose.ROTATE_180, 270: Image.Transpose.ROTATE_90}
    return image.transpose(methods[degrees])


def _preprocess_image(image: Image.Image, profile: PreprocessingProfile) -> tuple[Image.Image, dict[str, Any]]:
    before = (image.width, image.height)
    rotated = _apply_rotation(image, profile.rotation_degrees)
    transforms = {
        "rotation": _ledger_entry(
            "none" if profile.rotation_degrees == 0 else "rotate",
            {"degrees_clockwise": profile.rotation_degrees} if profile.rotation_degrees else None,
            before,
            (rotated.width, rotated.height),
        )
    }
    crop_before = (rotated.width, rotated.height)
    if profile.crop is None:
        cropped, crop_parameters, crop_operation = rotated, None, "none"
    else:
        if profile.crop[2] > rotated.width or profile.crop[3] > rotated.height:
            raise PreprocessingConfigError("crop rectangle is outside the oriented raster")
        cropped = rotated.crop(profile.crop)
        crop_parameters, crop_operation = {"rect_px": list(profile.crop)}, "crop"
    transforms["crop"] = _ledger_entry(crop_operation, crop_parameters, crop_before, (cropped.width, cropped.height))
    deskew_before = (cropped.width, cropped.height)
    if profile.deskew_degrees == 0:
        deskewed, deskew_parameters, deskew_operation = cropped, None, "none"
    else:
        # Pillow's positive angle is counter-clockwise; this contract defines
        # positive deskew as clockwise correction, so pass the negative angle.
        deskewed = cropped.rotate(
            -profile.deskew_degrees,
            resample=Image.Resampling.BICUBIC,
            expand=True,
            fillcolor=(255, 255, 255),
        )
        deskew_parameters, deskew_operation = {
            "degrees_clockwise": profile.deskew_degrees,
            "resampling": "bicubic",
            "expand": True,
            "fill_rgb": [255, 255, 255],
        }, "deskew"
    transforms["deskew"] = _ledger_entry(deskew_operation, deskew_parameters, deskew_before, (deskewed.width, deskewed.height))
    return deskewed, transforms


def preprocess_fixture(metadata: FixtureMetadata, config_path: Path, output_dir: Path) -> dict[str, Any]:
    """Preprocess one fixture through the single config-path lifecycle.

    Inventory creation deliberately precedes config parsing. A malformed or
    missing config therefore cannot bypass cleanup of exact stale artifacts.
    """

    inventory, inventory_error = _build_artifact_inventory(metadata, output_dir)
    if inventory_error is not None:
        return _output_error(metadata, 0, inventory, inventory_error)
    assert inventory is not None

    try:
        config = load_preprocessing_config(config_path)
    except PreprocessingConfigError as exc:
        result = _diagnostic(
            metadata,
            0,
            FAILURE,
            error={"code": "invalid_config", "reason": str(exc)},
        )
        return _finish_non_success(metadata, 0, inventory, result)

    try:
        profile = config.profile_for(metadata.fixture_id)
    except PreprocessingConfigError as exc:
        result = _diagnostic(
            metadata,
            config.dpi,
            FAILURE,
            error={"code": "invalid_config", "reason": str(exc)},
        )
        return _finish_non_success(metadata, config.dpi, inventory, result)
    if inventory.invalid_paths:
        return _finish_non_success(
            metadata,
            config.dpi,
            inventory,
            _output_error(
                metadata,
                config.dpi,
                inventory,
                "invalid non-regular derived destination: "
                + ", ".join(str(path) for path in inventory.invalid_paths),
            ),
        )

    if inventory.protected_paths:
        result = _diagnostic(
            metadata,
            config.dpi,
            FAILURE,
            error={
                "code": "source_alias",
                "reason": "refusing to overwrite the source PDF with derived output",
            },
        )
        # A metadata path aliased to the source cannot carry a diagnostic. It is
        # preserved and the result is therefore an output_error with unverified
        # metadata publication rather than a false source-alias diagnostic.
        if inventory.metadata_path in inventory.protected_paths:
            return _finish_non_success(
                metadata,
                config.dpi,
                inventory,
                _output_error(
                    metadata,
                    config.dpi,
                    inventory,
                    "the preprocess metadata path aliases the source PDF",
                ),
            )
        return _finish_non_success(metadata, config.dpi, inventory, result)

    if not metadata.source_pdf.is_file():
        result = _diagnostic(
            metadata,
            config.dpi,
            FAILURE,
            error={
                "code": "missing_fixture",
                "reason": (
                    f"Fixture PDF unavailable for {metadata.fixture_id}: expected the exact local file "
                    f"{metadata.source_pdf}. No alternate PDF will be selected."
                ),
            },
        )
        return _finish_non_success(metadata, config.dpi, inventory, result)
    if profile.uncertainty is not None:
        result = _diagnostic(metadata, config.dpi, UNCERTAIN, uncertainty=profile.uncertainty)
        return _finish_non_success(metadata, config.dpi, inventory, result)
    try:
        source_hash = _sha256(metadata.source_pdf)
        document = pymupdf.open(str(metadata.source_pdf))
    except Exception as exc:
        result = _diagnostic(metadata, config.dpi, FAILURE, error={"code": "source_open", "reason": str(exc)})
        return _finish_non_success(metadata, config.dpi, inventory, result)
    try:
        page_index = metadata.fixture_pdf_page_index_1_based - 1
        if page_index < 0 or page_index >= document.page_count:
            result = _diagnostic(
                metadata,
                config.dpi,
                FAILURE,
                error={"code": "source_page", "reason": f"local page index is outside PDF ({document.page_count} pages)"},
            )
            return _finish_non_success(metadata, config.dpi, inventory, result)
        page = document.load_page(page_index)
        source_dimensions = [float(page.rect.width), float(page.rect.height)]
        declared_rotation = int(page.rotation)
        scale = config.dpi / 72.0
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False, annots=False)
        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    except Exception as exc:
        result = _diagnostic(metadata, config.dpi, FAILURE, error={"code": "source_page", "reason": str(exc)})
        return _finish_non_success(metadata, config.dpi, inventory, result)
    finally:
        document.close()
    staging_dir: Path | None = None
    try:
        transformed, transforms = _preprocess_image(image, profile)
        split_before = (transformed.width, transformed.height)
        if profile.result_kind == "spread":
            assert profile.split_boundary is not None
            if profile.split_boundary >= transformed.width:
                raise PreprocessingConfigError("split boundary is outside the post-deskew raster")
            left = transformed.crop((0, 0, profile.split_boundary, transformed.height))
            right = transformed.crop((profile.split_boundary, 0, transformed.width, transformed.height))
            side_images = {"left": left, "right": right}
            split_parameters = {
                "split_x": profile.split_boundary,
                "left_source_rect_px": [0, 0, profile.split_boundary, transformed.height],
                "right_source_rect_px": [profile.split_boundary, 0, transformed.width, transformed.height],
            }
            transforms["split"] = _ledger_entry("split", split_parameters, split_before, split_before)
            ordered_images = [(side, side_images[side]) for side in profile.output_order]
            composed = Image.new("RGB", (transformed.width, transformed.height), (255, 255, 255))
            composed.paste(left, (0, 0))
            composed.paste(right, (profile.split_boundary, 0))
        else:
            transforms["split"] = _ledger_entry("none", None, split_before, split_before)
            ordered_images = [("page", transformed)]
            composed = transformed
        transforms["order"] = _ledger_entry(
            "order", {"output_order": list(profile.output_order)}, split_before, (composed.width, composed.height)
        )
        output_files = _result_paths(metadata.fixture_id, profile.result_kind)
        pages = []
        for side, side_image in ordered_images:
            source_rect = (
                transforms["split"]["parameters"][f"{side}_source_rect_px"]
                if profile.result_kind == "spread"
                else [0, 0, transformed.width, transformed.height]
            )
            pages.append(
                {
                    "side": side,
                    "output_path": output_files[side],
                    "width_px": side_image.width,
                    "height_px": side_image.height,
                    "source_stage": "post_deskew",
                    "source_rect_px": source_rect,
                    "blank": side in profile.blank_sides,
                }
            )
        metadata_result = _base_metadata(metadata, config.dpi, SUCCESS)
        metadata_result.update(
            {
                "source_pdf_sha256": source_hash,
                "source_pdf_dimensions_pt": {"width": source_dimensions[0], "height": source_dimensions[1]},
                "source_raster": {
                    "width_px": image.width,
                    "height_px": image.height,
                    "declared_pdf_rotation_degrees": declared_rotation,
                },
                "result": {
                    "kind": profile.result_kind,
                    "output_order": list(profile.output_order),
                    "blank_sides": list(profile.blank_sides),
                },
                "transforms": transforms,
                "pages": pages,
                "spread_output": output_files["spread"],
                "output_files": output_files,
            }
        )

        active_image_paths = {
            inventory.output_dir / filename
            for filename in output_files.values()
            if filename is not None
        }
        # A successful rerun also removes obsolete variants from a prior
        # profile, but only after the exact inventory has been validated.
        obsolete_paths = [path for path in inventory.image_paths if path not in active_image_paths]
        for path in obsolete_paths:
            if not _path_is_absent(path):
                if path in inventory.protected_paths or path.is_symlink() or not path.is_file():
                    raise OSError(f"invalid obsolete derived destination: {path}")
                _reject_source_alias(path, metadata.source_pdf)
                path.unlink()

        staging_dir = Path(tempfile.mkdtemp(prefix=f".{metadata.fixture_id}-", dir=inventory.output_dir))
        for side, side_image in ordered_images:
            staged_path = staging_dir / str(output_files[side])
            side_image.save(staged_path, format="PNG")
        if output_files["spread"] is not None:
            composed.save(staging_dir / str(output_files["spread"]), format="PNG")
        if _sha256(metadata.source_pdf) != source_hash:
            raise OSError("source PDF changed during preprocessing")
        _write_staged_json(staging_dir / inventory.metadata_path.name, metadata_result)
        for side, _side_image in ordered_images:
            os.replace(
                staging_dir / str(output_files[side]),
                inventory.output_dir / str(output_files[side]),
            )
        if output_files["spread"] is not None:
            os.replace(
                staging_dir / str(output_files["spread"]),
                inventory.output_dir / str(output_files["spread"]),
            )
        _reject_source_alias(inventory.metadata_path, metadata.source_pdf)
        os.replace(staging_dir / inventory.metadata_path.name, inventory.metadata_path)
        if _sha256(metadata.source_pdf) != source_hash:
            raise OSError("source PDF changed during preprocessing")
        if not all(path.is_file() for path in active_image_paths) or not inventory.metadata_path.is_file():
            raise OSError("published derived artifact inspection failed")
        # Defer the successful result until the staging directory has been
        # verified as removed. A published artifact set is not a clean success
        # while its temporary state remains unverified.
        result = metadata_result
    except PreprocessingConfigError as exc:
        result = _diagnostic(metadata, config.dpi, FAILURE, error={"code": "invalid_config", "reason": str(exc)})
    except FixtureUnavailableError as exc:
        result = _diagnostic(metadata, config.dpi, FAILURE, error={"code": "source_alias", "reason": str(exc)})
    except (OSError, ValueError, TypeError) as exc:
        result = _diagnostic(metadata, config.dpi, FAILURE, error={"code": "output_error", "reason": str(exc)})
    finally:
        staging_removed = _cleanup_staging(staging_dir)
    if result["status"] == SUCCESS:
        if not staging_removed:
            return _finish_non_success(
                metadata,
                config.dpi,
                inventory,
                _output_error(metadata, config.dpi, inventory, "staging cleanup could not be verified"),
            )
        return result
    if result["error"]["code"] == "source_alias":
        # This branch is reached only if a source alias appears after preflight
        # (for example, through an induced publication race). Preserve it and
        # clean every other exact path before publishing the diagnostic.
        if not staging_removed:
            return _output_error(metadata, config.dpi, inventory, "staging cleanup could not be verified")
        return _finish_non_success(metadata, config.dpi, inventory, result)
    if not staging_removed:
        return _output_error(metadata, config.dpi, inventory, "staging cleanup could not be verified")
    return _finish_non_success(metadata, config.dpi, inventory, result)


def validate_metadata_contract(record: Mapping[str, Any]) -> None:
    """Fail fast in tests and callers when the exposed root shape drifts."""

    if set(record) != _ROOT_KEYS:
        raise ValueError(f"metadata root keys differ: {sorted(set(record) ^ _ROOT_KEYS)}")
