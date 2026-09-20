from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from normalize.cli import main as cli_main
import normalize.rendering as rendering
from normalize.fixtures import FixtureCatalog
from normalize.rendering import (
    FAILURE,
    METADATA_SCHEMA,
    SUCCESS,
    UNCERTAIN,
    PreprocessingConfigError,
    load_preprocessing_config,
    preprocess_fixture,
    validate_metadata_contract,
)


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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _exact_artifacts(output_dir: Path, fixture_id: str) -> list[Path]:
    return [
        output_dir / f"{fixture_id}.{kind}.png"
        for kind in ("spread", "page", "left", "right")
    ]


def _write_profile_config(tmp_path: Path, **profile_updates) -> Path:
    record = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    record["profiles"][FIXTURE_IDS[0]].update(profile_updates)
    path = tmp_path / "variant.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def test_authoritative_config_has_one_explicit_profile_per_fixture():
    config = load_preprocessing_config(CONFIG_PATH)
    assert config.dpi == 144
    assert set(config.profiles) == set(FIXTURE_IDS)
    for profile in config.profiles.values():
        assert profile.result_kind == "spread"
        assert profile.rotation_degrees == 0
        assert profile.crop is None
        assert profile.deskew_degrees == 0
        assert profile.split_boundary == 792
        assert profile.output_order == ("left", "right")


def test_config_rejects_unknown_shape_and_invalid_uncertainty(tmp_path: Path):
    malformed = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    malformed["profiles"][FIXTURE_IDS[0]]["uncertainty"] = {
        "code": "split_unresolved",
        "field": "crop",
        "reason": "ambiguous",
    }
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(malformed), encoding="utf-8")
    with pytest.raises(PreprocessingConfigError, match="must name field 'split'"):
        load_preprocessing_config(path)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("result_kind", []),
        ("rotation_degrees", []),
        ("blank_sides", [[]]),
    ),
)
def test_profile_validator_rejects_unhashable_typed_values(
    tmp_path: Path, field: str, value: object
):
    profile = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))["profiles"][FIXTURE_IDS[0]]
    profile[field] = value

    with pytest.raises(PreprocessingConfigError):
        rendering._parse_profile(profile, tmp_path / "variant.json", FIXTURE_IDS[0])


def test_uncertainty_validator_rejects_unhashable_code(tmp_path: Path):
    uncertainty = {"code": [], "field": "split", "reason": "ambiguous"}

    with pytest.raises(PreprocessingConfigError):
        rendering._parse_uncertainty(uncertainty, tmp_path / "variant.json", FIXTURE_IDS[0])


def test_optional_crop_deskew_and_page_contract_are_recorded(tmp_path: Path):
    config_record = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    profile = config_record["profiles"][FIXTURE_IDS[0]]
    profile.update(
        {
            "result_kind": "page",
            "crop": [0, 0, 1400, 1100],
            "deskew_degrees": 1.0,
            "split_boundary": None,
            "output_order": ["page"],
            "blank_sides": [],
        }
    )
    config_path = tmp_path / "optional.json"
    config_path.write_text(json.dumps(config_record), encoding="utf-8")
    metadata = FixtureCatalog.load(ROOT).get(FIXTURE_IDS[0])
    result = preprocess_fixture(metadata, config_path, tmp_path / "out")
    assert result["status"] == "success"
    assert result["result"]["kind"] == "page"
    assert result["output_files"] == {
        "spread": None,
        "page": f"{metadata.fixture_id}.page.png",
        "left": None,
        "right": None,
    }
    assert result["transforms"]["crop"]["operation"] == "crop"
    assert result["transforms"]["deskew"]["operation"] == "deskew"
    assert result["transforms"]["deskew"]["parameters"] == {
        "degrees_clockwise": 1.0,
        "resampling": "bicubic",
        "expand": True,
        "fill_rgb": [255, 255, 255],
    }
    assert result["transforms"]["split"]["operation"] == "none"
    with Image.open(tmp_path / "out" / result["output_files"]["page"]) as image:
        image.verify()


