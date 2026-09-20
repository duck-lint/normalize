from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from PIL import Image, ImageChops

import normalize.cli as cli_module
import normalize.geometry as geometry_module
from normalize.cli import main as cli_main
from normalize.geometry import (
    GEOMETRY_SCHEMA,
    TSV_HEADER,
    group_physical_lines,
    parse_tsv_rows,
    run_geometry,
)
from normalize.fixtures import FixtureCatalog
from normalize.rendering import SUCCESS, preprocess_fixture


ROOT = Path(__file__).parents[1]
CONFIG_PATH = ROOT / "fixtures" / "preprocessing.json"
FIXTURE_IDS = [
    "relativity_pdf10_pp26-27",
    "relativity_pdf17_pp40-41",
    "relativity_pdf23_pp52-53",
    "stella_maris_pdf03_session-I",
    "stella_maris_pdf06_dense-dialogue",
    "stella_maris_pdf18_session-II_p35",
]


def _tsv(*rows: str) -> str:
    return "\t".join(TSV_HEADER) + "\n" + "\n".join(rows) + "\n"


def _row(
    text: str = "word",
    *,
    level: str = "5",
    page: str = "1",
    block: str = "1",
    par: str = "1",
    line: str = "1",
    word: str = "1",
    x: str = "10",
    y: str = "20",
    width: str = "30",
    height: str = "10",
    confidence: str = "95",
) -> str:
    return "\t".join((level, page, block, par, line, word, x, y, width, height, confidence, text))


