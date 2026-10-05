from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

from normalize.bookrun import run_book
from normalize.books import (BookContractError, draft_profile_from_record, freeze_profile,
                             load_manifest, load_profile, profile_record, save_profile,
                             validate_profile_for_manifest)
from normalize.cli import main
from normalize.engine import BookEngine
from normalize.lexical import (LexicalObservation, failed_observation,
                               observation_from_geometry, transcript_from_observations)
from normalize.geometry import TSV_HEADER, _PreprocessedPage, _engine_record, _page_geometry


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
    profile_json = profile_record(profile)
    assert profile_json["schema"] == "book-profile-v2"
    assert profile_json["physical_manifest_sha256"] == manifest.physical_sha256
    assert "manifest_sha256" not in profile_json
    profile_path = tmp_path / "profile.json"
    save_profile(profile, profile_path)
    assert load_profile(profile_path).schema == "book-profile-v2"
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


def test_v2_profile_compatibility_is_independent_of_lexical_evidence(tmp_path):
    manifest, profile = _scan_book(tmp_path)
    external_source = tmp_path / "optional-lexical.txt"
    external_source.write_text("first lexical evidence", encoding="utf-8")
    validate_profile_for_manifest(profile, manifest, require_frozen=True)
    external_source.write_text("corrected lexical evidence", encoding="utf-8")
    validate_profile_for_manifest(profile, manifest, require_frozen=True)


def test_v2_contract_rejects_lexical_fields(tmp_path):
    manifest, _ = _scan_book(tmp_path)
    record = json.loads(manifest.path.read_text())
    record["canonical_source"] = "raw.txt"
    manifest.path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(BookContractError, match="book-manifest-v2 fields"):
        load_manifest(manifest.path)


def test_manifest_and_profile_versions_are_never_cross_interpreted(tmp_path):
    manifest, profile_v2 = _scan_book(tmp_path)
    v2_record = json.loads(manifest.path.read_text())
    raw_path = tmp_path / "external.txt"
    raw_path.write_text("words", encoding="utf-8")
    v1_record = json.loads(manifest.path.read_text())
    v1_record["schema"] = "book-manifest-v1"
    v1_record["canonical_source"] = raw_path.name
    v1_record["pages"][0]["canonical_span"] = {"start": 0, "end": 5}
    manifest.path.write_text(json.dumps(v1_record), encoding="utf-8")
    manifest_v1 = load_manifest(manifest.path)
    measurements = {"source_dpi": 144,
        "source_dpi_provenance": {"source": "human", "note": "synthetic acquisition metadata"},
        "calibration_pages": ["page-001"], "pages": profile_record(profile_v2)["pages"]}
    profile_v1 = freeze_profile(draft_profile_from_record(measurements, manifest_v1,
                                                            profile_id="legacy-profile"), manifest_v1)
    assert profile_v1.schema == "book-profile-v1"
    assert profile_v1.manifest_sha256 == manifest_v1.sha256
    with pytest.raises(BookContractError, match="book-manifest-v1 requires book-profile-v1"):
        validate_profile_for_manifest(profile_v2, manifest_v1)
    with pytest.raises(BookContractError, match="book-manifest-v2 requires book-profile-v2"):
        v2_path = tmp_path / "book-v2.json"
        v2_path.write_text(json.dumps(v2_record), encoding="utf-8")
        validate_profile_for_manifest(profile_v1, load_manifest(v2_path))


