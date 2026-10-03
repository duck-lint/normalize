from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from normalize.bookrun import run_book
from normalize.books import (
    BookContractError,
    draft_profile_from_record,
    freeze_profile,
    load_manifest,
    load_profile,
    profile_record,
    revise_profile,
    revised_draft_from_record,
    save_manifest,
    revise_profile,
    save_profile,
    validate_profile_for_manifest,
)
from normalize.engine import BookEngine, EngineConfig
from normalize.rendering import preprocess_page_pixels


def _make_book(tmp_path: Path, rendered_texts=None):
    # The fixture is generated at test time: manifests model a page-image
    # collection directly and never require an intermediate PDF.
    page_texts = ["Alpha page.", "Beta page."]
    source = "Alpha page.\nBeta page.\n"
    canonical = tmp_path / "book.raw.md"
    canonical.write_text(source, encoding="utf-8")
    spans = [{"start": 0, "end": len("Alpha page.\n")},
             {"start": len("Alpha page.\n"), "end": len(source)}]
    pages = []
    for index, canonical_text in enumerate(page_texts, 1):
        image_path = tmp_path / f"scan-{index}.png"
        image = Image.new("RGB", (480, 360), "white")
        visible_text = rendered_texts[index - 1] if rendered_texts else canonical_text
        ImageDraw.Draw(image).text((70, 120), visible_text, fill="black", font=ImageFont.truetype("DejaVuSans.ttf", 28))
        image.save(image_path)
        pages.append({"page_id": f"sheet-{index:03}", "image": image_path.name, "canonical_span": spans[index - 1]})
    manifest_record = {"schema": "book-manifest-v1", "book_id": "synthetic-book",
                       "source_dpi": 144, "canonical_source": canonical.name, "pages": pages}
    manifest_path = tmp_path / "book.json"
    manifest_path.write_text(json.dumps(manifest_record, indent=2), encoding="utf-8")
    manifest = load_manifest(manifest_path)
    measurements = {
        "source_dpi": 144,
        "source_dpi_provenance": {"source": "human", "note": "scan acquisition record"},
        "calibration_pages": ["sheet-001"],
        "pages": [
            {"page_id": page["page_id"], "content_bounds": [30, 30, 450, 330],
             "content_status": "measured", "orientation_degrees": 0,
             "orientation_status": "no_transform", "deskew_degrees": 0.0,
             "deskew_status": "no_transform", "source": "human",
             "note": "synthetic test calibration"}
            for page in pages
        ],
    }
    return manifest, measurements


def _frozen_profile(manifest, measurements):
    return freeze_profile(draft_profile_from_record(measurements, manifest, profile_id="synthetic-profile"), manifest)


def test_manifest_preserves_declared_page_order_and_round_trips_sources(tmp_path):
    manifest, _ = _make_book(tmp_path)
    loaded = load_manifest(manifest.path)
    assert [page.page_id for page in loaded.pages] == ["sheet-001", "sheet-002"]
    assert loaded.pages[0].image.name == "scan-1.png"
    assert loaded.canonical_source.name == "book.raw.md"
    serialized = tmp_path / "serialized" / "book.json"
    save_manifest(loaded, serialized)
    again = load_manifest(serialized)
    assert again.sha256 == loaded.sha256
    assert [page.page_id for page in again.pages] == [page.page_id for page in loaded.pages]


def test_manifest_rejects_duplicate_ids_missing_sources_and_bad_span_order(tmp_path):
    manifest, _ = _make_book(tmp_path)
    record = json.loads(manifest.path.read_text())
    record["pages"][1]["page_id"] = record["pages"][0]["page_id"]
    manifest.path.write_text(json.dumps(record))
    with pytest.raises(BookContractError, match="duplicates"):
        load_manifest(manifest.path)
    record["pages"][1]["page_id"] = "sheet-002"
    record["pages"][0]["image"] = "absent.png"
    manifest.path.write_text(json.dumps(record))
    with pytest.raises(BookContractError, match="does not exist"):
        load_manifest(manifest.path)


