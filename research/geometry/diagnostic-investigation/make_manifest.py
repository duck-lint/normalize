"""Create the manifest for the sparse-connectivity investigation."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = ROOT.parents[2]
PRIOR_ROOT = REPOSITORY_ROOT / "research" / "geometry" / "residual-forensics"
BASELINE_SHA = "6453d2890fce5799640d7219effdd090ea6aed2d"


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(("git", *args), cwd=REPOSITORY_ROOT, text=True).strip()


def rel(path: Path) -> str:
    return path.relative_to(REPOSITORY_ROOT).as_posix()


def versions() -> dict[str, str]:
    names = (
        "normalize",
        "PyMuPDF",
        "Pillow",
        "pytesseract",
        "rapidfuzz",
        "numpy",
        "opencv-python-headless",
        "pytest",
    )
    return {name: importlib.metadata.version(name) for name in names}


def artifacts(generated_at: str) -> list[dict[str, object]]:
    excluded = {"make_manifest.py", "manifest.json"}
    return [
        {
            "path": rel(path),
            "sha256": digest(path),
            "size_bytes": path.stat().st_size,
            "generated_at_utc": generated_at,
        }
        for path in sorted(ROOT.rglob("*"))
        if path.is_file() and path.name not in excluded
    ]


def prior_inputs() -> dict[str, object]:
    prior_manifest_path = PRIOR_ROOT / "manifest.json"
    prior_manifest = json.loads(prior_manifest_path.read_text(encoding="utf-8"))
    selected = {}
    for fixture in prior_manifest["fixtures"]:
        if fixture["fixture_id"] in {"relativity_pdf10_pp26-27", "relativity_pdf17_pp40-41"}:
            selected[fixture["fixture_id"]] = fixture["source_references"]
    return {
        "prior_residual_forensics_manifest": {
            "path": rel(prior_manifest_path),
            "sha256": digest(prior_manifest_path),
        },
        "selected_scan_references": selected,
        "prior_geometry_artifacts": {
            fixture_id: {
                "path": rel(PRIOR_ROOT / fixture_id / "geometry.json"),
                "sha256": digest(PRIOR_ROOT / fixture_id / "geometry.json"),
            }
            for fixture_id in ("relativity_pdf10_pp26-27", "relativity_pdf17_pp40-41")
        },
        "source_pdfs_copied": False,
    }


def main() -> None:
    generated_at = datetime.now(timezone.utc).isoformat()
    current_sha = git("rev-parse", "HEAD")
    if current_sha != BASELINE_SHA:
        raise SystemExit(f"expected baseline {BASELINE_SHA}, found {current_sha}")
    diagnostics_path = ROOT / "diagnostics.json"
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    manifest = {
        "schema": "normalize-diagnostic-investigation-v1",
        "generated_at_utc": generated_at,
        "experiment_start": {
            "git_commit_sha": BASELINE_SHA,
            "git_branch": "geometry-forensics-identity-oracle",
            "git_status": "clean",
            "isolated_task_branch": git("branch", "--show-current"),
            "production_geometry_sha256": digest(REPOSITORY_ROOT / "src" / "normalize" / "geometry.py"),
        },
        "environment": {
            "python": sys.version,
            "python_executable": sys.executable,
            "packages": versions(),
            "tesseract": subprocess.check_output(("tesseract", "--version"), text=True).splitlines()[0],
            "geometry_module_import_path": str(__import__("normalize.geometry", fromlist=["__file__"]).__file__),
            "oracle_path": rel(REPOSITORY_ROOT / "tests" / "geometry_oracle.py"),
        },
        "commands": [
            ".venv/bin/python -m pytest -q",
            ".venv/bin/python research/geometry/diagnostic-investigation/investigate.py",
            ".venv/bin/python research/geometry/diagnostic-investigation/make_manifest.py",
            "git diff --check",
        ],
        "provenance": prior_inputs(),
        "diagnostic_summary": {
            "horizontal_case_count": len(diagnostics["horizontal_connectivity"]),
            "vertical_fixture_trace_count": len(diagnostics["vertical_fragmentation"]["fixture_traces"]),
            "synthetic_vertical_case_count": len(diagnostics["vertical_fragmentation"]["synthetic_cases"]),
            "rel17_observed_example": diagnostics["vertical_fragmentation"]["observed_rel17_lightning_A"],
        },
        "artifact_paths_and_hashes": artifacts(generated_at),
        "restrictions": {
            "production_geometry_modified": False,
            "identity_complete_oracle_modified": False,
            "fixture_contracts_modified": False,
            "source_pdfs_committed": False,
            "dependencies_installed": False,
            "symphony_modified": False,
        },
    }
    (ROOT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"artifact_count": len(manifest["artifact_paths_and_hashes"]), "output": str(ROOT / "manifest.json")}, indent=2))


if __name__ == "__main__":
    main()