def test_scan_only_run_derives_page_spans_and_writes_observation_transcript(tmp_path, monkeypatch):
    manifest, profile = _scan_book(tmp_path)
    tsv = "\t".join(("level", "page_num", "block_num", "par_num", "line_num", "word_num",
                      "left", "top", "width", "height", "conf", "text")) + "\n"
    tsv += "\t".join(("5", "1", "1", "1", "1", "1", "20", "30", "60", "15", "42.0", "Observed")) + "\n"
    tsv += "\t".join(("5", "1", "1", "1", "1", "2", "bad", "50", "40", "15", "91.0", "orphan")) + "\n"
    calls = []
    monkeypatch.setattr("normalize.engine.pytesseract.image_to_data",
                        lambda *args, **kwargs: calls.append(1) or tsv)
    run = run_book(manifest, profile, tmp_path / "run", engine=BookEngine(), resume=False)
    assert len(calls) == 1
    assert run["schema"] == "normalize-book-run-v2"
    assert run["status"] == "needs_review"
    transcript = json.loads((tmp_path / "run" / "lexical-transcript.json").read_text())
    assert transcript["method"] == "single-observer-transcript-v1"
    assert transcript["text"] == "Observed orphan"
    assert transcript["pages"][0]["transcript_span"] == {"start": 0, "end": 15}
    assert transcript["pages"][0]["token_ranges"][0]["observation_id"] == "token-0001"
    observation = json.loads((tmp_path / "run/pages/page-001/lexical-observation.json").read_text())
    assert observation["observations"][0]["text"] == "Observed"
    assert observation["observations"][1]["text"] == "orphan"
    assert observation["observations"][1]["anchor_id"] is None
    assert observation["observations"][1]["spatial_status"] == "unusable"
    emitted = (tmp_path / "run/normalized.md").read_text()
    assert "Observed" in emitted and "orphan" in emitted
    assert "canonical_source" not in (tmp_path / "run/run.json").read_text()
    review = json.loads((tmp_path / "run/review.json").read_text())
    assert any(item["code"] == "unmatched_lexical_token" for item in review["diagnostics"])


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
    provenance = {"fixture_id": "synthetic", "fixture_pdf_page_index_1_based": 1,
        "source_pdf_page_index_1_based": 1, "dpi": 144, "metadata_order": ["page-1"]}
    geometry = _page_geometry(_PreprocessedPage("page-1", Path("."), 180, 240, False,
        {"output_path": "synthetic.png"}), header + malformed_row, _engine_record(), provenance)
    malformed = observation_from_geometry("page-1", "a" * 64, geometry, {"engine": "fixture"},
                                          raw_tsv=header + malformed_row)
    assert len(malformed.observations) == 1
    malformed_word = malformed.observations[0]
    assert malformed_word["text"] == "uncertain-word"
    assert malformed_word["confidence"] == 31.0
    assert malformed_word["source_row"] == 1
    assert malformed_word["spatial_status"] == "unusable"
    assert malformed_word["anchor_id"] is None
    assert malformed_word["box"] is None
    assert any(item["code"] == "malformed_spatial_observation" for item in malformed.diagnostics)
    transcript = transcript_from_observations("book", [malformed])
    assert transcript.text == "uncertain-word"
    assert transcript.pages[0]["token_ranges"][0]["observation_id"] == malformed_word["observation_id"]

    empty = observation_from_geometry("page-2", "b" * 64,
        {"tokens": [], "error_details": [], "status": "uncertain"}, {"engine": "fixture"})
    assert any(item["code"] == "empty_ocr_page" for item in empty.diagnostics)


def test_real_geometry_schema_maps_accepted_word_to_lexical_observation():
    header = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
    word_row = "5\t1\t1\t1\t1\t1\t20\t30\t60\t15\t87.5\tword,\n"
    provenance = {"fixture_id": "synthetic", "fixture_pdf_page_index_1_based": 1,
        "source_pdf_page_index_1_based": 1, "dpi": 144, "metadata_order": ["page-1"]}
    geometry = _page_geometry(_PreprocessedPage("page-1", Path("."), 180, 240, False,
        {"output_path": "synthetic.png"}), header + word_row, _engine_record(), provenance)
    token = geometry["tokens"][0]
    assert {"x_px", "y_px", "width_px", "height_px"} <= set(token)
    observation = observation_from_geometry("page-1", "c" * 64, geometry,
        {"identity_sha256": "observer"}, raw_tsv=header + word_row)
    word = observation.observations[0]
    assert word["text"] == "word,"
    assert word["confidence"] == 87.5
    assert word["box"] == [20, 30, 60, 15]
    assert word["anchor_id"] == token["token_id"]
    assert word["physical_line_id"] == token["physical_line_id"]
    assert not any(item["code"] == "malformed_observation_geometry" for item in observation.diagnostics)

    geometry_only = observation_from_geometry("page-1", "c" * 64, geometry,
        {"identity_sha256": "observer"}, raw_tsv=None)
    projected_word = geometry_only.observations[0]
    assert projected_word["text"] == "word,"
    assert projected_word["confidence"] == 87.5
    assert projected_word["box"] == [20, 30, 60, 15]
    assert projected_word["anchor_id"] == token["token_id"]
    assert projected_word["physical_line_id"] == token["physical_line_id"]
    assert not any(item["code"] == "malformed_spatial_observation"
                   for item in geometry_only.diagnostics)


