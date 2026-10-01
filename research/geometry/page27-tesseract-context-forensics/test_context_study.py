"""Research checks for fixed-raster page-27 context comparison."""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import run_context_study as study


class ContextStudyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = study.ROOT
        cls.evidence = json.loads((study.OUT_DIR / "raw-tsv-comparison.json").read_text())

    def test_prior_source_and_final_raster_are_exact(self) -> None:
        raster, prior = study.reconstruct_source_raster()
        self.assertEqual(prior["source_sha256"], "d2ca32d3924df8f2e41db6f0d12bf387bb127aed405b9aead7759a297018b490")
        self.assertEqual(list(raster.size), [739, 1136])
        self.assertEqual(study.sha256(raster.tobytes()), "891fd22858854195cb20e8a60561b8c9073a014c4678e48f5f527cb5806a75d1")
        self.assertEqual(self.evidence["ocr"]["full_page_tsv_sha256"], prior["tsv_sha256"])
        self.assertTrue(self.evidence["ocr"]["full_page_tsv_matches_prior"])

    def test_full_page_control_reproduces_raw_malformed_boxes(self) -> None:
        records = self.evidence["full_page_control_target_records"]
        self.assertEqual([record["text_locator"] for record in records], ["See", "ae"])
        self.assertEqual(records[0]["source_tsv_row"], 190)
        self.assertEqual(records[0]["page_box_xyxy"], [7, 640, 624, 696])
        self.assertAlmostEqual(records[0]["confidence"], 14.663147)
        self.assertEqual(records[1]["source_tsv_row"], 191)
        self.assertEqual(records[1]["page_box_xyxy"], [625, 671, 639, 686])
        self.assertEqual(self.evidence["full_page_target_line_hierarchy"][0]["source_tsv_row"], 189)

    def test_crops_are_fixed_direct_views_and_outcomes_are_deterministic(self) -> None:
        manifest = json.loads((study.OUT_DIR / "crop-manifest.json").read_text())
        raster, _ = study.reconstruct_source_raster()
        for crop_id, row in manifest["crops"].items():
            self.assertFalse(row["resized"])
            self.assertFalse(row["redeskewed"])
            for prefix in ("target", "control"):
                bounds = tuple(row[f"{prefix}_bounds_xyxy_page"])
                crop = raster.crop(bounds)
                self.assertEqual(list(crop.size), row[f"{prefix}_dimensions"])
                self.assertEqual(study.sha256(crop.tobytes()), row[f"{prefix}_source_pixel_sha256"])
            run = self.evidence["crop_runs"][crop_id]
            self.assertTrue(run["target_raw_tsv_deterministic"])
            self.assertTrue(run["control_raw_tsv_deterministic"])
            self.assertEqual(run["target_raw_tsv_sha256_repeats"][0], run["target_raw_tsv_sha256_repeats"][1])
            self.assertEqual(run["control_raw_tsv_sha256_repeats"][0], run["control_raw_tsv_sha256_repeats"][1])

    def test_production_ocr_arguments_are_unchanged(self) -> None:
        image = Image.new("RGB", (5, 5), "white")
        with patch.object(study.pytesseract, "image_to_data", return_value="tsv") as call:
            self.assertEqual(study.ocr_tsv(image), "tsv")
        call.assert_called_once_with(
            image,
            lang="eng",
            config="--psm 6",
            output_type=study.Output.STRING,
        )
        self.assertEqual(self.evidence["ocr"]["tesseract_version"], "5.3.4")

    def test_crop_coordinate_mapping_adds_page_offset_without_other_changes(self) -> None:
        tsv = (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
            "5\t1\t2\t3\t4\t5\t10\t20\t30\t12\t91.5\tword\n"
        )
        mapped = study.mapped_records(tsv, (100, 200, 300, 400), (105, 215, 145, 235))
        self.assertEqual(len(mapped), 1)
        self.assertEqual(mapped[0]["source_tsv_row"], 1)
        self.assertEqual(mapped[0]["crop_local_box_xyxy"], [10, 20, 40, 32])
        self.assertEqual(mapped[0]["page_box_xyxy"], [110, 220, 140, 232])

    def test_target_transition_and_highlighted_control_are_recorded(self) -> None:
        runs = self.evidence["crop_runs"]
        self.assertEqual(runs["A_full_page"]["target_outcome"], "multirow_merged_observation")
        self.assertEqual(runs["B_text_column_broad_vertical"]["target_outcome"], "partial_per_word_observation")
        self.assertEqual(runs["C_target_plus_adjacent_rows"]["target_outcome"], "normal_per_word_observation")
        self.assertTrue(all(row["highlighted_control_outcome"] == "normal_per_word_observation" for row in runs.values()))

    def test_production_sources_are_unchanged_and_no_binary_is_tracked_or_staged(self) -> None:
        changed = subprocess.check_output(
            ["git", "diff", "--name-only", "HEAD", "--", "src", "fixtures/preprocessing.json", "tests"],
            cwd=self.root,
            text=True,
        ).splitlines()
        staged = subprocess.check_output(["git", "diff", "--cached", "--name-only"], cwd=self.root, text=True).splitlines()
        tracked_binary = subprocess.check_output(
            ["git", "ls-files", "*.jpg", "*.jpeg", "*.png", "*.pdf"],
            cwd=self.root,
            text=True,
        ).splitlines()
        self.assertEqual(changed, [])
        self.assertEqual(staged, [])
        self.assertEqual(tracked_binary, [])


if __name__ == "__main__":
    unittest.main()