def test_all_exact_fixtures_produce_complete_readable_spreads(tmp_path: Path):
    catalog = FixtureCatalog.load(ROOT)
    config = load_preprocessing_config(CONFIG_PATH)
    source_hashes = {item.fixture_id: _sha256(item.source_pdf) for item in catalog if item.pdf_available}
    for fixture_id in FIXTURE_IDS:
        metadata = catalog.get(fixture_id)
        if not metadata.pdf_available:
            pytest.fail(f"acceptance corpus missing exact PDF: {metadata.source_pdf}")
        result = preprocess_fixture(metadata, CONFIG_PATH, tmp_path / fixture_id)
        validate_metadata_contract(result)
        assert result["schema"] == METADATA_SCHEMA
        assert result["status"] == "success"
        assert result["fixture_pdf_page_index_1_based"] == 1
        assert result["source_pdf_page_index_1_based"] == metadata.source_pdf_page_index_1_based
        assert result["source_pdf_sha256"] == source_hashes[fixture_id]
        assert result["result"] == {
            "kind": "spread",
            "output_order": ["left", "right"],
            "blank_sides": ["left"] if fixture_id == "stella_maris_pdf03_session-I" else [],
        }
        assert result["source_raster"] == {
            "width_px": 1584,
            "height_px": 1224,
            "declared_pdf_rotation_degrees": 90,
        }
        assert result["transforms"]["rotation"]["operation"] == "none"
        assert result["transforms"]["crop"]["operation"] == "none"
        assert result["transforms"]["deskew"]["operation"] == "none"
        assert result["transforms"]["split"]["parameters"]["split_x"] == 792
        assert result["transforms"]["order"]["parameters"]["output_order"] == ["left", "right"]
        fixture_output = tmp_path / fixture_id
        for filename in result["output_files"].values():
            if filename is not None:
                with Image.open(fixture_output / filename) as image:
                    image.verify()
        assert _sha256(metadata.source_pdf) == source_hashes[fixture_id]


def test_blank_side_is_explicit_and_independently_inspectable(tmp_path: Path):
    metadata = FixtureCatalog.load(ROOT).get("stella_maris_pdf03_session-I")
    result = preprocess_fixture(metadata, CONFIG_PATH, tmp_path)
    assert result["pages"][0]["side"] == "left"
    assert result["pages"][0]["blank"] is True
    assert result["pages"][1]["side"] == "right"
    assert result["pages"][1]["blank"] is False
    with Image.open(tmp_path / result["output_files"]["left"]) as left:
        grayscale = left.convert("L")
        histogram = grayscale.histogram()
        dark_pixel_ratio = sum(histogram[:100]) / (left.width * left.height)
        assert dark_pixel_ratio < 0.01


def test_uncertain_profile_writes_diagnostic_metadata_without_pngs(tmp_path: Path):
    config_record = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    config_record["profiles"][FIXTURE_IDS[0]]["uncertainty"] = {
        "code": "split_unresolved",
        "field": "split",
        "reason": "gutter is not established",
    }
    config_path = tmp_path / "uncertain.json"
    config_path.write_text(json.dumps(config_record), encoding="utf-8")
    metadata = FixtureCatalog.load(ROOT).get(FIXTURE_IDS[0])
    result = preprocess_fixture(metadata, config_path, tmp_path / "out")
    assert result["status"] == UNCERTAIN
    assert result["uncertainty"]["code"] == "split_unresolved"
    assert not list((tmp_path / "out").glob("*.png"))


def test_success_then_uncertain_rerun_removes_stale_images_and_keeps_diagnostic(tmp_path: Path):
    metadata = FixtureCatalog.load(ROOT).get(FIXTURE_IDS[0])
    output_dir = tmp_path / "rerun"
    config = load_preprocessing_config(CONFIG_PATH)
    assert preprocess_fixture(metadata, CONFIG_PATH, output_dir)["status"] == SUCCESS

    uncertain_config = load_preprocessing_config(
        _write_profile_config(
            tmp_path,
            uncertainty={
                "code": "split_unresolved",
                "field": "split",
                "reason": "gutter is not established",
            },
        )
    )
    result = preprocess_fixture(metadata, uncertain_config.path, output_dir)
    assert result["status"] == UNCERTAIN
    assert json.loads(
        (output_dir / f"{metadata.fixture_id}.preprocess.json").read_text(encoding="utf-8")
    )["status"] == UNCERTAIN
    assert all(not path.exists() for path in _exact_artifacts(output_dir, metadata.fixture_id))