def test_literal_quotes_keep_geometry_and_lexical_tsv_projections_in_sync():
    header = "\t".join(TSV_HEADER)
    rows = [
        "4\t1\t1\t1\t0\t0\t0\t0\t0\t0\t-1\t",
        '5\t1\t1\t1\t1\t1\t10\t20\t20\t12\t37.331131\t"',
        '5\t1\t1\t1\t1\t2\t40\t20\t30\t12\t91.5\t"word',
        '5\t1\t1\t1\t1\t3\t80\t20\t30\t12\t92.5\tword"',
        '5\t1\t1\t1\t1\t4\t120\t20\t40\t12\t93.5\t"word"',
        "5\t1\t1\t1\t1\t5\t170\t20\t40\t12\t94.5\treader's",
        "5\t1\t1\t1\t1\t6\t220\t20\t35\t12\t95.5\tafter",
    ]
    raw_tsv = header + "\n" + "\n".join(rows) + "\n"
    provenance = {"fixture_id": "synthetic", "fixture_pdf_page_index_1_based": 1,
        "source_pdf_page_index_1_based": 1, "dpi": 144, "metadata_order": ["page-1"]}
    geometry = _page_geometry(_PreprocessedPage("page-1", Path("."), 300, 100, False,
        {"output_path": "synthetic.png"}), raw_tsv, _engine_record(), provenance)

    observations = observation_from_geometry("page-1", "e" * 64, geometry,
        {"identity_sha256": "observer"}, raw_tsv=raw_tsv)

    assert [token["source_row"] for token in geometry["tokens"]] == [2, 3, 4, 5, 6, 7]
    assert [token["text"] for token in geometry["tokens"]] == [
        '"', '"word', 'word"', '"word"', "reader's", "after"]
    assert [(item["source_row"], item["text"]) for item in observations.observations] == [
        (2, '"'), (3, '"word'), (4, 'word"'), (5, '"word"'),
        (6, "reader's"), (7, "after")]
    assert observations.observations[0]["confidence"] == 37.331131
    assert observations.observations[0]["box"] == [10, 20, 20, 12]
    for token, observation in zip(geometry["tokens"], observations.observations):
        assert observation["anchor_id"] == token["token_id"]
        assert observation["box"] == [token[key] for key in ("x_px", "y_px", "width_px", "height_px")]
    assert len({item["source_row"] for item in observations.observations}) == 6
    assert all("\n5\t" not in item["text"] for item in observations.observations)


def test_three_token_ranges_are_exact_across_pages_and_empty_page():
    def observation(page_id: str, words: list[str]) -> LexicalObservation:
        tokens = tuple({"observation_id": f"{page_id}:o{index}", "text": word,
                        "confidence": 90.0, "anchor_id": f"{page_id}:a{index}"}
                       for index, word in enumerate(words))
        return LexicalObservation(page_id, {"identity_sha256": "observer"}, "d" * 64,
                                  tokens, (), "observed")

    transcript = transcript_from_observations("book", [
        observation("p1", ["foo", "bar,", "baz!"]),
        observation("p2", []),
        observation("p3", ["qux?", "end.", "done!"]),
    ])
    assert transcript.text == "foo bar, baz!\n\n\n\nqux? end. done!"
    for page in transcript.pages:
        for token in page["token_ranges"]:
            assert transcript.text[token["start"]:token["end"]] == token["text"]
            assert token["observation_id"].startswith(page["page_id"] + ":o")
    assert transcript.pages[0]["token_ranges"][1]["text"] == "bar,"
    assert transcript.pages[1]["token_ranges"] == []
    assert transcript.pages[2]["token_ranges"][0]["start"] > transcript.pages[0]["token_ranges"][-1]["end"]