def _local_source_preprocessed(fixture_id: str, tmp_path: Path) -> tuple[Path, Path]:
    fixture = FixtureCatalog.load(ROOT).get(fixture_id)
    preprocess_dir = tmp_path / "preprocessed"
    assert preprocess_fixture(fixture, CONFIG_PATH, preprocess_dir)["status"] == SUCCESS
    source_copy = preprocess_dir / "source.pdf"
    shutil.copyfile(fixture.source_pdf, source_copy)
    metadata_path = next(preprocess_dir.glob("*.preprocess.json"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["source_pdf"] = source_copy.name
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    return preprocess_dir, source_copy


def test_token_admission_ignores_sentinel_rows_and_collapses_exact_duplicates():
    duplicate = _row()
    tokens, errors = parse_tsv_rows(
        _tsv(duplicate, duplicate, _row(text=" ", confidence="-1"), _row(text="ignored", confidence="-1")),
        100,
        100,
    )
    assert errors == []
    assert len(tokens) == 1
    assert tokens[0].source_row == 1


@pytest.mark.parametrize(
    ("row", "code"),
    (
        (_row(level="0"), "tsv_invalid"),
        (_row(confidence="101"), "tsv_invalid"),
        (_row(width="0"), "geometry_invalid"),
        (_row(x="80", width="30"), "geometry_invalid"),
        (_row(level="not-an-int"), "tsv_invalid"),
    ),
)
def test_token_admission_is_exhaustive_and_classifies_invalid_rows(row: str, code: str):
    tokens, errors = parse_tsv_rows(_tsv(row), 100, 100)
    assert tokens == []
    assert [error["code"] for error in errors] == [code]


def test_invalid_header_prevents_no_token_uncertainty():
    tokens, errors = parse_tsv_rows("wrong\theader\n", 100, 100)
    assert tokens == []
    assert errors[0]["code"] == "tsv_invalid"


def test_grouping_is_coordinate_based_and_stable():
    tsv = _tsv(
        _row("first", x="50", y="20", word="2"),
        _row("line", x="10", y="20", word="1"),
        _row("next", x="10", y="50", line="2"),
    )
    tokens, errors = parse_tsv_rows(tsv, 100, 100)
    assert errors == []
    lines, unresolved, measurements = group_physical_lines(tokens)
    assert not unresolved
    assert [line["token_ids"] for line in lines] == [["token-0002", "token-0001"], ["token-0003"]]
    assert measurements["tolerance_px"] == 3
    assert lines[0]["vertical_gap_to_next_px"] == 20


def test_grouping_tracks_a_sloped_page_baseline():
    rows = [
        _row("a", x="10", y="35", height="10", word="1"),
        _row("b", x="100", y="30", height="10", word="2"),
        _row("c", x="190", y="25", height="10", word="3"),
        _row("d", x="10", y="65", height="10", word="4"),
        _row("e", x="100", y="60", height="10", word="5"),
        _row("f", x="190", y="55", height="10", word="6"),
    ]
    tokens, errors = parse_tsv_rows(_tsv(*rows), 300, 100)
    assert errors == []

    lines, unresolved, measurements = group_physical_lines(tokens)

    assert unresolved == []
    assert [line["token_ids"] for line in lines] == [
        ["token-0001", "token-0002", "token-0003"],
        ["token-0004", "token-0005", "token-0006"],
    ]
    assert measurements["baseline_slope_px_per_px"] < 0


@pytest.mark.parametrize(
    ("groups", "expected_lines"),
    (
        (
            ((100, (10, 20, 30)), (120, (210, 220, 230))),
            (("token-0001", "token-0002", "token-0003"), ("token-0004", "token-0005", "token-0006")),
        ),
        (
            ((40, (10, 20, 30)), (70, (35, 45, 55))),
            (("token-0001", "token-0002", "token-0003"), ("token-0004", "token-0005", "token-0006")),
        ),
        (
            ((50, (10, 20, 30)), (50, (210, 220, 230))),
            (("token-0001", "token-0002", "token-0003"), ("token-0004", "token-0005", "token-0006")),
        ),
        (
            ((50, (10, 20, 30)), (85, (10, 20, 30))),
            (("token-0001", "token-0002", "token-0003"), ("token-0004", "token-0005", "token-0006")),
        ),
    ),
)
def test_grouping_preserves_synthetic_physical_line_oracles(groups, expected_lines):
    rows = []
    source_row = 1
    for center_y, x_positions in groups:
        for x in x_positions:
            rows.append(
                _row(
                    str(source_row),
                    x=str(x),
                    y=str(center_y - 5),
                    width="10",
                    height="10",
                    word=str(source_row),
                )
            )
            source_row += 1

    tokens, errors = parse_tsv_rows(_tsv(*rows), 300, 150)
    assert errors == []

    lines, unresolved, _ = group_physical_lines(tokens)

    assert unresolved == []
    assert [line["token_ids"] for line in lines] == [list(group) for group in expected_lines]


@pytest.mark.parametrize(
    ("centers", "code", "source_row"),
    (
        ((20, 25, 26, 29), "ambiguous_line_assignment", 3),
        ((25, 28, 29, 29), "unassigned_line_assignment", 1),
    ),
)
def test_grouping_serializes_actual_unresolved_assignments(centers, code, source_row):
    rows = [
        _row(str(index), x="10", y=str(center - 5), height="10", word=str(index))
        for index, center in enumerate(centers, start=1)
    ]
    tokens, errors = parse_tsv_rows(_tsv(*rows), 100, 100)
    assert errors == []

    lines, unresolved, _ = group_physical_lines(tokens)

    matching = [item for item in unresolved if item["token_source_row"] == source_row]
    assert matching and matching[0]["code"] == code
    if code == "ambiguous_line_assignment":
        assert len(matching[0]["candidate_line_ids"]) == 2
    else:
        assert matching[0]["candidate_line_ids"] == []
    if code == "ambiguous_line_assignment":
        assert any(source_row in line["unresolved_token_source_rows"] for line in lines)
    else:
        assert all(source_row not in line["unresolved_token_source_rows"] for line in lines)


def test_ambiguous_token_bounds_are_conservative_and_measurements_abstain():
    rows = [
        _row("first", x="10", y="15", width="30", height="10", word="1"),
        _row("middle-a", x="10", y="20", width="30", height="10", word="2"),
        _row("ambiguous", x="10", y="21", width="30", height="10", word="3"),
        _row("middle-b", x="10", y="24", width="30", height="10", word="4"),
    ]
    tokens, errors = parse_tsv_rows(_tsv(*rows), 100, 100)
    assert errors == []

    lines, unresolved, measurements = group_physical_lines(tokens)

    ambiguous = next(item for item in unresolved if item["code"] == "ambiguous_line_assignment")
    ambiguous_token = tokens[2]
    affected = [line for line in lines if line["line_id"] in ambiguous["candidate_line_ids"]]
    assert len(affected) == 2
    for line in affected:
        assert line["left_px"] <= ambiguous_token.x
        assert line["right_px"] >= ambiguous_token.x1
        assert line["top_px"] <= ambiguous_token.y
        assert line["bottom_px"] >= ambiguous_token.y1
        assert line["line_height_px"] is None
    assert all(line["vertical_gap_to_next_px"] is None for line in lines)
    assert measurements["line_height_median_px"] is None
    assert all(item["signed_vertical_gap_px"] is None for item in measurements["line_gaps"])


def test_unassigned_token_abstains_from_all_page_line_measurements():
    rows = [
        _row("unassigned", x="10", y="20", word="1"),
        _row("assigned-a", x="10", y="23", word="2"),
        _row("assigned-b", x="10", y="24", word="3"),
        _row("assigned-c", x="10", y="24", word="4"),
    ]
    tokens, errors = parse_tsv_rows(_tsv(*rows), 100, 100)
    assert errors == []

    lines, unresolved, measurements = group_physical_lines(tokens)

    assert any(item["code"] == "unassigned_line_assignment" for item in unresolved)
    for line in lines:
        assert all(line[field] is None for field in ("left_px", "right_px", "top_px", "bottom_px"))
        assert line["line_height_px"] is None
        assert line["vertical_gap_to_next_px"] is None
    assert measurements["line_height_median_px"] is None
    assert all(item["signed_vertical_gap_px"] is None for item in measurements["line_gaps"])


def test_fully_assigned_measurements_keep_numeric_values():
    tokens, errors = parse_tsv_rows(
        _tsv(_row("top", y="20"), _row("bottom", y="50", line="2")), 100, 100
    )
    assert errors == []

    lines, unresolved, measurements = group_physical_lines(tokens)

    assert unresolved == []
    assert [line["line_height_px"] for line in lines] == [10, 10]
    assert [line["vertical_gap_to_next_px"] for line in lines] == [20, None]
    assert measurements["line_height_median_px"] == 10
    assert measurements["line_gaps"] == [
        {
            "line_id": "line-0001",
            "next_line_id": "line-0002",
            "signed_vertical_gap_px": 20,
        }
    ]


def test_annotation_skips_line_rectangles_with_withheld_bounds(tmp_path: Path):
    image_path = tmp_path / "left.png"
    destination = tmp_path / "annotated.png"
    Image.new("RGB", (40, 40), "white").save(image_path)
    page = geometry_module._PreprocessedPage(
        side="left",
        image_path=image_path,
        width=40,
        height=40,
        blank=False,
        record={"output_path": "left.png"},
    )
    geometry = {
        "tokens": [],
        "physical_lines": [
            {
                "left_px": None,
                "top_px": None,
                "right_px": None,
                "bottom_px": None,
            }
        ],
        "block_evidence": [],
    }

    geometry_module._annotate(page, geometry, destination)

    with Image.open(destination) as annotated:
        assert ImageChops.difference(annotated, Image.new("RGB", annotated.size, "white")).getbbox() is None


def test_geometry_verifies_missing_and_modified_source_before_publication(tmp_path: Path):
    fixture = FixtureCatalog.load(ROOT).get(FIXTURE_IDS[0])
    preprocess_dir = tmp_path / "preprocessed"
    assert preprocess_fixture(fixture, CONFIG_PATH, preprocess_dir)["status"] == SUCCESS
    metadata_path = next(preprocess_dir.glob("*.preprocess.json"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    metadata["source_pdf"] = "missing.pdf"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    missing_result = run_geometry(preprocess_dir, tmp_path / "missing-geometry")
    assert missing_result["errors"] == ["provenance_mismatch"]
    assert not (tmp_path / "missing-geometry").exists()

    altered_source = preprocess_dir / "altered.pdf"
    altered_source.write_bytes(b"not the declared source")
    metadata["source_pdf"] = altered_source.name
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    altered_result = run_geometry(preprocess_dir, tmp_path / "altered-geometry")
    assert altered_result["errors"] == ["provenance_mismatch"]
    assert not (tmp_path / "altered-geometry").exists()


def test_failed_rerun_removes_previous_publication_for_missing_and_changed_source(tmp_path: Path):
    preprocess_dir, source_copy = _local_source_preprocessed(FIXTURE_IDS[0], tmp_path)
    output_dir = tmp_path / "geometry"

    assert run_geometry(preprocess_dir, output_dir)["status"] in {SUCCESS, "uncertain"}
    source_copy.unlink()
    missing_result = run_geometry(preprocess_dir, output_dir)

    assert missing_result["errors"] == ["provenance_mismatch"]
    assert not output_dir.exists()

    shutil.copyfile(FixtureCatalog.load(ROOT).get(FIXTURE_IDS[0]).source_pdf, source_copy)
    assert run_geometry(preprocess_dir, output_dir)["status"] in {SUCCESS, "uncertain"}
    source_copy.write_bytes(b"changed source bytes")
    changed_result = run_geometry(preprocess_dir, output_dir)

    assert changed_result["errors"] == ["provenance_mismatch"]
    assert not output_dir.exists()


def test_failed_rerun_preserves_publication_with_unowned_nested_annotation_file(tmp_path: Path):
    preprocess_dir, source_copy = _local_source_preprocessed(FIXTURE_IDS[0], tmp_path)
    output_dir = tmp_path / "geometry"

    first_result = run_geometry(preprocess_dir, output_dir)
    assert first_result["status"] in {SUCCESS, "uncertain"}
    keep_path = output_dir / "annotations" / "keep.txt"
    keep_path.write_text("user-owned annotation data\n", encoding="utf-8")
    prior_files = {
        path.relative_to(output_dir): path.read_bytes()
        for path in output_dir.rglob("*")
        if path.is_file() and not path.is_symlink()
    }

    source_copy.write_bytes(b"changed source bytes")
    result = run_geometry(preprocess_dir, output_dir)

    assert result["errors"] == ["provenance_mismatch"]
    assert output_dir.is_dir()
    assert {
        path.relative_to(output_dir): path.read_bytes()
        for path in output_dir.rglob("*")
        if path.is_file() and not path.is_symlink()
    } == prior_files
    assert keep_path.read_text(encoding="utf-8") == "user-owned annotation data\n"


def test_same_source_rerun_replaces_exact_owned_publication(tmp_path: Path):
    preprocess_dir, _source_copy = _local_source_preprocessed(FIXTURE_IDS[0], tmp_path)
    output_dir = tmp_path / "geometry"

    first_result = run_geometry(preprocess_dir, output_dir)
    second_result = run_geometry(preprocess_dir, output_dir)

    assert first_result["status"] in {SUCCESS, "uncertain"}
    assert second_result == first_result
    assert not list(tmp_path.glob(".*.geometry-previous-*"))
    assert not list(tmp_path.glob(".*.geometry-staging-*"))
    assert (output_dir / "geometry.json").is_file()
    assert sorted(path.relative_to(output_dir).as_posix() for path in output_dir.rglob("*")) == [
        "annotations",
        "annotations/left.png",
        "annotations/right.png",
        "geometry.json",
    ]


def test_same_source_rerun_preserves_unowned_nested_annotation_data(tmp_path: Path):
    preprocess_dir, _source_copy = _local_source_preprocessed(FIXTURE_IDS[0], tmp_path)
    output_dir = tmp_path / "geometry"

    first_result = run_geometry(preprocess_dir, output_dir)
    assert first_result["status"] in {SUCCESS, "uncertain"}
    keep_path = output_dir / "annotations" / "keep.txt"
    keep_path.write_text("user-owned annotation data\n", encoding="utf-8")
    unowned_dir = output_dir / "annotations" / "unowned"
    unowned_dir.mkdir()
    marker = unowned_dir / "marker.txt"
    marker.write_text("preserve", encoding="utf-8")
    prior_files = {
        path.relative_to(output_dir): path.read_bytes()
        for path in output_dir.rglob("*")
        if path.is_file() and not path.is_symlink()
    }

    result = run_geometry(preprocess_dir, output_dir)

    assert result["errors"] == ["publication_failure"]
    assert output_dir.is_dir()
    assert {
        path.relative_to(output_dir): path.read_bytes()
        for path in output_dir.rglob("*")
        if path.is_file() and not path.is_symlink()
    } == prior_files
    assert keep_path.read_text(encoding="utf-8") == "user-owned annotation data\n"
    assert marker.read_text(encoding="utf-8") == "preserve"
    assert not list(tmp_path.glob(".*.geometry-previous-*"))
    assert not list(tmp_path.glob(".*.geometry-staging-*"))


def test_failed_rerun_preserves_publication_with_unowned_nested_annotation_directory(
    tmp_path: Path,
):
    preprocess_dir, source_copy = _local_source_preprocessed(FIXTURE_IDS[0], tmp_path)
    output_dir = tmp_path / "geometry"
    first_result = run_geometry(preprocess_dir, output_dir)
    assert first_result["status"] in {SUCCESS, "uncertain"}

    unowned_dir = output_dir / "annotations" / "unowned"
    unowned_dir.mkdir()
    marker = unowned_dir / "marker.txt"
    marker.write_text("preserve", encoding="utf-8")
    source_copy.write_bytes(b"changed source bytes")

    result = run_geometry(preprocess_dir, output_dir)

    assert result["errors"] == ["provenance_mismatch"]
    assert unowned_dir.is_dir()
    assert marker.read_text(encoding="utf-8") == "preserve"


def test_failed_rerun_preserves_publication_with_unowned_nested_annotation_symlink(
    tmp_path: Path,
):
    preprocess_dir, source_copy = _local_source_preprocessed(FIXTURE_IDS[0], tmp_path)
    output_dir = tmp_path / "geometry"
    first_result = run_geometry(preprocess_dir, output_dir)
    assert first_result["status"] in {SUCCESS, "uncertain"}

    target = tmp_path / "annotation-target.txt"
    target.write_text("preserve", encoding="utf-8")
    unowned_link = output_dir / "annotations" / "unowned-link"
    unowned_link.symlink_to(target)
    source_copy.write_bytes(b"changed source bytes")

    result = run_geometry(preprocess_dir, output_dir)

    assert result["errors"] == ["provenance_mismatch"]
    assert unowned_link.is_symlink()
    assert target.read_text(encoding="utf-8") == "preserve"


def test_failed_rerun_marks_publication_failure_when_removal_cannot_be_verified(
    tmp_path: Path, monkeypatch
):
    preprocess_dir, source_copy = _local_source_preprocessed(FIXTURE_IDS[0], tmp_path)
    output_dir = tmp_path / "geometry"
    first_result = run_geometry(preprocess_dir, output_dir)
    assert first_result["status"] in {SUCCESS, "uncertain"}
    source_copy.unlink()
    monkeypatch.setattr(geometry_module, "_safe_remove", lambda _path: False)

    result = run_geometry(preprocess_dir, output_dir)

    assert result["errors"] == ["provenance_mismatch"]
    retained = json.loads((output_dir / "geometry.json").read_text(encoding="utf-8"))
    assert retained["status"] == "failure"
    assert retained["errors"] == ["cleanup_unverified"]


def test_failed_rerun_reports_cleanup_unverified_if_invalidation_cannot_be_verified(
    tmp_path: Path, monkeypatch
):
    preprocess_dir, source_copy = _local_source_preprocessed(FIXTURE_IDS[0], tmp_path)
    output_dir = tmp_path / "geometry"
    first_result = run_geometry(preprocess_dir, output_dir)
    assert first_result["status"] in {SUCCESS, "uncertain"}
    source_copy.unlink()
    original_replace = geometry_module.os.replace
    monkeypatch.setattr(geometry_module, "_safe_remove", lambda _path: False)

    def fail_invalidation_replace(source, destination):
        if Path(source).name.startswith(".geometry-invalid-"):
            raise OSError("injected invalidation failure")
        return original_replace(source, destination)

    monkeypatch.setattr(geometry_module.os, "replace", fail_invalidation_replace)

    result = run_geometry(preprocess_dir, output_dir)

    assert result["errors"] == ["cleanup_unverified"]
    retained = json.loads((output_dir / "geometry.json").read_text(encoding="utf-8"))
    assert retained["status"] in {SUCCESS, "uncertain"}


@pytest.mark.parametrize(
    "inventory_kind",
    [
        "malformed",
        "extra",
        "annotation_path_traversal",
        "geometry_symlink",
        "annotations_symlink",
        "output_symlink",
    ],
)
def test_failed_rerun_does_not_remove_unrecognized_output(
    tmp_path: Path, inventory_kind: str
):
    preprocess_dir, source_copy = _local_source_preprocessed(FIXTURE_IDS[0], tmp_path)
    output_dir = tmp_path / "geometry"
    if inventory_kind == "malformed":
        (output_dir / "annotations").mkdir(parents=True)
        (output_dir / "geometry.json").write_text("not json", encoding="utf-8")
    elif inventory_kind == "extra":
        (output_dir / "annotations").mkdir(parents=True)
        (output_dir / "geometry.json").write_text("{}", encoding="utf-8")
        (output_dir / "unrelated.txt").write_text("preserve", encoding="utf-8")
    elif inventory_kind == "annotation_path_traversal":
        assert run_geometry(preprocess_dir, output_dir)["status"] in {SUCCESS, "uncertain"}
        geometry_path = output_dir / "geometry.json"
        geometry = json.loads(geometry_path.read_text(encoding="utf-8"))
        geometry["annotation_paths"] = ["annotations/../outside.png"]
        geometry_path.write_text(json.dumps(geometry), encoding="utf-8")
    elif inventory_kind == "geometry_symlink":
        target = tmp_path / "geometry-target.json"
        target.write_text("{}", encoding="utf-8")
        output_dir.mkdir()
        (output_dir / "annotations").mkdir()
        (output_dir / "geometry.json").symlink_to(target)
    elif inventory_kind == "annotations_symlink":
        target = tmp_path / "annotations-target"
        target.mkdir()
        output_dir.mkdir()
        (output_dir / "geometry.json").write_text("{}", encoding="utf-8")
        (output_dir / "annotations").symlink_to(target, target_is_directory=True)
    else:
        target = tmp_path / "output-target"
        target.mkdir()
        (target / "keep.txt").write_text("preserve", encoding="utf-8")
        output_dir.symlink_to(target, target_is_directory=True)

    def output_snapshot() -> list[str]:
        return sorted(
            path.relative_to(tmp_path).as_posix()
            for path in (tmp_path / "geometry").parent.rglob("geometry*")
            if path.exists() or path.is_symlink()
        )

    before = output_snapshot()
    source_copy.unlink()
    result = run_geometry(preprocess_dir, output_dir)
    after = output_snapshot()

    assert result["errors"] == ["provenance_mismatch"]
    assert before == after


def test_relative_source_pdf_resolves_from_metadata_directory(tmp_path: Path):
    fixture = FixtureCatalog.load(ROOT).get(FIXTURE_IDS[0])
    preprocess_dir = tmp_path / "preprocessed"
    assert preprocess_fixture(fixture, CONFIG_PATH, preprocess_dir)["status"] == SUCCESS
    source_copy = preprocess_dir / "source.pdf"
    shutil.copyfile(fixture.source_pdf, source_copy)
    metadata_path = next(preprocess_dir.glob("*.preprocess.json"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["source_pdf"] = source_copy.name
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    result = run_geometry(preprocess_dir, tmp_path / "geometry")

    assert result["provenance"]["source_pdf"] == source_copy.name
    assert result["provenance"]["source_pdf_sha256"] == hashlib.sha256(source_copy.read_bytes()).hexdigest()


def test_geometry_cli_publishes_reloadable_provenance_and_annotations(tmp_path: Path):
    fixture = FixtureCatalog.load(ROOT).get(FIXTURE_IDS[0])
    source_digest = hashlib.sha256(fixture.source_pdf.read_bytes()).hexdigest()
    preprocess_dir = tmp_path / "preprocessed"
    assert preprocess_fixture(fixture, CONFIG_PATH, preprocess_dir)["status"] == SUCCESS
    output_dir = tmp_path / "geometry"

    result = run_geometry(preprocess_dir, output_dir)
    assert result["schema"] == GEOMETRY_SCHEMA
    assert result["fixture_id"] == fixture.fixture_id
    assert result["provenance"]["source_pdf_sha256"] == source_digest
    assert result["provenance"]["fixture_pdf_page_index_1_based"] == 1
    assert result["provenance"]["source_pdf_page_index_1_based"] == 10
    assert [page["side"] for page in result["pages"]] == ["left", "right"]
    assert all(token["coordinate_system"] == {"origin": "top-left", "units": "px"} for page in result["pages"] for token in page["tokens"])
    assert all("tesseract_block_num" in token["evidence_only"] for page in result["pages"] for token in page["tokens"])
    reloaded = json.loads((output_dir / "geometry.json").read_text(encoding="utf-8"))
    assert reloaded == result
    for page in result["pages"]:
        with Image.open(output_dir / "annotations" / f"{page['side']}.png") as image:
            assert image.size == (page["width_px"], page["height_px"])


def test_blank_declared_page_is_explicit(tmp_path: Path):
    fixture = FixtureCatalog.load(ROOT).get("stella_maris_pdf03_session-I")
    preprocess_dir = tmp_path / "preprocessed"
    assert preprocess_fixture(fixture, CONFIG_PATH, preprocess_dir)["status"] == SUCCESS
    result = run_geometry(preprocess_dir, tmp_path / "geometry")
    blank = result["pages"][0]
    assert blank["side"] == "left"
    assert blank["blank"] is True
    assert blank["tokens"] == []
    assert "no_tokens_on_declared_nonblank_page" not in blank["uncertainties"]
    assert (tmp_path / "geometry" / "annotations" / "left.png").is_file()


@pytest.mark.parametrize(("status", "expected_exit"), ((SUCCESS, 0), ("uncertain", 3), ("failure", 2)))
def test_geometry_cli_maps_each_status_to_declared_exit_code(
    monkeypatch, tmp_path: Path, capsys, status, expected_exit
):
    monkeypatch.setattr(cli_module, "run_geometry", lambda _preprocessed, _output: {"status": status})
    exit_code = cli_main(
        ["geometry", "--preprocessed", str(tmp_path / "preprocessed"), "--output", str(tmp_path / "geometry")]
    )
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == expected_exit
    assert payload["status"] == status


def test_geometry_cli_does_not_discover_repository_catalog(monkeypatch, tmp_path: Path, capsys):
    monkeypatch.setattr(cli_module, "FixtureCatalog", type("NoCatalog", (), {"load": staticmethod(lambda: (_ for _ in ()).throw(AssertionError("catalog loaded")))}))
    monkeypatch.setattr(cli_module, "run_geometry", lambda _preprocessed, _output: {"status": SUCCESS})

    assert cli_main(
        ["geometry", "--preprocessed", str(tmp_path / "preprocessed"), "--output", str(tmp_path / "geometry")]
    ) == 0
    assert json.loads(capsys.readouterr().out)["status"] == SUCCESS


def test_invalid_regular_file_parent_returns_structured_api_and_cli_failure(
    tmp_path: Path, capsys
):
    fixture = FixtureCatalog.load(ROOT).get(FIXTURE_IDS[0])
    preprocess_dir = tmp_path / "preprocessed"
    assert preprocess_fixture(fixture, CONFIG_PATH, preprocess_dir)["status"] == SUCCESS
    parent_file = tmp_path / "parent.pdf"
    parent_file.write_bytes(b"fixture parent is intentionally not a directory")
    output_dir = parent_file / "geometry"

    api_result = run_geometry(preprocess_dir, output_dir)

    assert api_result["status"] == "failure"
    assert api_result["fixture_id"] == fixture.fixture_id
    assert api_result["errors"] == ["publication_failure"]
    assert api_result["error_details"][0]["code"] == "publication_failure"
    assert str(parent_file) in api_result["error_details"][0]["reason"]
    assert not output_dir.exists()

    exit_code = cli_main(
        ["geometry", "--preprocessed", str(preprocess_dir), "--output", str(output_dir)]
    )
    captured = capsys.readouterr()
    cli_result = json.loads(captured.out)

    assert exit_code == 2
    assert cli_result == api_result
    assert "Traceback" not in captured.out
    assert "Traceback" not in captured.err
    assert captured.err == ""
    assert not output_dir.exists()


def test_geometry_staging_cleanup_failure_is_explicit(tmp_path: Path, monkeypatch):
    fixture = FixtureCatalog.load(ROOT).get(FIXTURE_IDS[0])
    preprocess_dir = tmp_path / "preprocessed"
    assert preprocess_fixture(fixture, CONFIG_PATH, preprocess_dir)["status"] == SUCCESS

    def fail_annotation(*_args, **_kwargs):
        raise geometry_module.GeometryError("annotation_failure", "injected annotation failure")

    monkeypatch.setattr(geometry_module, "_annotate", fail_annotation)
    monkeypatch.setattr(geometry_module, "_safe_remove", lambda _path: False)

    result = run_geometry(preprocess_dir, tmp_path / "geometry")

    assert result["status"] == "failure"
    assert result["errors"] == ["cleanup_unverified"]
    assert "annotation_failure" in result["error_details"][0]["reason"]


def test_geometry_serialization_cleanup_failure_is_explicit(tmp_path: Path, monkeypatch):
    fixture = FixtureCatalog.load(ROOT).get(FIXTURE_IDS[0])
    preprocess_dir = tmp_path / "preprocessed"
    assert preprocess_fixture(fixture, CONFIG_PATH, preprocess_dir)["status"] == SUCCESS
    original_write_text = Path.write_text

    def fail_geometry_write(path, *args, **kwargs):
        if path.name == "geometry.json":
            raise OSError("injected serialization failure")
        return original_write_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_geometry_write)
    monkeypatch.setattr(geometry_module, "_safe_remove", lambda _path: False)

    result = run_geometry(preprocess_dir, tmp_path / "geometry")

    assert result["status"] == "failure"
    assert result["errors"] == ["cleanup_unverified"]
    assert "injected serialization failure" in result["error_details"][0]["reason"]