def test_success_then_invalid_config_rerun_removes_stale_images(tmp_path: Path):
    metadata = FixtureCatalog.load(ROOT).get(FIXTURE_IDS[0])
    output_dir = tmp_path / "invalid-rerun"
    assert preprocess_fixture(metadata, CONFIG_PATH, output_dir)["status"] == SUCCESS
    invalid_config = load_preprocessing_config(
        _write_profile_config(tmp_path, crop=[0, 0, 9999, 9999])
    )

    result = preprocess_fixture(metadata, invalid_config.path, output_dir)
    assert result["status"] == FAILURE
    assert result["error"]["code"] == "invalid_config"
    assert all(not path.exists() for path in _exact_artifacts(output_dir, metadata.fixture_id))
    assert json.loads(
        (output_dir / f"{metadata.fixture_id}.preprocess.json").read_text(encoding="utf-8")
    )["error"]["code"] == "invalid_config"


def test_successful_page_then_spread_rerun_removes_obsolete_page_variant(tmp_path: Path):
    metadata = FixtureCatalog.load(ROOT).get(FIXTURE_IDS[0])
    page_config = load_preprocessing_config(
        _write_profile_config(
            tmp_path,
            result_kind="page",
            crop=[0, 0, 1400, 1100],
            split_boundary=None,
            output_order=["page"],
            blank_sides=[],
        )
    )
    output_dir = tmp_path / "variant-rerun"
    page_result = preprocess_fixture(metadata, page_config.path, output_dir)
    assert page_result["status"] == SUCCESS
    assert (output_dir / f"{metadata.fixture_id}.page.png").is_file()

    spread_result = preprocess_fixture(metadata, CONFIG_PATH, output_dir)
    assert spread_result["status"] == SUCCESS
    assert not (output_dir / f"{metadata.fixture_id}.page.png").exists()
    assert (output_dir / f"{metadata.fixture_id}.spread.png").is_file()


def test_cleanup_failure_returns_output_error_without_claiming_safe_artifacts(tmp_path: Path, monkeypatch):
    metadata = FixtureCatalog.load(ROOT).get(FIXTURE_IDS[0])
    output_dir = tmp_path / "cleanup-failure"
    assert preprocess_fixture(metadata, CONFIG_PATH, output_dir)["status"] == SUCCESS
    uncertain_config = load_preprocessing_config(
        _write_profile_config(
            tmp_path,
            uncertainty={
                "code": "split_unresolved",
                "field": "split",
                "reason": "gutter is not established",
            },
        )
    )
    original_unlink = Path.unlink

    def fail_left_unlink(path, *args, **kwargs):
        if path.name == f"{metadata.fixture_id}.left.png":
            raise OSError("induced cleanup failure")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_left_unlink)
    result = preprocess_fixture(metadata, uncertain_config.path, output_dir)
    assert result["status"] == FAILURE
    assert result["error"]["code"] == "output_error"
    # The contract deliberately does not claim zero artifacts after cleanup
    # itself fails; this leftover is the observable unverified state.
    assert (output_dir / f"{metadata.fixture_id}.left.png").is_file()
    assert not (output_dir / f"{metadata.fixture_id}.preprocess.json").exists()


def test_invalid_exact_destination_directory_is_preserved_before_any_image_write(tmp_path: Path):
    metadata = FixtureCatalog.load(ROOT).get(FIXTURE_IDS[0])
    output_dir = tmp_path / "invalid-destination"
    output_dir.mkdir()
    invalid_destination = output_dir / f"{metadata.fixture_id}.left.png"
    invalid_destination.mkdir()

    result = preprocess_fixture(metadata, CONFIG_PATH, output_dir)
    assert result["status"] == FAILURE
    assert result["error"]["code"] == "output_error"
    assert invalid_destination.is_dir()
    assert not (output_dir / f"{metadata.fixture_id}.right.png").exists()
    assert not (output_dir / f"{metadata.fixture_id}.spread.png").exists()