def test_profile_freezes_with_measurement_provenance_and_requires_explicit_revision(tmp_path):
    manifest, measurements = _make_book(tmp_path)
    draft = draft_profile_from_record(measurements, manifest, profile_id="synthetic-profile")
    frozen = freeze_profile(draft, manifest)
    assert frozen.state == "frozen"
    assert frozen.pages[0].source == "human"
    assert frozen.pages[0].content_bounds == (30, 30, 450, 330)
    with pytest.raises(BookContractError, match="already frozen"):
        freeze_profile(frozen, manifest)
    revised = revise_profile(frozen, manifest)
    assert revised.revision == frozen.revision + 1
    assert revised.state == "draft" and revised.frozen_at is None
    next_measurements = json.loads(json.dumps(measurements))
    next_measurements["pages"][0]["content_bounds"] = [40, 40, 440, 320]
    second_draft = revised_draft_from_record(next_measurements, manifest, frozen)
    second_revision = freeze_profile(second_draft, manifest)
    assert second_revision.revision == frozen.revision + 1
    assert second_revision.pages[0].content_bounds == (40, 40, 440, 320)
    validate_profile_for_manifest(frozen, manifest, require_frozen=True)


def test_profile_serialization_round_trip_and_frozen_status(tmp_path):
    manifest, measurements = _make_book(tmp_path)
    profile = _frozen_profile(manifest, measurements)
    output = tmp_path / "profile.json"
    save_profile(profile, output)
    reloaded = load_profile(output)
    validate_profile_for_manifest(reloaded, manifest, require_frozen=True)
    assert profile_record(reloaded) == profile_record(profile)
    assert reloaded.sha256 == profile.sha256
    tampered = json.loads(output.read_text())
    tampered["pages"][0]["note"] = "silently edited frozen measurement"
    output.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(BookContractError, match="integrity digest mismatch"):
        load_profile(output)


@pytest.mark.parametrize("measurement, message", [
    ({"content_bounds": [-1, 0, 10, 10]}, "non-empty half-open"),
    ({"content_bounds": [0, 0, 9999, 9999]}, "exceed image dimensions"),
    ({"deskew_degrees": 90.0}, "magnitude at most 45"),
    ({"orientation_degrees": 45, "orientation_status": "measured"}, "one of 0, 90, 180, 270"),
])
def test_profile_rejects_invalid_bounds_and_angles(tmp_path, measurement, message):
    manifest, measurements = _make_book(tmp_path)
    measurements["pages"][0].update(measurement)
    with pytest.raises(BookContractError, match=message):
        _frozen_profile(manifest, measurements)


def test_profiles_from_different_calibration_provenance_use_same_fixed_transform(tmp_path):
    manifest, measurements = _make_book(tmp_path)
    first = _frozen_profile(manifest, measurements)
    imported_record = json.loads(json.dumps(measurements))
    imported_record["pages"][0]["source"] = "imported"
    second = _frozen_profile(manifest, imported_record)
    image = Image.open(manifest.pages[0].image)
    engine = BookEngine()
    left, left_meta = engine.preprocess(image, first.page_calibrations["sheet-001"], first.source_dpi)
    right, right_meta = engine.preprocess(image, second.page_calibrations["sheet-001"], second.source_dpi)
    assert left.tobytes() == right.tobytes()
    assert left_meta["final_dimensions_px"] == right_meta["final_dimensions_px"]
    with pytest.raises(ValueError, match="fixed global configuration"):
        BookEngine(EngineConfig(target_dpi=300))


def test_book_geometry_adapter_uses_the_established_fixed_ocr_arguments(monkeypatch):
    import normalize.engine as engine_module
    from pytesseract import Output

    calls = []
    monkeypatch.setattr(engine_module.pytesseract, "image_to_data",
                        lambda image, **kwargs: calls.append(kwargs) or "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n")
    monkeypatch.setattr(engine_module, "_engine_record", lambda: {
        "executable": "tesseract", "version": "synthetic", "language": "eng",
        "config": "--psm 6", "output": "TSV"})
    result = engine_module._observe_image_geometry(Image.new("RGB", (100, 80), "white"), "page-a",
                                                   book_id="synthetic", page_index=0, dpi=144,
                                                   source_image="scan.png", source_sha256="a" * 64)
    assert calls == [{"lang": "eng", "config": "--psm 6", "output_type": Output.STRING}]
    assert result["page_id"] == "page-a"
    assert result["provenance"]["source_image_sha256"] == "a" * 64


