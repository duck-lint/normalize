import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "research/end-to-end/canonical-alignment-vertical-slice"


def test_frozen_exact_source_observations_match_prior_acquisition():
    observations = json.loads((ARTIFACTS / "geometry-observations.json").read_text())
    expected_rectangles = {
        26: [146, 468, 1255, 2160], 27: [204, 86, 1354, 2115],
        40: [134, 557, 1245, 2169], 41: [213, 145, 1337, 2190],
        52: [173, 473, 1279, 2166], 53: [177, 159, 1285, 2187],
    }
    expected_angles = {26: 0.48, 27: -0.92, 40: 0.90, 41: -0.80, 52: 0.74, 53: -0.38}
    for page in observations["pages"]:
        number = page["printed_page"]
        acquisition = page["acquisition"]
        assert acquisition["rectangle_xyxy_half_open"] == expected_rectangles[number]
        assert round(acquisition["fixed_angle_degrees"], 2) == expected_angles[number]
        assert acquisition["prior_exact_source_capture_match"] == {
            "admitted_token_count": True, "physical_line_count": True,
            "ambiguous_count": True, "unassigned_count": True,
            "final_raster_hash": True, "tsv_hash": True,
        }
        assert acquisition["tesseract_version"] == "5.3.4"
        assert acquisition["language"] == "eng"
        assert acquisition["config"] == "--psm 6"


def test_generated_acceptance_output_preserves_page_order_and_canonical_tokens():
    results = json.loads((ARTIFACTS / "results.json").read_text())
    assert results["page_order"] == [26, 27, 40, 41, 52, 53]
    assert len(results["sources"]) == 3
    assert all(item["lexical_order_preserved"] for item in results["sources"].values())
    output = (ARTIFACTS / "generated.md").read_text()
    assert output.index("Fixture pages 26, 27") < output.index("Fixture pages 40, 41") < output.index("Fixture pages 52, 53")
    for page in results["page_order"]:
        assert (ARTIFACTS / "per-page" / f"{page}.md").is_file()
    assert all(item["reference_loaded_after_generation"] for item in results["oracle_comparison_inputs"].values())


def test_page_span_manifest_retains_raw_source_hashes_and_page_mapping():
    manifest = json.loads((ARTIFACTS / "page-spans.json").read_text())
    pages = manifest["pages"]
    assert [item["printed_page"] for item in pages] == [26, 27, 40, 41, 52, 53]
    for item in pages:
        raw = (ROOT / item["raw_fixture"]).read_bytes()
        import hashlib
        assert hashlib.sha256(raw).hexdigest() == item["raw_fixture_sha256"]
        assert 0 <= item["start_byte"] < item["end_byte"] <= len(raw)


def test_production_downstream_modules_do_not_load_structural_oracles():
    for name in ("alignment.py", "reconstruction.py", "markdown.py"):
        source = (ROOT / "src/normalize" / name).read_text(encoding="utf-8")
        assert "normalized_reference" not in source
        assert ".expected.json" not in source
        assert ".normalized.md" not in source


def test_recorded_defects_use_only_authorized_taxonomy():
    defects = json.loads((ARTIFACTS / "defects.json").read_text())
    allowed = set(defects["allowed_categories"])
    assert defects["defect_count"] == len(defects["defects"])
    assert all(item["category"] in allowed for item in defects["defects"])
    assert all(item["first_meaningful_cause"] for item in defects["defects"])
    assert defects["defect_count"] == 8
    assert defects["affected_pages"] == [27, 52, 53]
    assert {item["id"] for item in defects["defects"]} >= {
        "p27-missing-boundary-before-if",
        "p27-missing-boundary-before-we-advance",
        "p27-missing-boundary-before-as-long",
        "p52-display-math-group",
        "p53-zero-equation-continuity",
    }
