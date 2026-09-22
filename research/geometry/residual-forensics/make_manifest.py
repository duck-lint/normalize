"""Write the versioned manifest for the residual-geometry evidence set."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from normalize.fixtures import FixtureCatalog


ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = ROOT.parents[2]
CONFIG = REPOSITORY_ROOT / "fixtures" / "preprocessing.json"
FIXTURE_IDS = (
    "relativity_pdf10_pp26-27",
    "relativity_pdf17_pp40-41",
    "relativity_pdf23_pp52-53",
    "stella_maris_pdf03_session-I",
    "stella_maris_pdf06_dense-dialogue",
    "stella_maris_pdf18_session-II_p35",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(("git", *args), cwd=REPOSITORY_ROOT, text=True).strip()


def relative(path: Path) -> str:
    return path.relative_to(REPOSITORY_ROOT).as_posix()


def package_versions() -> dict[str, str]:
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


def output_inventory(generated_at: str) -> list[dict[str, object]]:
    paths = sorted(
        path
        for path in ROOT.rglob("*")
        if path.is_file()
        and path.name not in {"manifest.json", "forensic-report.md"}
        and path.name not in {"make_manifest.py", "make_diagnostic_crops.py", "evaluate_invariance.py"}
    )
    return [
        {
            "path": relative(path),
            "sha256": sha256(path),
            "size_bytes": path.stat().st_size,
            "generated_at_utc": generated_at,
        }
        for path in paths
    ]


def fixture_records(catalog: FixtureCatalog) -> list[dict[str, object]]:
    records = []
    for fixture_id in FIXTURE_IDS:
        fixture = catalog.get(fixture_id)
        geometry_path = ROOT / fixture_id / "geometry.json"
        geometry = json.loads(geometry_path.read_text(encoding="utf-8"))
        uncertainty_counts: dict[str, int] = {}
        residual_tokens = []
        for page in geometry["pages"]:
            for token in page["tokens"]:
                if token["physical_line_id"] is None:
                    code = "ambiguous_line_assignment" if token["candidate_line_ids"] else "unassigned_line_assignment"
                    uncertainty_counts[code] = uncertainty_counts.get(code, 0) + 1
                    residual_tokens.append(
                        {
                            "identity": [fixture_id, page["side"], token["source_row"]],
                            "side": page["side"],
                            "source_row": token["source_row"],
                            "text": token["text"],
                            "state": code,
                            "candidate_line_ids": token["candidate_line_ids"],
                        }
                    )
        records.append(
            {
                "fixture_id": fixture_id,
                "status": geometry["status"],
                "uncertainty_counts": uncertainty_counts,
                "residual_token_count": len(residual_tokens),
                "residual_tokens": residual_tokens,
                "source_references": {
                    "source_pdf": relative(fixture.source_pdf),
                    "source_pdf_sha256": sha256(fixture.source_pdf),
                    "raw_fixture": relative(fixture.raw_fixture),
                    "raw_fixture_sha256": sha256(fixture.raw_fixture),
                    "normalized_reference": relative(fixture.normalized_reference),
                    "normalized_reference_sha256": sha256(fixture.normalized_reference),
                    "expected_metadata": relative(fixture.metadata_path),
                    "expected_metadata_sha256": sha256(fixture.metadata_path),
                    "source_pdf_page_index_1_based": fixture.source_pdf_page_index_1_based,
                    "fixture_pdf_page_index_1_based": fixture.fixture_pdf_page_index_1_based,
                },
                "artifacts": [
                    relative(path)
                    for path in sorted((ROOT / fixture_id).rglob("*"))
                    if path.is_file() and path.name != "geometry.json"
                ]
                + [relative(geometry_path)],
            }
        )
    return records


def main() -> None:
    generated_at = datetime.now(timezone.utc).isoformat()
    catalog = FixtureCatalog.load(REPOSITORY_ROOT)
    tesseract_version = subprocess.check_output(("tesseract", "--version"), text=True).splitlines()[0]
    current_branch = git("branch", "--show-current")
    manifest = {
        "schema": "normalize-residual-geometry-forensics-v1",
        "generated_at_utc": generated_at,
        "experiment_start": {
            "git_commit_sha": "a2ccdb1f06f3e97fbcc437fb969636305031355f",
            "git_branch": "guh",
            "git_status": "clean",
            "historical_revision_confirmed": True,
            "current_source_geometry_sha256": sha256(REPOSITORY_ROOT / "src/normalize/geometry.py"),
        },
        "manifest_generation_state": {
            "git_commit_sha": git("rev-parse", "HEAD"),
            "git_branch": current_branch,
            "git_status_porcelain": git("status", "--porcelain=v1", "--untracked-files=all"),
            "dedicated_task_branch": current_branch == "geometry-forensics-identity-oracle",
            "branch_reason": "Dedicated branch created after the initial ref-write attempt was rejected by the read-only Git metadata layer.",
        },
        "environment": {
            "python": sys.version,
            "python_executable": sys.executable,
            "packages": package_versions(),
            "tesseract": tesseract_version,
            "geometry_module_import_path": str(__import__("normalize.geometry", fromlist=["__file__"]).__file__),
            "geometry_schema": "geometry-probe-v1",
        },
        "configuration": {
            "preprocessing_config": relative(CONFIG),
            "preprocessing_config_sha256": sha256(CONFIG),
            "dpi": 144,
            "work_root": "/tmp/normalize-residual-forensics",
            "source_pdfs_copied_to_research_directory": False,
        },
        "commands": [
            ".venv/bin/normalize check-env",
            ".venv/bin/normalize preprocess <fixture_id> --config fixtures/preprocessing.json --output /tmp/normalize-residual-forensics/<fixture_id>/preprocessed",
            ".venv/bin/normalize geometry --preprocessed /tmp/normalize-residual-forensics/<fixture_id>/preprocessed --output research/geometry/residual-forensics/<fixture_id>",
            ".venv/bin/python research/geometry/residual-forensics/make_diagnostic_crops.py",
            ".venv/bin/python research/geometry/residual-forensics/evaluate_invariance.py",
            ".venv/bin/python -m pytest -q tests/test_slice2.py -k 'permutation or identity_complete'",
            ".venv/bin/python -m pytest -q",
        ],
        "historical_comparison": {
            "previous_report": {
                "revision": "a2ccdb1f06f3e97fbcc437fb969636305031355f",
                "tests_passing": 84,
                "successful_fixtures": 4,
                "relativity_10": {"ambiguous": 4, "unassigned": 2},
                "relativity_17": {"ambiguous": 1, "unassigned": 0},
            },
            "historical_twelve_token_control": "kept distinct; not regenerated or treated as current evidence",
            "artifact_hashes_from_previous_report": "not supplied",
        },
        "fixtures": fixture_records(catalog),
        "output_artifacts": output_inventory(generated_at),
        "supporting_code": [
            relative(ROOT / "make_manifest.py"),
            relative(ROOT / "make_diagnostic_crops.py"),
            relative(ROOT / "evaluate_invariance.py"),
            "tests/geometry_oracle.py",
            "tests/test_slice2.py",
        ],
    }
    (ROOT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
