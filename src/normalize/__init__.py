"""Repository-owned preprocessing runtime for the Normalize project."""

from .environment import EnvironmentReport, check_tesseract
from .fixtures import (
    FixtureCatalog,
    FixtureMetadata,
    MetadataError,
    load_fixture_metadata,
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
    "FAILURE",
    "SUCCESS",
    "UNCERTAIN",
    "check_tesseract",
    "load_fixture_metadata",
    "load_preprocessing_config",
    "preprocess_fixture",
]
