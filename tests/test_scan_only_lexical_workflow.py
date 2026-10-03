from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

from normalize.bookrun import run_book
from normalize.books import (BookContractError, draft_profile_from_record, freeze_profile,
                             load_manifest, validate_profile_for_manifest)
from normalize.cli import main
from normalize.engine import BookEngine
from normalize.lexical import (LexicalObservation, failed_observation,
                               observation_from_geometry, transcript_from_observations)


def _scan_book(tmp_path: Path):
    image_path = tmp_path / "page.png"
    Image.new("RGB", (180, 240), "white").save(image_path)
    source_hash = hashlib.sha256(image_path.read_bytes()).hexdigest()
    manifest_path = tmp_path / "book.json"
    manifest_path.write_text(json.dumps({"schema": "book-manifest-v2", "book_id": "scan-only",
        "source_dpi": 144, "pages": [{"page_id": "page-001", "image": image_path.name,
                                      "source_sha256": source_hash}]}), encoding="utf-8")
    manifest = load_manifest(manifest_path)
    measurements = {"source_dpi": 144,
        "source_dpi_provenance": {"source": "human", "note": "synthetic acquisition metadata"},
        "calibration_pages": ["page-001"],
        "pages": [{"page_id": "page-001", "content_bounds": None,
            "content_status": "full_page", "orientation_degrees": 0,
            "orientation_status": "no_transform", "deskew_degrees": 0.0,
            "deskew_status": "no_transform", "source": "human", "note": "synthetic page"}]}
    profile = freeze_profile(draft_profile_from_record(measurements, manifest, profile_id="scan-profile"), manifest)
    return manifest, profile


def test_v2_manifest_and_frozen_profile_are_physical_only(tmp_path):
    manifest, profile = _scan_book(tmp_path)
    assert manifest.canonical_source is None
    assert manifest.schema == "book-manifest-v2"
    assert manifest.sha256 == manifest.physical_sha256
    validate_profile_for_manifest(profile, manifest, require_frozen=True)
    manifest_record = json.loads(manifest.path.read_text())
    assert "canonical_source" not in manifest_record
    assert "canonical_span" not in manifest_record["pages"][0]
    assert main(["book", "validate", "--manifest", str(manifest.path)]) == 0
    with Image.open(manifest.pages[0].image) as source:
        changed = source.copy()
    changed.putpixel((0, 0), (240, 240, 240))
    changed.save(manifest.pages[0].image)
    record = json.loads(manifest.path.read_text())
    record["pages"][0]["source_sha256"] = hashlib.sha256(manifest.pages[0].image.read_bytes()).hexdigest()
    manifest.path.write_text(json.dumps(record), encoding="utf-8")
    changed_manifest = load_manifest(manifest.path)
    assert changed_manifest.physical_sha256 != manifest.physical_sha256
    with pytest.raises(BookContractError, match="physical book identity"):
        validate_profile_for_manifest(profile, changed_manifest)


def test_v2_contract_rejects_lexical_fields(tmp_path):
    manifest, _ = _scan_book(tmp_path)
    record = json.loads(manifest.path.read_text())
    record["canonical_source"] = "raw.txt"
    manifest.path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(BookContractError, match="book-manifest-v2 fields"):
        load_manifest(manifest.path)


def test_scan_only_run_derives_page_spans_and_writes_observation_transcript(tmp_path, monkeypatch):
    manifest, profile = _scan_book(tmp_path)
    tsv = "\t".join(("level", "page_num", "block_num", "par_num", "line_num", "word_num",
                      "left", "top", "width", "height", "conf", "text")) + "\n"
    tsv += "\t".join(("5", "1", "1", "1", "1", "1", "20", "30", "60", "15", "42.0", "Observed")) + "\n"
    calls = []
    monkeypatch.setattr("normalize.engine.pytesseract.image_to_data",
                        lambda *args, **kwargs: calls.append(1) or tsv)
    run = run_book(manifest, profile, tmp_path / "run", engine=BookEngine(), resume=False)
    assert len(calls) == 1
    assert run["schema"] == "normalize-book-run-v2"
    assert run["status"] == "needs_review"
    transcript = json.loads((tmp_path / "run" / "lexical-transcript.json").read_text())
    assert transcript["method"] == "single-observer-transcript-v1"
    assert transcript["text"] == "Observed"
    assert transcript["pages"][0]["transcript_span"] == {"start": 0, "end": 8}
    assert transcript["pages"][0]["token_ranges"][0]["observation_id"] == "token-0001"
    observation = json.loads((tmp_path / "run/pages/page-001/lexical-observation.json").read_text())
    assert observation["observations"][0]["text"] == "Observed"
    assert "Observed" in (tmp_path / "run/normalized.md").read_text()
    assert not (tmp_path / "run/run.json").read_text().find("canonical_source") >= 0


def test_transcript_preserves_low_confidence_and_failed_page_diagnostics():
    low = LexicalObservation("p1", {"engine": "fixture"}, "a" * 64,
        ({"observation_id": "o1", "text": "rn", "confidence": 4.0, "physical_line_id": "l1"},),
        ({"code": "observer_confidence_below_50", "observation_id": "o1", "confidence": 4.0},), "observed")
    failed = failed_observation("p2", "b" * 64, "recognizer unavailable", {"engine": "fixture"})
    transcript = transcript_from_observations("book", [low, failed])
    assert transcript.text == "rn\n\n"
    assert transcript.pages[0]["transcript_span"] == {"start": 0, "end": 4}
    assert transcript.pages[1]["transcript_span"] == {"start": 4, "end": 4}
    assert any(item["code"] == "observer_confidence_below_50" for item in transcript.diagnostics)
    assert any(item["code"] == "ocr_page_failed" for item in transcript.diagnostics)


def test_malformed_tsv_evidence_is_retained_and_empty_pages_are_diagnosed():
    header = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
    malformed_row = "5\t1\t1\t1\t1\t1\tbad\t20\t60\t15\t31.0\tuncertain-word\n"
    from normalize.geometry import _PreprocessedPage, _engine_record, _page_geometry

    provenance = {"fixture_id": "synthetic", "fixture_pdf_page_index_1_based": 1,
        "source_pdf_page_index_1_based": 1, "dpi": 144, "metadata_order": ["page-1"]}
    geometry = _page_geometry(_PreprocessedPage("page-1", Path("."), 180, 240, False,
        {"output_path": "synthetic.png"}), header + malformed_row, _engine_record(), provenance)
    malformed = observation_from_geometry("page-1", "a" * 64, geometry, {"engine": "fixture"},
                                          raw_tsv=header + malformed_row)
    assert malformed.observations == ()
    malformed_record = next(item for item in malformed.diagnostics if item["code"] == "malformed_observation")
    assert malformed_record["observed_text"] == "uncertain-word"

    empty = observation_from_geometry("page-2", "b" * 64,
        {"tokens": [], "error_details": [], "status": "uncertain"}, {"engine": "fixture"})
    assert any(item["code"] == "empty_ocr_page" for item in empty.diagnostics)
