"""External runtime checks used by Slice 0."""

from __future__ import annotations

from dataclasses import dataclass

import pytesseract


@dataclass(frozen=True)
class EnvironmentReport:
    tesseract_available: bool
    version: str | None
    message: str


def check_tesseract() -> EnvironmentReport:
    """Check only that the configured Tesseract executable is invokable."""

    try:
        version = str(pytesseract.get_tesseract_version()).strip()
    except Exception as exc:  # pytesseract exposes several platform-specific errors.
        return EnvironmentReport(
            tesseract_available=False,
            version=None,
            message=(
                "Tesseract is unavailable. Install the Tesseract executable or set "
                f"pytesseract.pytesseract.tesseract_cmd. Detail: {exc}"
            ),
        )
    return EnvironmentReport(
        tesseract_available=True,
        version=version,
        message=f"Tesseract available ({version})",
    )
