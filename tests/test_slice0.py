from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from normalize.cli import main
from normalize.environment import check_tesseract
from normalize.fixtures import FixtureCatalog, parse_fixture_metadata
from normalize.rendering import FixtureUnavailableError, render_fixture_page


ROOT = Path(__file__).parents[1]


def test_package_import_and_all_fixture_metadata_loads_without_pdf_substitution():
    catalog = FixtureCatalog.load(ROOT)

    assert len(catalog.items) == 6
    assert {item.fixture_id for item in catalog} == {
        "relativity_pdf10_pp26-27",
        "relativity_pdf17_pp40-41",
        "relativity_pdf23_pp52-53",
        "stella_maris_pdf03_session-I",
        "stella_maris_pdf06_dense-dialogue",
        "stella_maris_pdf18_session-II_p35",
    }
    assert all(item.fixture_pdf_page_index_1_based == 1 for item in catalog)
    assert [item.source_pdf_page_index_1_based for item in catalog] == [10, 17, 23, 3, 6, 18]
    assert all(item.raw_fixture.is_file() for item in catalog)


def test_metadata_parser_does_not_require_local_pdf(tmp_path: Path):
    fixture_dir = tmp_path / "fixtures" / "sample"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "sample.raw.md").write_text("source", encoding="utf-8")
    (fixture_dir / "sample.normalized.md").write_text("derived", encoding="utf-8")
    record = {
        "schema_version": "probe-expected-v1",
        "fixture_id": "sample",
        "source_pdf": "missing.pdf",
        "raw_fixture": "sample.raw.md",
        "normalized_reference": "sample.normalized.md",
        "fixture_pdf_page_index_1_based": 1,
        "source_pdf_page_index_1_based": 42,
    }
    metadata_path = fixture_dir / "sample.expected.json"
    metadata_path.write_text(json.dumps(record), encoding="utf-8")

    metadata = parse_fixture_metadata(metadata_path)

    assert metadata.source_pdf.name == "missing.pdf"
    assert not metadata.pdf_available
    assert metadata.source_pdf_page_index_1_based == 42


def test_render_reports_missing_exact_pdf_without_substitution(tmp_path: Path):
    metadata = FixtureCatalog.load(ROOT).items[0]
    missing = replace(metadata, source_pdf=tmp_path / "missing-exact.pdf")

    with pytest.raises(FixtureUnavailableError, match="No alternate PDF will be selected"):
        render_fixture_page(missing)


def test_tesseract_check_returns_version_when_available():
    report = check_tesseract()
    if not report.tesseract_available:
        pytest.skip(report.message)
    assert report.version


def test_one_page_render_preserves_local_and_source_page_provenance():
    metadata = FixtureCatalog.load(ROOT).get("relativity_pdf10_pp26-27")
    if not metadata.pdf_available:
        pytest.skip(f"missing exact fixture PDF: {metadata.source_pdf}")

    rendered = render_fixture_page(metadata)

    assert rendered.image.mode == "RGB"
    assert rendered.image.width > 0 and rendered.image.height > 0
    assert rendered.fixture_pdf_page_index_1_based == 1
    assert rendered.source_pdf_page_index_1_based == 10


def test_cli_fixture_listing_and_derived_render(tmp_path: Path, capsys):
    assert main(["fixtures", "--json"]) == 0
    listing = json.loads(capsys.readouterr().out)
    assert len(listing) == 6

    metadata = FixtureCatalog.load(ROOT).get("relativity_pdf10_pp26-27")
    if not metadata.pdf_available:
        pytest.skip(f"missing exact fixture PDF: {metadata.source_pdf}")
    output = tmp_path / "render.png"
    assert main(["render", metadata.fixture_id, "--output", str(output)]) == 0
    assert output.is_file()


def test_installed_console_lists_fixtures_without_src_path_injection():
    executable = Path(sys.executable).with_name("normalize")
    assert executable.is_file(), "clean bootstrap must install the normalize console command"

    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [str(executable), "fixtures", "--json"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    listing = json.loads(result.stdout)
    assert len(listing) == 6


def test_cli_rejects_hard_link_to_source_pdf():
    metadata = FixtureCatalog.load(ROOT).get("relativity_pdf10_pp26-27")
    if not metadata.pdf_available:
        pytest.skip(f"missing exact fixture PDF: {metadata.source_pdf}")

    source_hash = metadata.source_pdf.read_bytes()
    linked_output = metadata.source_pdf.parent / ".slice0-source-hard-link.png"
    os.link(metadata.source_pdf, linked_output)
    try:
        assert main(["render", metadata.fixture_id, "--output", str(linked_output)]) == 2
        assert metadata.source_pdf.read_bytes() == source_hash
    finally:
        linked_output.unlink(missing_ok=True)
