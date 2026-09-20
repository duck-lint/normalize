"""Repository-owned preprocessing runtime for the Normalize project."""

from .environment import EnvironmentReport, check_tesseract
from .fixtures import (
    FixtureCatalog,
    FixtureMetadata,
    MetadataError,
    load_fixture_metadata,
)
from .geometry import (
    GEOMETRY_ERROR_CODES,
    GEOMETRY_SCHEMA,
    GEOMETRY_UNCERTAINTY_CODES,
    group_physical_lines,
    parse_tsv_rows,
    run_geometry,
)
from .rendering import (
    FAILURE,
    SUCCESS,
    UNCERTAIN,
    CONFIG_SCHEMA,
    METADATA_SCHEMA,
    FixtureUnavailableError,
    PreprocessingConfig,
    PreprocessingConfigError,
    PreprocessingProfile,
    load_preprocessing_config,
    preprocess_fixture,
)

__all__ = [
    "EnvironmentReport",
    "FixtureCatalog",
    "FixtureMetadata",
    "FixtureUnavailableError",
    "PreprocessingConfig",
    "PreprocessingConfigError",
    "PreprocessingProfile",
    "CONFIG_SCHEMA",
    "METADATA_SCHEMA",
    "MetadataError",
    "GEOMETRY_ERROR_CODES",
    "GEOMETRY_SCHEMA",
    "GEOMETRY_UNCERTAINTY_CODES",
    "FAILURE",
    "SUCCESS",
    "UNCERTAIN",
    "check_tesseract",
    "load_fixture_metadata",
    "load_preprocessing_config",
    "preprocess_fixture",
    "group_physical_lines",
    "parse_tsv_rows",
    "run_geometry",
]
