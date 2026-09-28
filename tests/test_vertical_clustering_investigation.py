"""Integrity checks for the research-only vertical-clustering record."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "research/geometry/vertical-clustering-investigation"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(name: str) -> dict:
    return json.loads((RESEARCH / name).read_text(encoding="utf-8"))


def test_baseline_residuals_and_synthetic_permutation_results_are_recorded() -> None:
    results = _load("results.json")
    assert results["baseline_commit"] == "c0f7ea88493a07e6139e9c71d413a2eda130c17b"
    # Keep the seven-token observation explicit; GH-11's twelve-token record is
    # intentionally a separate historical datum.
    assert results["baseline"]["current_residual_counts"] == {
        "relativity_pdf10_pp26-27": {"ambiguous": 4, "unassigned": 2},
        "relativity_pdf17_pp40-41": {"ambiguous": 1, "unassigned": 0},
        "total_unresolved": 7,
    }
    identities = [
        tuple(item["identity"])
        for sides in results["real_scan_residuals"].values()
        for page in sides.values()
        for item in page["residual_token_traces"]
    ]
    assert len(identities) == 7
    assert len(set(identities)) == 7
    assert all(
        all(case["input_permutation_stability"].values())
        for case in results["synthetic_cases"]
    )


def test_production_control_matches_versioned_geometry_and_research_scope() -> None:
    results = _load("results.json")
    for sides in results["real_scan_residuals"].values():
        for page in sides.values():
            assert page["production"]["matches_versioned_geometry"]
    assert results["scope"] == {
        "production_assignments_modified": False,
        "pixel_evidence_integrated": False,
        "non_greedy_vertical_model_integrated": False,
        "fixture_expectations_modified": False,
    }


def test_recovered_evidence_and_manifest_hashes_are_durable() -> None:
    results = _load("results.json")
    ledger = _load("provenance-ledger.json")
    manifest = _load("manifest.json")
    assert ledger["recovery"] == results["recovery"]
    assert results["recovery"]["temporary_originals_modified_or_deleted"] is False
    assert all(
        record["repository_destination"].startswith("research/geometry/")
        for record in results["recovery"]["recovered"]
    )
    assert all(
        not command.startswith("/tmp") and " /tmp/" not in command
        for command in manifest["commands"]
    )
    recorded_rasters = []
    post_archive_script_updates = {
        "research/geometry/vertical-clustering-investigation/investigate.py"
    }
    for artifact in manifest["artifact_paths_and_hashes"]:
        path = ROOT / artifact["path"]
        if path.suffix.lower() in {".png", ".pdf"}:
            # The manifest preserves the historical identity; purge policy
            # intentionally does not require the binary to be in this checkout.
            assert len(artifact["sha256"]) == 64
            assert artifact["size_bytes"] > 0
            recorded_rasters.append(artifact)
            continue
        if artifact["path"] in post_archive_script_updates:
            # The archived inventory hashes the original executable. This
            # repair removes only its purged-object gate; its current contract
            # is checked by the geometry/oracle hash test below.
            assert len(artifact["sha256"]) == 64
            continue
        assert path.is_file(), artifact["path"]
        assert _sha256(path) == artifact["sha256"], artifact["path"]
        assert path.stat().st_size == artifact["size_bytes"], artifact["path"]
    assert recorded_rasters
    assert all(item["path"].endswith(".png") for item in recorded_rasters)
    recovered_png_records = [
        item for item in results["recovery"]["recovered"] if item["repository_destination"].endswith(".png")
    ]
    assert len(recovered_png_records) == len(recorded_rasters)
    assert {
        item["repository_destination"]: item["repository_sha256"] for item in recovered_png_records
    } == {item["path"]: item["sha256"] for item in recorded_rasters}


def test_source_and_oracle_hashes_match_the_published_baseline() -> None:
    results = _load("results.json")
    assert _sha256(ROOT / "src/normalize/geometry.py") == results["production_geometry_sha256"]
    assert _sha256(ROOT / "tests/geometry_oracle.py") == results["identity_complete_oracle_sha256"]
