"""Regression checks for reusable research verification contracts."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "research/geometry/pixel-evidence-prototype/prototype.py"
SPEC = importlib.util.spec_from_file_location("pixel_evidence_prototype_verification", SCRIPT)
assert SPEC and SPEC.loader
prototype = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prototype)


def test_verified_descendant_runs_reusable_prototype_tests(tmp_path: Path) -> None:
    verification = prototype.verify_research_contract()
    assert verification["current_revision"] != prototype.HISTORICAL_BASELINE_COMMIT
    result = prototype.run_prototype(tmp_path, include_real=False, write_manifest=False)
    assert result["verification"]["current_revision"] == verification["current_revision"]


def test_explicit_historical_reproduction_rejects_a_different_head(tmp_path: Path) -> None:
    with pytest.raises(AssertionError, match="historical reproduction requires exact revision"):
        prototype.run_prototype(
            tmp_path,
            include_real=False,
            write_manifest=False,
            require_exact_revision=True,
        )


def test_relevant_content_mismatch_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    original_hash = prototype.sha256
    geometry = (ROOT / "src/normalize/geometry.py").resolve()

    def mismatched_hash(path: Path) -> str:
        if path.resolve() == geometry:
            return "0" * 64
        return original_hash(path)

    monkeypatch.setattr(prototype, "sha256", mismatched_hash)
    with pytest.raises(AssertionError, match="production_geometry"):
        prototype.verify_research_contract()


def test_unrelated_repository_state_is_not_a_research_content_dependency() -> None:
    contract = prototype.verify_research_contract()
    assert "git_status" not in contract
    assert contract["content_hashes"]["prior_experiment_results"]
    assert contract["preserved_inputs"]


def test_historical_result_and_manifest_hashes_remain_recorded() -> None:
    contract = prototype.verify_research_contract()
    assert contract["historical_baseline"] == "699771d01c1a83c6f89c6a7eb2102e79a709b671"
    assert contract["exact_revision_required"] is False