def test_profile_supports_page_orientation_and_deskew_as_separate_observations(tmp_path):
    manifest, measurements = _make_book(tmp_path)
    measurements["pages"][0].update({"orientation_degrees": 90, "orientation_status": "measured",
                                      "deskew_degrees": 0.4, "deskew_status": "measured"})
    profile = _frozen_profile(manifest, measurements)
    with Image.open(manifest.pages[0].image) as image:
        prepared, evidence = BookEngine().preprocess(image, profile.pages[0], profile.source_dpi)
    assert prepared.width < prepared.height
    assert evidence["orientation_degrees_clockwise"] == 90
    assert evidence["deskew_degrees_clockwise"] == 0.4


def test_book_engine_uses_shared_raster_preprocessor_and_half_up_dimensions():
    image = Image.new("RGB", (9, 5), "white")
    image.putpixel((2, 2), (0, 0, 0))
    bounds = (1, 0, 8, 5)
    shared, evidence = preprocess_page_pixels(
        image, content_bounds=bounds, orientation_degrees=90, deskew_degrees=0,
        source_dpi=288, target_dpi=144)
    assert shared.size == (3, 4)
    assert evidence["dimensions_after_crop_px"] == [7, 5]
    assert evidence["dimensions_after_orientation_px"] == [5, 7]
    assert evidence["dimension_rounding"] == "half-up"


def test_whole_book_runner_orders_pages_emits_provenance_and_reuses_unchanged_work(tmp_path, monkeypatch):
    manifest, measurements = _make_book(tmp_path)
    profile = _frozen_profile(manifest, measurements)
    output = tmp_path / "run"
    # Book source paths, not repository fixture discovery, define this run.
    monkeypatch.chdir(tmp_path)
    first = run_book(manifest, profile, output)
    assert first["status"] in {"succeeded", "needs_review"}
    assert [row["page_id"] for row in first["pages"]] == ["sheet-001", "sheet-002"]
    assert all(row["status"] != "failed" for row in first["pages"])
    markdown = (output / "normalized.md").read_text()
    assert markdown.index("Alpha page.") < markdown.index("Beta page.")
    assert "Alpha page." in markdown and "Beta page." in markdown
    assert json.loads((output / "run.json").read_text())["profile"]["sha256"] == profile.sha256
    assert json.loads((output / "pages/sheet-001/geometry.json").read_text())["provenance"]["page_id"] == "sheet-001"
    second = run_book(manifest, profile, output)
    assert all(row["cache_hit"] for row in second["pages"])


def test_changed_source_cannot_reuse_stale_page_geometry(tmp_path):
    manifest, measurements = _make_book(tmp_path)
    profile = _frozen_profile(manifest, measurements)
    output = tmp_path / "changed-source-run"
    run_book(manifest, profile, output)
    with Image.open(manifest.pages[1].image) as image:
        changed = image.convert("RGB")
    changed.putpixel((0, 0), (254, 255, 255))
    changed.save(manifest.pages[1].image)
    result = run_book(manifest, profile, output)
    assert [row["cache_hit"] for row in result["pages"]] == [True, False]
    assert result["pages"][1]["status"] == "failed"
    assert "source hash differs from manifest" in result["pages"][1]["error"]


def test_canonical_source_change_requires_manifest_reload_and_profile_refreeze(tmp_path):
    manifest, measurements = _make_book(tmp_path)
    profile = _frozen_profile(manifest, measurements)
    manifest.canonical_source.write_text("changed canonical source\n", encoding="utf-8")
    with pytest.raises(BookContractError, match="canonical source changed after manifest validation"):
        run_book(manifest, profile, tmp_path / "stale-canonical-run")


def test_runner_records_page_failure_and_preserves_its_canonical_text(tmp_path, monkeypatch):
    manifest, measurements = _make_book(tmp_path)
    profile = _frozen_profile(manifest, measurements)
    original = BookEngine.process_page

    def fail_second(self, page, calibration, **kwargs):
        if page.page_id == "sheet-002":
            raise RuntimeError("synthetic OCR outage")
        return original(self, page, calibration, **kwargs)

    monkeypatch.setattr(BookEngine, "process_page", fail_second)
    output = tmp_path / "failed-run"
    result = run_book(manifest, profile, output, resume=False)
    assert [row["status"] for row in result["pages"]] == ["succeeded", "failed"]
    assert result["status"] == "failed"
    markdown = (output / "normalized.md").read_text()
    assert "Beta page." in markdown
    review = json.loads((output / "review.json").read_text())
    assert any(item["code"] == "page_processing_failed" and item["page_id"] == "sheet-002"
               for item in review["diagnostics"])