def test_staging_write_failure_leaves_no_partial_images_and_reports_output_error(tmp_path: Path, monkeypatch):
    metadata = FixtureCatalog.load(ROOT).get(FIXTURE_IDS[0])
    output_dir = tmp_path / "staging-failure"
    original_save = Image.Image.save
    calls = 0

    def fail_second_save(image, destination, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("induced staging failure")
        return original_save(image, destination, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "save", fail_second_save)
    result = preprocess_fixture(metadata, CONFIG_PATH, output_dir)
    assert result["status"] == FAILURE
    assert result["error"]["code"] == "output_error"
    assert all(not path.exists() for path in _exact_artifacts(output_dir, metadata.fixture_id))
    diagnostic = output_dir / f"{metadata.fixture_id}.preprocess.json"
    assert json.loads(diagnostic.read_text(encoding="utf-8"))["error"]["code"] == "output_error"


def test_diagnostic_staging_removal_failure_is_unverified_output_error(tmp_path: Path, monkeypatch):
    metadata = FixtureCatalog.load(ROOT).get(FIXTURE_IDS[0])
    uncertain_config = _write_profile_config(
        tmp_path,
        uncertainty={
            "code": "split_unresolved",
            "field": "split",
            "reason": "gutter is not established",
        },
    )
    output_dir = tmp_path / "diagnostic-teardown-failure"
    real_rmtree = rendering.shutil.rmtree
    staging_dirs: list[Path] = []

    def fail_diagnostic_rmtree(path, *args, **kwargs):
        path = Path(path)
        if path.name.startswith(".diagnostic-"):
            staging_dirs.append(path)
            raise OSError("induced diagnostic staging teardown failure")
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(rendering.shutil, "rmtree", fail_diagnostic_rmtree)
    result = preprocess_fixture(metadata, uncertain_config, output_dir)

    assert result["status"] == FAILURE
    assert result["dpi"] == 144
    assert result["error"]["code"] == "output_error"
    assert "unverified" in result["error"]["reason"]
    assert staging_dirs and all(path.is_dir() for path in staging_dirs)
    assert not (output_dir / f"{metadata.fixture_id}.preprocess.json").exists()
    assert not list(output_dir.glob("*.png"))


def test_successful_staging_removal_failure_invalidates_published_success_and_cli_maps_failure(
    tmp_path: Path, monkeypatch, capsys
):
    metadata = FixtureCatalog.load(ROOT).get(FIXTURE_IDS[0])
    real_rmtree = rendering.shutil.rmtree
    staging_dirs: list[Path] = []

    def fail_success_rmtree(path, *args, **kwargs):
        path = Path(path)
        if path.name.startswith(f".{metadata.fixture_id}-"):
            staging_dirs.append(path)
            raise OSError("induced successful-run staging teardown failure")
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(rendering.shutil, "rmtree", fail_success_rmtree)

    backend_output = tmp_path / "backend"
    result = preprocess_fixture(metadata, CONFIG_PATH, backend_output)
    assert result["status"] == FAILURE
    assert result["error"]["code"] == "output_error"
    assert "staging cleanup" in result["error"]["reason"]
    assert staging_dirs and all(path.is_dir() for path in staging_dirs)
    assert all(not path.exists() for path in _exact_artifacts(backend_output, metadata.fixture_id))
    diagnostic = backend_output / f"{metadata.fixture_id}.preprocess.json"
    assert json.loads(diagnostic.read_text(encoding="utf-8"))["error"]["code"] == "output_error"

    cli_output = tmp_path / "cli"
    exit_code = cli_main(
        [
            "preprocess",
            metadata.fixture_id,
            "--config",
            str(CONFIG_PATH),
            "--output",
            str(cli_output),
        ]
    )
    assert exit_code == 2
    cli_payload = json.loads(capsys.readouterr().out)
    assert cli_payload["status"] == FAILURE
    assert cli_payload["error"]["code"] == "output_error"
    assert all(not path.exists() for path in _exact_artifacts(cli_output, metadata.fixture_id))
    assert json.loads(
        (cli_output / f"{metadata.fixture_id}.preprocess.json").read_text(encoding="utf-8")
    )["error"]["code"] == "output_error"


def test_publication_failure_cleans_already_published_images(tmp_path: Path, monkeypatch):
    metadata = FixtureCatalog.load(ROOT).get(FIXTURE_IDS[0])
    output_dir = tmp_path / "publication-failure"
    real_replace = rendering.os.replace
    calls = 0

    def fail_second_replace(source, destination):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("induced publication failure")
        return real_replace(source, destination)

    monkeypatch.setattr(rendering.os, "replace", fail_second_replace)
    result = preprocess_fixture(metadata, CONFIG_PATH, output_dir)
    assert result["status"] == FAILURE
    assert result["error"]["code"] == "output_error"
    assert all(not path.exists() for path in _exact_artifacts(output_dir, metadata.fixture_id))
    assert json.loads(
        (output_dir / f"{metadata.fixture_id}.preprocess.json").read_text(encoding="utf-8")
    )["error"]["code"] == "output_error"


def test_metadata_publication_failure_invalidates_prior_success_metadata(tmp_path: Path, monkeypatch):
    metadata = FixtureCatalog.load(ROOT).get(FIXTURE_IDS[0])
    output_dir = tmp_path / "metadata-failure"
    assert preprocess_fixture(metadata, CONFIG_PATH, output_dir)["status"] == SUCCESS
    metadata_path = output_dir / f"{metadata.fixture_id}.preprocess.json"
    real_replace = rendering.os.replace

    def fail_metadata_replace(source, destination):
        if Path(destination) == metadata_path:
            raise OSError("induced metadata publication failure")
        return real_replace(source, destination)

    monkeypatch.setattr(rendering.os, "replace", fail_metadata_replace)
    result = preprocess_fixture(metadata, CONFIG_PATH, output_dir)
    assert result["status"] == FAILURE
    assert result["error"]["code"] == "output_error"
    assert not metadata_path.exists()
    assert all(not path.exists() for path in _exact_artifacts(output_dir, metadata.fixture_id))


def test_source_alias_is_rejected_before_derived_write(tmp_path: Path):
    metadata = FixtureCatalog.load(ROOT).get(FIXTURE_IDS[0])
    output_dir = metadata.source_pdf.parent
    output = output_dir / f"{metadata.fixture_id}.right.png"
    stale_left = output_dir / f"{metadata.fixture_id}.left.png"
    stale_left.write_bytes(b"stale derived output")
    os.link(metadata.source_pdf, output)
    source_hash = _sha256(metadata.source_pdf)
    try:
        result = preprocess_fixture(metadata, CONFIG_PATH, output_dir)
        assert result["status"] == FAILURE
        assert result["error"]["code"] == "source_alias"
        assert not (output_dir / f"{metadata.fixture_id}.left.png").exists()
        assert _sha256(metadata.source_pdf) == source_hash
    finally:
        output.unlink(missing_ok=True)
        stale_left.unlink(missing_ok=True)
        for name in (
            f"{metadata.fixture_id}.right.png",
            f"{metadata.fixture_id}.spread.png",
            f"{metadata.fixture_id}.preprocess.json",
        ):
            (output_dir / name).unlink(missing_ok=True)


def test_metadata_path_source_alias_is_preserved_and_returns_output_error(tmp_path: Path):
    metadata = FixtureCatalog.load(ROOT).get(FIXTURE_IDS[0])
    output_dir = metadata.source_pdf.parent
    metadata_path = output_dir / f"{metadata.fixture_id}.preprocess.json"
    os.link(metadata.source_pdf, metadata_path)
    source_hash = _sha256(metadata.source_pdf)
    try:
        result = preprocess_fixture(metadata, CONFIG_PATH, output_dir)
        assert result["status"] == FAILURE
        assert result["error"]["code"] == "output_error"
        assert _sha256(metadata.source_pdf) == source_hash
        assert os.path.samefile(metadata_path, metadata.source_pdf)
        assert all(not path.exists() for path in _exact_artifacts(output_dir, metadata.fixture_id))
    finally:
        metadata_path.unlink(missing_ok=True)


def test_cli_missing_fixture_returns_failure_without_substitution(tmp_path: Path, monkeypatch, capsys):
    from dataclasses import replace

    import normalize.cli as cli

    catalog = FixtureCatalog.load(ROOT)
    missing = replace(
        catalog.get(FIXTURE_IDS[0]),
        source_pdf=tmp_path / "missing-exact.pdf",
    )
    fake_catalog = FixtureCatalog(ROOT, (missing,))
    monkeypatch.setattr(cli.FixtureCatalog, "load", lambda: fake_catalog)
    exit_code = cli.main(
        [
            "preprocess",
            FIXTURE_IDS[0],
            "--config",
            str(CONFIG_PATH),
            "--output",
            str(tmp_path / "output"),
        ]
    )
    assert exit_code == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == FAILURE
    assert "No alternate PDF will be selected" in result["error"]["reason"]
    assert not list((tmp_path / "output").glob("*.png"))


def test_installed_preprocess_command_is_clean_and_emits_one_json_line(tmp_path: Path):
    executable = Path(os.sys.executable).with_name("normalize")
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [
            str(executable),
            "preprocess",
            FIXTURE_IDS[3],
            "--config",
            str(CONFIG_PATH),
            "--output",
            str(tmp_path),
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    payload = json.loads(result.stdout)
    assert payload["status"] == "success"
    assert len(result.stdout.splitlines()) == 1


def test_installed_cli_reports_uncertain_rerun_and_invalid_destination(tmp_path: Path):
    executable = Path(os.sys.executable).with_name("normalize")
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    fixture_id = FIXTURE_IDS[0]
    output_dir = tmp_path / "cli-rerun"
    success = subprocess.run(
        [str(executable), "preprocess", fixture_id, "--config", str(CONFIG_PATH), "--output", str(output_dir)],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert success.returncode == 0, success.stderr
    assert json.loads(success.stdout)["status"] == SUCCESS

    uncertain_config = _write_profile_config(
        tmp_path,
        uncertainty={
            "code": "split_unresolved",
            "field": "split",
            "reason": "gutter is not established",
        },
    )
    uncertain = subprocess.run(
        [str(executable), "preprocess", fixture_id, "--config", str(uncertain_config), "--output", str(output_dir)],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert uncertain.returncode == 3, uncertain.stderr
    assert json.loads(uncertain.stdout)["status"] == UNCERTAIN
    assert all(not path.exists() for path in _exact_artifacts(output_dir, fixture_id))

    invalid_output = tmp_path / "cli-invalid-destination"
    invalid_output.mkdir()
    (invalid_output / f"{fixture_id}.left.png").mkdir()
    failed = subprocess.run(
        [str(executable), "preprocess", fixture_id, "--config", str(CONFIG_PATH), "--output", str(invalid_output)],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert failed.returncode == 2, failed.stderr
    failed_payload = json.loads(failed.stdout)
    assert failed_payload["status"] == FAILURE
    assert failed_payload["error"]["code"] == "output_error"
    assert (invalid_output / f"{fixture_id}.left.png").is_dir()


def test_installed_cli_config_failures_clean_prior_success_outputs(tmp_path: Path):
    executable = Path(os.sys.executable).with_name("normalize")
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    fixture_id = FIXTURE_IDS[0]
    source_pdf = FixtureCatalog.load(ROOT).get(fixture_id).source_pdf
    source_hash = _sha256(source_pdf)
    base_record = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    malformed_json = tmp_path / "malformed.json"
    malformed_json.write_text("{not-json", encoding="utf-8")
    wrong_root = tmp_path / "wrong-root.json"
    wrong_root.write_text(json.dumps({"schema": "preprocessing-config-v1", "dpi": 144}), encoding="utf-8")
    wrong_schema = tmp_path / "wrong-schema.json"
    wrong_schema_record = dict(base_record)
    wrong_schema_record["schema"] = "wrong-schema"
    wrong_schema.write_text(json.dumps(wrong_schema_record), encoding="utf-8")
    invalid_profile = tmp_path / "invalid-profile.json"
    invalid_profile_record = json.loads(json.dumps(base_record))
    invalid_profile_record["profiles"][fixture_id]["uncertainty"] = {
        "code": "split_unresolved",
        "field": "crop",
        "reason": "invalid profile for probe",
    }
    invalid_profile.write_text(json.dumps(invalid_profile_record), encoding="utf-8")
    unhashable_result_kind = tmp_path / "unhashable-result-kind.json"
    unhashable_result_kind_record = json.loads(json.dumps(base_record))
    unhashable_result_kind_record["profiles"][fixture_id]["result_kind"] = []
    unhashable_result_kind.write_text(json.dumps(unhashable_result_kind_record), encoding="utf-8")
    unhashable_rotation = tmp_path / "unhashable-rotation.json"
    unhashable_rotation_record = json.loads(json.dumps(base_record))
    unhashable_rotation_record["profiles"][fixture_id]["rotation_degrees"] = []
    unhashable_rotation.write_text(json.dumps(unhashable_rotation_record), encoding="utf-8")
    invalid_utf8 = tmp_path / "invalid-utf8.json"
    invalid_utf8.write_bytes(b'{"schema": "preprocessing-config-v1", \xff')
    oversized_deskew = tmp_path / "oversized-deskew.json"
    oversized_deskew_record = json.loads(json.dumps(base_record))
    oversized_deskew_record["profiles"][fixture_id]["deskew_degrees"] = 10**1000
    oversized_deskew.write_text(json.dumps(oversized_deskew_record), encoding="utf-8")
    parser_limit_deskew = tmp_path / "parser-limit-deskew.json"
    parser_limit_literal = "9" * 5000
    parser_limit_text = json.dumps(base_record).replace(
        '"deskew_degrees": 0',
        f'"deskew_degrees": {parser_limit_literal}',
        1,
    )
    parser_limit_deskew.write_text(parser_limit_text, encoding="utf-8")
    cases = {
        "missing": tmp_path / "missing.json",
        "malformed": malformed_json,
        "wrong-root": wrong_root,
        "wrong-schema": wrong_schema,
        "invalid-profile": invalid_profile,
        "unhashable-result-kind": unhashable_result_kind,
        "unhashable-rotation": unhashable_rotation,
        "invalid-utf8": invalid_utf8,
        "oversized-deskew": oversized_deskew,
        "parser-limit-deskew": parser_limit_deskew,
    }

    for name, config_path in cases.items():
        output_dir = tmp_path / name
        success = subprocess.run(
            [str(executable), "preprocess", fixture_id, "--config", str(CONFIG_PATH), "--output", str(output_dir)],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert success.returncode == 0, success.stderr
        assert json.loads(success.stdout)["status"] == SUCCESS
        assert list(output_dir.glob("*.png"))

        failed = subprocess.run(
            [str(executable), "preprocess", fixture_id, "--config", str(config_path), "--output", str(output_dir)],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert failed.returncode == 2, failed.stderr
        assert failed.stderr == ""
        payload = json.loads(failed.stdout)
        assert payload["status"] == FAILURE
        assert payload["dpi"] == 0
        assert payload["error"]["code"] == "invalid_config"
        assert len(failed.stdout.splitlines()) == 1
        assert not list(output_dir.glob("*.png"))
        metadata_path = output_dir / f"{fixture_id}.preprocess.json"
        assert json.loads(metadata_path.read_text(encoding="utf-8"))["error"]["code"] == "invalid_config"
        assert _sha256(source_pdf) == source_hash


def test_expected_structural_oracles_are_byte_unchanged(tmp_path: Path):
    before = {
        path: path.read_bytes()
        for path in sorted((ROOT / "fixtures").glob("*/*.expected.json"))
    }
    catalog = FixtureCatalog.load(ROOT)
    config = load_preprocessing_config(CONFIG_PATH)
    for fixture_id in FIXTURE_IDS:
        metadata = catalog.get(fixture_id)
        preprocess_fixture(metadata, CONFIG_PATH, tmp_path / fixture_id)
    assert {path: path.read_bytes() for path in before} == before