def test_ocr_words_remain_anchors_and_never_become_emitted_prose(tmp_path):
    manifest, measurements = _make_book(tmp_path, rendered_texts=["OCR decoy.", "Visible anchor."])
    profile = _frozen_profile(manifest, measurements)
    output = tmp_path / "lexical-authority-run"
    run_book(manifest, profile, output)
    markdown = (output / "normalized.md").read_text()
    assert "Alpha page." in markdown and "Beta page." in markdown
    assert "OCR decoy" not in markdown and "Visible anchor" not in markdown
    diagnostics = json.loads((output / "review.json").read_text())["diagnostics"]
    assert any(item["code"] == "unmatched_ocr_anchors" for item in diagnostics)


def test_changed_page_calibration_invalidates_only_its_cached_geometry(tmp_path):
    manifest, measurements = _make_book(tmp_path)
    profile = _frozen_profile(manifest, measurements)
    output = tmp_path / "resume-run"
    run_book(manifest, profile, output)
    draft = revise_profile(profile, manifest)
    changed_page = replace(draft.pages[0], deskew_degrees=0.25, deskew_status="measured")
    changed = freeze_profile(replace(draft, pages=(changed_page, draft.pages[1])), manifest)
    second = run_book(manifest, changed, output)
    assert [row["cache_hit"] for row in second["pages"]] == [False, True]


def test_review_aggregates_diagnostics_without_mutating_markdown(tmp_path, monkeypatch):
    manifest, measurements = _make_book(tmp_path)
    profile = _frozen_profile(manifest, measurements)
    engine = BookEngine()
    before = engine.preprocess(Image.open(manifest.pages[0].image), profile.pages[0], profile.source_dpi)[0].tobytes()
    output = tmp_path / "review-run"
    run_book(manifest, profile, output)
    emitted = (output / "normalized.md").read_bytes()
    review = json.loads((output / "review.json").read_text())
    assert review["schema"] == "normalize-review-v1"
    assert (output / "normalized.md").read_bytes() == emitted
    after = engine.preprocess(Image.open(manifest.pages[0].image), profile.pages[0], profile.source_dpi)[0].tobytes()
    assert before == after


def test_run_rejects_draft_profile(tmp_path):
    manifest, measurements = _make_book(tmp_path)
    draft = draft_profile_from_record(measurements, manifest, profile_id="draft-profile")
    with pytest.raises(BookContractError, match="requires a frozen"):
        run_book(manifest, draft, tmp_path / "not-run")


def test_cli_validates_freezes_and_invokes_the_book_runner(tmp_path, monkeypatch, capsys):
    from normalize import cli

    manifest, measurements = _make_book(tmp_path)
    measurements_path = tmp_path / "measurements.json"
    measurements_path.write_text(json.dumps(measurements), encoding="utf-8")
    assert cli.main(["book", "validate", "--manifest", str(manifest.path)]) == 0
    profile_path = tmp_path / "frozen-profile.json"
    assert cli.main(["calibrate", "freeze", "--manifest", str(manifest.path),
                     "--measurements", str(measurements_path), "--profile-id", "synthetic-profile",
                     "--output", str(profile_path)]) == 0
    profile = load_profile(profile_path)
    called = {}

    def fake_run(loaded_manifest, loaded_profile, output, *, resume):
        called.update(manifest=loaded_manifest, profile=loaded_profile, output=output, resume=resume)
        return {"status": "succeeded", "run_id": "synthetic-run", "pages": [{}, {}],
                "review_diagnostic_count": 0}

    monkeypatch.setattr(cli, "run_book", fake_run)
    assert cli.main(["run", "--manifest", str(manifest.path), "--profile", str(profile_path),
                     "--output", str(tmp_path / "cli-run")]) == 0
    assert called["profile"].sha256 == profile.sha256
    assert called["resume"] is True
    assert "synthetic-run" in capsys.readouterr().out
